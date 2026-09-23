"""Dev-set eval (calls 001-015) against eval/dev_expectations.json.

Pass/fail is mechanical so two engineers get the same verdict:
- Each label item is a CASE anchored to an inclusive line span in the transcript.
- A prediction is the (proposal, call) pair with the transcript lines its evidence cites.
  Writes = new tickets and corroborations. Enablement nudges don't file anything.
- file-new       PASS iff a new-ticket prediction of the right type cites a line in the span.
- file-new-low   same, and priority is P4 (lowest).
- corroborate    PASS iff a corroboration to that exact issue cites a line in the span.
- cluster:<case> PASS iff this call's evidence sits in the SAME new ticket that passed <case>.
- none           PASS iff no unmatched write cites a line in the span.
- A call PASSES iff all its cases pass and it has zero unmatched writes (no garbage filed).
Each prediction can satisfy at most one case.

For every failing case the report names the stage that lost it (never extracted / dismissed by triage /
rejected by validator / matched to the wrong issue / merged or split by clustering), with the model's own
finding text and the gold label side by side, so a reviewer can tell a genuine miss from a bad key.
"""

from __future__ import annotations

import json
import shutil
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import pipeline
from .extract import Finding
from .llm import LLM
from .store import Store

WRITES = {"new_ticket", "corroborate"}


@dataclass
class Pred:
    proposal_key: str
    kind: str
    call_id: str
    lines: set[int]
    target: str | None
    type: str | None
    priority: str | None


def predictions(proposals: list[dict]) -> list[Pred]:
    out = []
    for p in proposals:
        by_call: dict[str, set[int]] = defaultdict(set)
        for e in p["review"]["evidence"]:
            by_call[e["call_id"]].add(e["line"])  # the quoted line only: context lines would over-match
        for call, lines in by_call.items():
            out.append(Pred(p["key"], p["kind"], call, lines,
                            p["review"].get("target"),
                            p.get("jira", {}).get("type"), p.get("jira", {}).get("priority")))
    return out


def grade(cases: list[dict], proposals: list[dict], findings: list[Finding]) -> dict:
    preds = predictions(proposals)
    used: set[int] = set()
    verdict: dict[str, dict] = {}

    def in_span(p: Pred, c: dict) -> bool:
        lo, hi = c["span"]
        return p.call_id == c["call_id"] and any(lo <= n <= hi for n in p.lines)

    def fits(c: dict, p: Pred, ref: str | None) -> bool:
        a, tgt = c["action"], c.get("target") or ""
        if not in_span(p, c):
            return False
        if a in ("file-new", "file-new-low"):
            return p.kind == "new_ticket" and p.type == c["type"] and (a == "file-new" or p.priority == "P4")
        if tgt.startswith("cluster:"):
            return p.kind == "new_ticket" and p.proposal_key == ref
        return p.kind == "corroborate" and p.target == tgt

    positives = [c for c in cases if c["action"] != "none"]
    # Most-constrained case first, so a prediction that could satisfy two cases goes to the one that has no
    # alternative. Cluster references are resolved after the case they point at.
    base = [c for c in positives if not str(c.get("target", "")).startswith("cluster:")]
    refs = [c for c in positives if str(c.get("target", "")).startswith("cluster:")]
    for group in (base, refs):
        def options(c):
            ref = verdict.get(str(c.get("target", "")).split(":", 1)[-1], {}).get("proposal_key")
            return [i for i, p in enumerate(preds) if i not in used and fits(c, p, ref)]
        for c in sorted(group, key=lambda c: len(options(c))):
            opts = options(c)
            p = preds[opts[0]] if opts else None
            if opts:
                used.add(opts[0])
            verdict[c["case_id"]] = {"pass": p is not None, "proposal_key": p.proposal_key if p else None}

    unmatched = [p for i, p in enumerate(preds) if i not in used and p.kind in WRITES]
    for c in cases:
        if c["action"] == "none":
            bad = [p for p in unmatched if in_span(p, c)]
            verdict[c["case_id"]] = {"pass": not bad, "wrote": [p.proposal_key for p in bad]}

    calls = sorted({c["call_id"] for c in cases})
    call_pass = {}
    for call in calls:
        extra = [p.proposal_key for p in unmatched if p.call_id == call]
        call_pass[call] = {"pass": all(verdict[c["case_id"]]["pass"] for c in cases if c["call_id"] == call)
                           and not extra, "extra_writes": extra}

    for c in cases:
        v = verdict[c["case_id"]]
        v.update(action=c["action"], target=c.get("target"), label=c["label_text"])
        if not v["pass"]:
            v["diagnosis"] = diagnose(c, findings, proposals)

    n_new_pred = len({p.proposal_key for p in preds if p.kind == "new_ticket"})
    n_new_ok = len({verdict[c["case_id"]]["proposal_key"] for c in cases
                    if c["action"].startswith("file-new") and verdict[c["case_id"]]["pass"]})
    pos = positives
    return {
        "cases": verdict, "calls": call_pass,
        "metrics": {
            "case_pass": f"{sum(v['pass'] for v in verdict.values())}/{len(verdict)}",
            "call_pass": f"{sum(v['pass'] for v in call_pass.values())}/{len(call_pass)}",
            "positive_recall": f"{sum(verdict[c['case_id']]['pass'] for c in pos)}/{len(pos)}",
            "new_ticket_precision": f"{n_new_ok}/{n_new_pred}",
            "garbage_writes": len({p.proposal_key for p in unmatched}),  # per ticket, not per (ticket, call)
            "injection_writes": sum(len(verdict[c["case_id"]]["wrote"]) for c in cases if _is_injection(c)),
        },
    }


