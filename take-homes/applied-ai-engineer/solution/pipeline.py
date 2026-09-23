"""`run`: transcripts -> validated findings -> proposals in the store + a review packet.

Nothing here writes to Jira/Slack. That only happens in dispatch.py, after human approval.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import extract as ex
from . import proposals as pr
from .llm import LLM
from .obs import RunLog
from .store import Store
from .transcript import Transcript, TranscriptError, load


@dataclass
class Paths:
    root: Path  # the exercise folder (transcripts/, data/, stubs/)
    state: Path
    cache: Path
    runs: Path
    out: Path

    @classmethod
    def default(cls, root: Path) -> "Paths":
        sol = root / "solution"
        return cls(root=root, state=sol / "var", cache=sol / "cache", runs=sol / "var" / "runs", out=sol / "output")


@dataclass
class RunResult:
    findings: list[ex.Finding] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    transcripts: dict[str, Transcript] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


def run(paths: Paths, llm: LLM | None, *, only: set[str] | None = None, refresh: bool = False,
        workers: int = 4, store: Store | None = None, persist: bool = True) -> RunResult:
    log = RunLog(paths.runs, "run")
    store = store or Store(paths.state)
    catalog = json.loads((paths.root / "data" / "existing_issues.json").read_text())
    by_key = {i["key"]: i for i in catalog}
    files = sorted((paths.root / "transcripts").glob("call-*.md"))
    if only:
        files = [f for f in files if f.stem in only]

    res = RunResult()
    failed: dict[str, str] = {}
    stats = {"seen": len(files), "extracted": 0, "skipped_internal": 0, "failed": 0, "from_cache": 0}

    # 1. Parse (code). Internal-only calls never reach the model.
    todo: list[Transcript] = []
    for f in files:
        try:
            t = load(f)
        except (TranscriptError, UnicodeDecodeError) as e:
            failed[f.stem] = str(e)
            log.event("parse", "failed", call_id=f.stem, error=str(e))
            continue
        res.transcripts[t.call_id] = t
        if not t.has_external:
            stats["skipped_internal"] += 1
            store.set_call(t.call_id, t.sha256, "skipped_internal", log.run_id)
            log.event("parse", "skipped_internal", call_id=t.call_id, reason="no [EXTERNAL] participant")
            continue
        todo.append(t)

    # 2. Extract (model, cached) + validate (code). Each call isolated: one failure doesn't touch others.
    def work(t: Transcript):
        try:
            e = ex.extract(t, llm, catalog, paths.cache, refresh=refresh)
            for f in e.findings:
                ex.validate(t, f, by_key)
                pr.apply_policy(f, t, by_key)
            return t, e, None
        except Exception as err:
            return t, None, f"{type(err).__name__}: {err}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for t, e, err in pool.map(work, todo):
            if err:
                failed[t.call_id] = err
                store.set_call(t.call_id, t.sha256, "failed", log.run_id, error=err)
                log.event("extract", "failed", call_id=t.call_id, error=err)
                continue
            stats["extracted"] += 1
            stats["from_cache"] += int(e.cached)
            store.set_call(t.call_id, t.sha256, "extracted", log.run_id)
            res.findings.extend(e.findings)
            log.event("extract", "ok", call_id=t.call_id, cached=e.cached, model=e.model,
                      prompt_version=e.prompt_version, n_findings=len(e.findings),
                      n_actionable=sum(f.actionable for f in e.findings),
                      n_rejected=sum(not f.valid for f in e.findings), **e.usage)
            for f in e.findings:
                log.event("finding", _outcome(f), call_id=t.call_id, finding=f.id, line=f.line,
                          kind=f.kind, disposition=f.disposition, tracked_key=f.tracked_key,
                          reason=f.reject_reason or f.no_action_reason or f.policy_note, title=f.title)
    stats["failed"] = len(failed)

    # 3. Build proposals (code) with cross-call clustering (model, validated).
    res.proposals = build_proposals(res.findings, res.transcripts, by_key, store, llm, paths.cache, log)

    # 4. Persist proposals. Approved-then-changed payloads lose their approval automatically.
    changes = {"new": 0, "unchanged": 0, "changed": 0, "locked": 0}
    if persist:
        for p in res.proposals:
            outcome = store.upsert_proposal(p["key"], p["kind"], p, pr.sha(pr.written_part(p)), log.run_id)
            changes[outcome] += 1
            log.event("proposal", outcome, proposal=p["key"], kind=p["kind"], calls=p["call_ids"])
        # Only withdraw proposals from calls this run actually looked at (a partial / --only run must
        # not withdraw everything else).
        scope = {c for c in res.transcripts if c not in failed}
        live = {p["key"] for p in res.proposals}
        withdrawn = [k for k in store.withdraw_missing(live | _out_of_scope(store, scope), log.run_id)]
        for k in withdrawn:
            log.event("proposal", "withdrawn", proposal=k)
        (paths.state / "last_findings.json").write_text(json.dumps([asdict(f) for f in res.findings], indent=1))

    fs = res.findings
    res.summary = log.finish(
        calls=stats, failed_calls=failed,
        findings={"total": len(fs), "actionable": sum(f.actionable for f in fs),
                  "rejected_by_validator": sum(not f.valid for f in fs),
                  "no_action": sum(f.valid and f.disposition == "no_action" for f in fs)},
        proposals={"new_ticket": sum(p["kind"] == "new_ticket" for p in res.proposals),
                   "corroborate": sum(p["kind"] == "corroborate" for p in res.proposals),
                   "enablement": sum(p["kind"] == "enablement" for p in res.proposals), **changes},
    )
    return res


def _outcome(f: ex.Finding) -> str:
    if not f.valid:
        return "rejected_by_validator"
    return f.disposition


def _out_of_scope(store: Store, scope: set[str]) -> set[str]:
    return {p["key"] for p in store.proposals() if not set(p["payload"]["call_ids"]) & scope}


def build_proposals(findings: list[ex.Finding], ts: dict[str, Transcript], by_key: dict[str, dict],
                    store: Store, llm: LLM | None, cache: Path, log: RunLog) -> list[dict]:
    # Evidence already covered by something we dispatched is settled and must not be re-proposed (e.g. as
    # a "corroboration" of the very ticket it created). Keyed by (call, transcript version, quoted line),
    # not by finding index: a re-extraction can reorder the model's list.
    settled: set[tuple[str, str, int]] = set()
    dispatched_keys = {a["proposal_key"] for a in store.actions() if a["status"] == "sent"}
    for p in store.proposals():
        if p["key"] in dispatched_keys:
            settled.update((e["call_id"], e.get("sha", ""), e["line"]) for e in p["payload"]["review"]["evidence"])

    live = [f for f in findings if f.actionable and (f.call_id, ts[f.call_id].sha256[:12], f.line) not in settled]
    related: dict[str, list[ex.Finding]] = {}
    for f in findings:  # workaround requests ride along with the issue they work around
        if f.valid and f.disposition == "no_action" and f.no_action_reason == "workaround_request" and f.related_line:
            host = next((g for g in live if g.call_id == f.call_id and g.line == f.related_line), None)
            if host:
                related.setdefault(host.id, []).append(f)

    out: list[dict] = []
    # Corroborations of tracked issues: one per (call, issue).
    corr: dict[tuple[str, str], list[ex.Finding]] = {}
    for f in live:
        if f.disposition == "matches_tracked":
            corr.setdefault((f.call_id, f.tracked_key), []).append(f)
        elif f.disposition == "shipped_feature":
            out.append(pr.enablement(f, by_key[f.tracked_key], ts[f.call_id]))
    for (call_id, key), members in corr.items():
        out.append(pr.corroboration(call_id, key, by_key[key]["summary"], members, ts[call_id], False))

    # New issues: cluster across calls (and against tickets we already filed).
    filed = store.filed_tickets()
    groups = pr.cluster([f for f in live if f.disposition == "new"], filed, llm, cache, log)
    filed_by_key = {x["key"]: x for x in filed}
    for g in groups:
        log.event("cluster", "group", members=[m.id for m in g.members], filed_key=g.filed_key, reason=g.reason)
        if g.filed_key:
            already = set(filed_by_key[g.filed_key]["call_ids"])  # calls already attached to that ticket
            for call_id in sorted({m.call_id for m in g.members} - already):
                ms = [m for m in g.members if m.call_id == call_id]
                out.append(pr.corroboration(call_id, g.filed_key, filed_by_key[g.filed_key]["title"], ms,
                                            ts[call_id], True))
        else:
            out.append(pr.new_ticket(g, ts, related))
    return sorted(out, key=lambda p: p["key"])


def last_findings(paths: Paths) -> list[ex.Finding]:
    p = paths.state / "last_findings.json"
    return [ex.Finding(**d) for d in json.loads(p.read_text())] if p.exists() else []
