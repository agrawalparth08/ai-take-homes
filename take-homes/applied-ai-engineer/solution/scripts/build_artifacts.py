"""Build the committed evidence files in solution/output/ from the committed model outputs (no API key).

  run-manifest.{json,md}      one row per transcript (all 140): status, findings, rejects, proposals
  eval-numbers.json           dev-eval numbers per run, mean and variance, plus the pre-fix history
  idempotency-diff.{json,md}  outbox counts + hashes after run -> dispatch -> re-dispatch -> re-run -> re-dispatch
  ledger-after-demo.json      delivery-ledger rows + the Jira and corroboration records the demo wrote
  observability-sample.md     the full run's counts and health output, plus what each alarm looks like
  review-stats.json, example-card.md   measured review effort, and one real card from the queue

All state lives in a temp folder and the stubs write to a temp outbox, so the real repo state is untouched.
Run from take-homes/applied-ai-engineer/:  python solution/scripts/build_artifacts.py
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from solution import dispatch as dp  # noqa: E402
from solution import obs, pipeline, proposals, review  # noqa: E402
from solution.obs import RunLog  # noqa: E402
from solution.store import Store  # noqa: E402
from stubs import jira_stub, slack_stub  # noqa: E402

OUT = ROOT / "solution" / "output"
OUTBOX_FILES = ("jira.jsonl", "slack.jsonl", "corroborations.jsonl")


def offline_run(tmp: Path, store: Store) -> pipeline.RunResult:
    paths = pipeline.Paths(root=ROOT, state=tmp / "state", cache=ROOT / "solution" / "cache",
                           runs=tmp / "runs", out=tmp / "out")
    return pipeline.run(paths, None, store=store)


# --- 1. run manifest -----------------------------------------------------------------------------

def run_manifest(tmp: Path) -> dict:
    store = Store(tmp / "state")
    res = offline_run(tmp, store)
    status = {r["call_id"]: r for r in (dict(x) for x in store.db.execute("SELECT * FROM calls"))}
    by_call: dict[str, dict] = defaultdict(lambda: Counter())
    for f in res.findings:
        c = by_call[f.call_id]
        c["findings"] += 1
        c["actionable"] += f.actionable
        c["rejected_by_validator"] += not f.valid
        c["dismissed"] += f.valid and f.disposition == "no_action"
    props: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for p in res.proposals:
        for call in p["call_ids"]:
            props[call][p["kind"]].append(p["key"])

    events = [json.loads(l) for l in (tmp / "runs" / res.summary["run_id"] / "events.jsonl").read_text().splitlines()]
    warnings = [e.get("detail") for e in events if e["outcome"] in ("warn", "failed", "stale_fallback")]

    rows = []
    for t in sorted(res.transcripts.values(), key=lambda t: t.call_id):
        c = by_call[t.call_id]
        rows.append({
            "call_id": t.call_id, "account": t.account or "(internal)", "date": t.date,
            "owner": t.owner.name if t.owner else None,
            "status": status[t.call_id]["status"],
            "findings": c["findings"], "actionable": c["actionable"],
            "rejected_by_validator": c["rejected_by_validator"], "dismissed": c["dismissed"],
            "new_ticket": props[t.call_id]["new_ticket"], "corroborate": props[t.call_id]["corroborate"],
            "enablement": props[t.call_id]["enablement"],
        })
    s = res.summary
    return {
        "run_id": s["run_id"], "source": "committed model outputs in solution/cache (claude-sonnet-5, prompt extract-v4)",
        "totals": {
            "transcripts": s["calls"]["seen"], "processed": s["calls"]["extracted"],
            "skipped_internal": s["calls"]["skipped_internal"], "failed": s["calls"]["failed"],
            "findings": s["findings"]["total"], "actionable": s["findings"]["actionable"],
            "rejected_by_validator": s["findings"]["rejected_by_validator"], "dismissed": s["findings"]["no_action"],
            "proposals_new_ticket": s["proposals"]["new_ticket"], "proposals_corroborate": s["proposals"]["corroborate"],
            "proposals_enablement": s["proposals"]["enablement"],
            "new_tickets_grouped_across_calls": sum(len(p["call_ids"]) > 1 for p in res.proposals
                                                    if p["kind"] == "new_ticket"),
        },
        "warnings": warnings,
        "calls": rows,
    }


def manifest_md(m: dict) -> str:
    t = m["totals"]
    L = ["# Full-run manifest: all 140 transcripts", "",
         f"Run `{m['run_id']}`, replayed from {m['source']}. Regenerate: `python solution/scripts/build_artifacts.py`.", "",
         "| transcripts | processed | skipped (internal-only) | failed | findings | actionable | rejected by evidence check | dismissed with reason | new tickets | grouped across calls | corroborations | enablement |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|",
         f"| {t['transcripts']} | {t['processed']} | {t['skipped_internal']} | {t['failed']} | {t['findings']} | "
         f"{t['actionable']} | {t['rejected_by_validator']} | {t['dismissed']} | {t['proposals_new_ticket']} | "
         f"{t['new_tickets_grouped_across_calls']} | {t['proposals_corroborate']} | {t['proposals_enablement']} |", ""]
    if m["warnings"]:
        L += ["Warnings logged during the run (code handled each one):", ""]
        L += [f"- {w}" for w in m["warnings"]] + [""]
    L += ["Nothing is filed by a run: every proposal waits for a person. The ticket columns count the proposals each "
          "call contributes to (a grouped ticket appears on every call it cites).", "",
          "| call | account | status | findings | actionable | rejected | dismissed | new ticket | corroborate | enablement |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in m["calls"]:
        L.append(f"| {r['call_id']} | {r['account']} | {r['status']} | {r['findings']} | {r['actionable']} | "
                 f"{r['rejected_by_validator']} | {r['dismissed']} | {', '.join(r['new_ticket']) or '-'} | "
                 f"{', '.join(r['corroborate']) or '-'} | {', '.join(r['enablement']) or '-'} |")
    return "\n".join(L) + "\n"


# --- 2. eval numbers -----------------------------------------------------------------------------

def frac(s: str) -> float:
    a, b = s.split("/")
    return int(a) / int(b)


def eval_numbers() -> dict:
    rep = json.loads((OUT / "eval-report.json").read_text())
    runs = rep["runs"]
    rates = [frac(r["metrics"]["case_pass"]) for r in runs]
    per_case = Counter()
    for r in runs:
        for k, v in r["cases"].items():
            per_case[k] += v["pass"]
    three = json.loads((OUT / "history" / "eval-extract-v4-3runs.json").read_text())
    v3 = (OUT / "history" / "eval-extract-v3-run1.md").read_text()
    m = re.search(r"\| 0 \| \w+ \| (\d+/\d+) \| (\d+/\d+) \| (\d+/\d+) \| (\d+/\d+) \| (\d+) \|", v3)
    return {
        "dev_set": "calls 001-015, 30 label items (data/dev_labels.json restated as line spans in solution/eval/dev_expectations.json)",
        "model": "claude-sonnet-5",
        "final": {
            "prompt": "extract-v4", "runs": len(runs), "fresh_model_calls_each_run": True,
            "per_run": [dict(run=r["run"], **r["metrics"]) for r in runs],
            "case_pass_rate_mean": round(statistics.mean(rates), 4),
            "case_pass_rate_variance": round(statistics.pvariance(rates), 6),
            "case_pass_rate_min": min(rates), "case_pass_rate_max": max(rates),
            "cases_passing_every_run": f"{sum(v == len(runs) for v in per_case.values())}/{len(per_case)}",
            "flaky_cases": [k for k, v in per_case.items() if 0 < v < len(runs)],
            "report": "solution/output/eval-report.md",
        },
        "history": [
            {"prompt": "extract-v3", "runs": 1, "case_pass": m.group(1) if m else None,
             "call_pass": m.group(2) if m else None, "positive_recall": m.group(3) if m else None,
             "new_ticket_precision": m.group(4) if m else None, "garbage_writes": int(m.group(5)) if m else None,
             "note": "before the fix: a workaround ask (call-012) and a declined cosmetic remark (call-006) were filed",
             "report": "solution/output/history/eval-extract-v3-run1.md"},
            {"prompt": "extract-v4", "runs": three["summary"]["runs"], "per_run": three["summary"]["per_run"],
             "note": "run 0 replayed the cache, runs 1-2 fresh", "report": "solution/output/history/eval-extract-v4-3runs.md"},
        ],
        "baseline_file_nothing": {"case_pass": "16/30", "call_pass": "3/15", "positive_recall": "0/14"},
    }


# --- 3. idempotency diff -------------------------------------------------------------------------

def outbox_state(outbox: Path) -> dict:
    counts, h = {}, hashlib.sha256()
    for name in OUTBOX_FILES:
        p = outbox / name
        data = p.read_bytes() if p.exists() else b""
        counts[name] = data.count(b"\n")
        h.update(name.encode() + b"\0" + data)
    return {"outbox": counts, "outbox_total": sum(counts.values()), "outbox_sha256": h.hexdigest()}


def idempotency_diff(tmp: Path) -> dict:
    outbox = tmp / "outbox"
    jira_stub._OUTBOX = slack_stub._OUTBOX = str(outbox)
    jira_stub._JIRA_LOG, slack_stub._SLACK_LOG = str(outbox / "jira.jsonl"), str(outbox / "slack.jsonl")
    sinks = dp.default_sinks()
    sinks.outbox = outbox
    store = Store(tmp / "state")
    steps = []

    def record(step: str, sent: int, note: str) -> None:
        steps.append({"step": step, "sent_this_step": sent, "note": note, **outbox_state(outbox)})

    def dispatch() -> dict:
        return dp.dispatch(store, sinks, RunLog(tmp / "runs", "dispatch"))

    res = offline_run(tmp, store)
    record("run", 0, f"{len(res.proposals)} proposals, nothing written")
    # The same approvals as scripts/demo.sh: 3 tickets (one after a reviewer edit) and every corroboration.
    for k in ("new:call-006#f0", "new:call-010#f3"):
        store.decide(k, "approved", "artifact-builder")
    key = "new:call-008#f1"
    p = proposals.apply_edit(store.proposal(key)["payload"], priority="P4",
                             title='Typo "BetterBrak" in confirmation email footer', by="parthagrawal")
    store.edit_payload(key, p, proposals.sha(proposals.written_part(p)))
    store.decide(key, "approved", "artifact-builder")
    for q in store.proposals("proposed"):
        if q["kind"] == "corroborate":
            store.decide(q["key"], "approved", "artifact-builder")
    s = dispatch()
    record("dispatch #1", s["sent"], "approved: 3 tickets + 21 corroborations")
    s = dispatch()
    record("dispatch #2", s["sent"], f"{s['skipped_already_sent']} actions skipped: already sent")
    res2 = offline_run(tmp, store)
    ch = res2.summary["proposals"]
    record("re-run", 0, f"new proposals {ch['new']}, unchanged {ch['unchanged']}, changed {ch['changed']}")
    s = dispatch()
    record("dispatch #3", s["sent"], f"{s['skipped_already_sent']} actions skipped: already sent")
    read = lambda n: [json.loads(l) for l in (outbox / n).read_text().splitlines()] if (outbox / n).exists() else []
    ledger = {
        "what": "store.actions after the demo approvals, two re-dispatches and a re-run; every write happened once",
        "actions": [{k: a[k] for k in ("action_key", "proposal_key", "sink", "status", "sink_ref", "attempts")}
                    for a in store.actions()],
        "jira_records": read("jira.jsonl"),
        "corroboration_records": read("corroborations.jsonl"),
    }
    return {"what": "same approvals as scripts/demo.sh, stub outbox in a temp folder", "steps": steps}, ledger


def idempotency_md(d: dict) -> str:
    L = ["# Idempotency proof: re-run and re-dispatch write nothing new", "",
         "Generated by `python solution/scripts/build_artifacts.py` (" + d["what"] + "). "
         "`outbox sha256` hashes all three outbox files; an unchanged hash means not one byte was appended.", "",
         "| step | sent this step | jira | slack | corroborations | total | outbox sha256 | note |",
         "|---|---|---|---|---|---|---|---|"]
    for s in d["steps"]:
        o = s["outbox"]
        L.append(f"| {s['step']} | {s['sent_this_step']} | {o['jira.jsonl']} | {o['slack.jsonl']} | "
                 f"{o['corroborations.jsonl']} | {s['outbox_total']} | `{s['outbox_sha256'][:16]}` | {s['note']} |")
    return "\n".join(L) + "\n"


def observability_sample(tmp: Path, summary: dict) -> str:
    """The real run's counts and health output, then each alarm triggered on a copy of that summary."""
    def health_of(s: dict) -> list[str]:
        d = tmp / "obs" / s["run_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(json.dumps(s))
        ok, msgs = obs.health(tmp / "obs", 26.0)
        for p in d.iterdir():
            p.unlink()
        d.rmdir()
        return msgs

    now = summary
    from datetime import datetime, timedelta, timezone
    k = now["counts"]
    stale = dict(now, finished_at=(datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds"))
    misfile = dict(now, findings=dict(now["findings"], rejected_by_validator=40), counts=dict(k, validation_failed=40))
    stopped = dict(now, calls=dict(now["calls"], seen=0, extracted=0),
                   counts=dict(k, seen=0, extracted=0, skipped_internal=0, findings=0, actionable=0, dismissed=0,
                               proposals_new=0))
    failed = dict(now, calls=dict(now["calls"], failed=3, extracted=131), counts=dict(k, failed=3, extracted=131),
                  failed_calls={"call-017": "LLMError: gave up after 3 attempts", "call-044": "LLMError: timeout",
                                "call-090": "TranscriptError: no speaker lines"})
    L = ["# Observability sample", "",
         "Every run writes `var/runs/<run_id>/events.jsonl` (one event per call per stage) and `summary.json`. "
         "`python -m solution health` reads the summaries and exits 1 on any alarm. Generated by "
         "`python solution/scripts/build_artifacts.py`.", "",
         "## The full 140-call run", "", "`summary.json` counts:", "", "```json", json.dumps(now["counts"], indent=1),
         "```", "", "`health` output:", "", "```", *health_of(now), "```", "",
         "## What each alarm looks like", "",
         "Each block below is the same summary with one field changed, run through the same `health` check.", ""]
    for title, s in (("Silent stop: no run for over 26 h", stale), ("Silent stop: zero transcripts seen", stopped),
                     ("Silent mis-filing: the evidence check rejects over 15% of findings", misfile),
                     ("Partial failure: 3 calls failed", failed)):
        L += [f"### {title}", "", "```", *health_of(dict(s, run_id=s["run_id"] + "-x")), "```", ""]
    return "\n".join(L)


def review_stats(tmp: Path) -> tuple[dict, str]:
    store = Store(tmp / "state")
    res = offline_run(tmp, store)
    md = review.render(store, res.findings, tmp / "out").read_text()
    section = md.split("## New tickets", 1)[1].split("## Corroborations", 1)[0]
    cards = [c for c in section.split("\n### ")[1:]]
    visible = [c.split("<details>", 1)[0] for c in cards]  # the JSON payload is folded away by default
    words = sorted(len(v.split()) for v in visible)
    kinds = Counter(p["kind"] for p in res.proposals)
    stats = {
        "new_ticket_cards": kinds["new_ticket"], "corroborations": kinds["corroborate"],
        "enablement_nudges": kinds["enablement"],
        "decisions_needed": kinds["new_ticket"] + (kinds["corroborate"] > 0) + (kinds["enablement"] > 0),
        "decisions_note": "one approve per new ticket, one batch approve for corroborations, one for enablement",
        "median_words_per_card": statistics.median(words), "max_words_per_card": max(words),
        "median_context_lines_per_card": statistics.median(v.count("\n>  - L") for v in visible),
        "reviewer_time": "Parth spent about 1 h in total on direction and review, including reading this queue. "
                         "Per-card review time was not recorded, so no median is claimed.",
    }
    example = next(c for c in cards if "call-006" in c.split("\n", 3)[2])
    return stats, "# Example review card\n\nCopied from `output/review.md` (the new-ticket card for the search-lag bug " \
                  "that three customers reported). The data is fictional, so nothing is redacted.\n\n### " + example


def main() -> None:
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
        m = run_manifest(Path(a))
        d, ledger = idempotency_diff(Path(b))
        rs, card = review_stats(Path(c))
        full = json.loads((OUT / "last-run-summary.json").read_text())
        obs_md = observability_sample(Path(c), full)
    (OUT / "ledger-after-demo.json").write_text(json.dumps(ledger, indent=1, ensure_ascii=False))
    (OUT / "observability-sample.md").write_text(obs_md)
    (OUT / "review-stats.json").write_text(json.dumps(rs, indent=1))
    (OUT / "example-card.md").write_text(card)
    (OUT / "run-manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False))
    (OUT / "run-manifest.md").write_text(manifest_md(m))
    (OUT / "eval-numbers.json").write_text(json.dumps(eval_numbers(), indent=1))
    (OUT / "idempotency-diff.json").write_text(json.dumps(d, indent=1))
    (OUT / "idempotency-diff.md").write_text(idempotency_md(d))
    print(json.dumps(m["totals"]), "\n", idempotency_md(d))


if __name__ == "__main__":
    main()