def _is_injection(c: dict) -> bool:
    return c["action"] == "none" and any(w in c["label_text"].lower() for w in ("injection", "instruction"))


def diagnose(c: dict, findings: list[Finding], proposals: list[dict]) -> str:
    lo, hi = c["span"]
    fs = [f for f in findings if f.call_id == c["call_id"] and (lo <= f.line <= hi or any(lo <= n <= hi for n in f.context_lines))]
    if c["action"] == "none":
        return "wrote here: " + "; ".join(f"{f.id} L{f.line} '{f.title}' ({f.disposition})" for f in fs if f.actionable)
    if not fs:
        return "NEVER EXTRACTED: model produced no finding in the span"
    parts = [f"(span L{lo}-L{hi})"]
    for f in fs:
        if not f.valid:
            parts.append(f"REJECTED BY VALIDATOR {f.id}: {f.reject_reason}")
        elif f.disposition == "no_action":
            parts.append(f"DISMISSED {f.id} ({f.no_action_reason}{'; ' + f.policy_note if f.policy_note else ''}): '{f.title}'")
        elif f.disposition == "matches_tracked":
            parts.append(f"MATCHED {f.id} L{f.line} to {f.tracked_key}: '{f.title}' / {f.match_note}")
        elif f.disposition == "new":
            owner = next((p["key"] for p in proposals if any(e["finding_id"] == f.id for e in p["review"]["evidence"])), None)
            parts.append(f"NEW {f.id} L{f.line} '{f.title}' [{f.kind}/{f.severity}] -> {owner}")
        else:
            parts.append(f"{f.disposition.upper()} {f.id} -> {f.tracked_key}")
    return " | ".join(parts)


def run_eval(root: Path, llm: LLM | None, runs: int, refresh: bool, out_dir: Path, name: str = "eval-report") -> dict:
    spec = json.loads((root / "solution" / "eval" / "dev_expectations.json").read_text())
    cases = spec["cases"]
    dev = {c["call_id"] for c in cases}
    paths = pipeline.Paths.default(root)
    results = []
    for i in range(runs):
        tmp = Path(tempfile.mkdtemp(prefix="june-eval-"))
        # Run 0 replays the committed cache unless --refresh; later runs always call the model fresh.
        cache = paths.cache if (i == 0 and not refresh) else tmp / "cache"
        p = pipeline.Paths(root=root, state=tmp / "state", cache=cache, runs=tmp / "runs", out=tmp / "out")
        res = pipeline.run(p, llm, only=dev, store=Store(tmp / "state"), persist=False)
        g = grade(cases, res.proposals, res.findings)
        g["run"] = i
        g["cache"] = "committed" if cache == paths.cache else "fresh"
        results.append(g)
        shutil.rmtree(tmp, ignore_errors=True)

    report = summarize(results, cases)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps({"summary": report, "runs": results}, indent=1))
    (out_dir / f"{name}.md").write_text(render(report, results))
    return report


def summarize(results: list[dict], cases: list[dict]) -> dict:
    n = len(results)
    per_case = {c["case_id"]: sum(r["cases"][c["case_id"]]["pass"] for r in results) for c in cases}
    per_call = defaultdict(int)
    for r in results:
        for call, v in r["calls"].items():
            per_call[call] += v["pass"]
    frac = lambda s: int(s.split("/")[0]) / int(s.split("/")[1]) if int(s.split("/")[1]) else 0.0
    return {
        "runs": n,
        "case_pass_mean": round(statistics.mean(frac(r["metrics"]["case_pass"]) for r in results), 3),
        "case_pass_all_runs": f"{sum(v == n for v in per_case.values())}/{len(per_case)}",
        "call_pass_all_runs": f"{sum(v == n for v in per_call.values())}/{len(per_call)}",
        "flaky_cases": {k: f"{v}/{n}" for k, v in per_case.items() if 0 < v < n},
        "always_failing": [k for k, v in per_case.items() if v == 0],
        "garbage_writes_per_run": [r["metrics"]["garbage_writes"] for r in results],
        "injection_writes_per_run": [r["metrics"]["injection_writes"] for r in results],
        "per_run": [r["metrics"] for r in results],
    }


def render(s: dict, results: list[dict]) -> str:
    L = ["# Dev-set eval (calls 001-015)", "",
         f"Runs: {s['runs']} · mean case pass rate {s['case_pass_mean']:.0%} · cases passing EVERY run "
         f"{s['case_pass_all_runs']} · calls passing every run {s['call_pass_all_runs']}", "",
         f"Garbage writes per run: {s['garbage_writes_per_run']} · injection-triggered writes per run: "
         f"{s['injection_writes_per_run']}", "", "| run | cache | cases | calls | positive recall | new-ticket precision | garbage |",
         "|---|---|---|---|---|---|---|"]
    for r in results:
        m = r["metrics"]
        L.append(f"| {r['run']} | {r['cache']} | {m['case_pass']} | {m['call_pass']} | {m['positive_recall']} | "
                 f"{m['new_ticket_precision']} | {m['garbage_writes']} |")
    if s["flaky_cases"]:
        L += ["", "**Flaky (pass in some runs only):** " + ", ".join(f"{k} {v}" for k, v in s["flaky_cases"].items())]
    if s["always_failing"]:
        L += ["", "**Failing in every run:** " + ", ".join(s["always_failing"])]
    L += ["", "## Failures by run", ""]
    for r in results:
        bad = {k: v for k, v in r["cases"].items() if not v["pass"]}
        extra = {k: v["extra_writes"] for k, v in r["calls"].items() if v["extra_writes"]}
        L.append(f"### run {r['run']}: {len(bad)} failing case(s)")
        for k, v in bad.items():
            L += [f"- **{k}** expected `{v['action']}{' ' + v['target'] if v.get('target') else ''}`: {v['label']}",
                  f"  - got: {v.get('diagnosis', '')}"]
        for call, keys in extra.items():
            L.append(f"- {call} unmatched writes: {keys}")
        L.append("")
    return "\n".join(L)
