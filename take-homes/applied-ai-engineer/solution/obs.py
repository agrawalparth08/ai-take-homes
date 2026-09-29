"""Structured run log + health checks.

Every stage emits one JSON event per call to runs/<run_id>/events.jsonl. The run ends with
summary.json. `health` reads the latest summaries and answers two questions for an operator:
  1. Did it silently stop?        (no recent run, calls not processed, all-zero output)
  2. Did it silently start mis-filing? (rates drift outside the band of previous runs)
"""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunLog:
    def __init__(self, runs_dir: Path, command: str):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.dir = runs_dir / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self.counts: Counter[str] = Counter()
        self.t0 = time.monotonic()
        self.command = command
        self.event("run", "start", command=command)

    def event(self, stage: str, outcome: str, call_id: str | None = None, **fields: Any) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "run_id": self.run_id,
               "stage": stage, "outcome": outcome, **({"call_id": call_id} if call_id else {}), **fields}
        self._fh.write(json.dumps(rec, default=str) + "\n")
        self._fh.flush()
        self.counts[f"{stage}.{outcome}"] += 1

    def finish(self, **summary: Any) -> dict:
        s = {"run_id": self.run_id, "command": self.command,
             "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "duration_s": round(time.monotonic() - self.t0, 1), "event_counts": dict(self.counts), **summary}
        self.dir.mkdir(parents=True, exist_ok=True)  # survive someone clearing state mid-run
        (self.dir / "summary.json").write_text(json.dumps(s, indent=1))
        self.event("run", "finish")
        self._fh.close()
        return s


def health(runs_dir: Path, max_age_hours: float = 26.0, store=None) -> tuple[bool, list[str]]:
    """Return (healthy, messages). Designed to be run by a separate scheduler/alerting job.
    Only full-scope runs count: an `--only` debug run must not mask a stalled schedule."""
    summaries = []
    for p in sorted(runs_dir.glob("*/summary.json")):
        s = json.loads(p.read_text())
        if s.get("command") == "run" and s.get("scope", "full") == "full":
            summaries.append(s)
    msgs: list[str] = []
    if not summaries:
        return False, ["STOPPED: no completed `run` found"]
    last = summaries[-1]
    ok = True

    age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(last["finished_at"])).total_seconds() / 3600
    if age_h > max_age_hours:
        ok = False
        msgs.append(f"STOPPED: last successful run {age_h:.1f}h ago (> {max_age_hours}h)")

    c = last["calls"]
    if c["seen"] == 0:
        ok = False
        msgs.append("STOPPED: run saw zero transcripts (input path or upstream export broken?)")
    if c["failed"]:
        ok = False
        msgs.append(f"DEGRADED: {c['failed']}/{c['seen']} calls failed: {last.get('failed_calls')}")

    f = last["findings"]
    actionable = max(f["actionable"], 1)
    reject_rate = f["rejected_by_validator"] / max(f["actionable"] + f["rejected_by_validator"], 1)
    if reject_rate > 0.15:
        ok = False
        msgs.append(f"MISFILING RISK: validator rejected {reject_rate:.0%} of actionable findings "
                    "(model quoting/attribution drift?)")

    processed = max(c["extracted"], 1)
    rate = f["actionable"] / processed
    prev = [s["findings"]["actionable"] / max(s["calls"]["extracted"], 1) for s in summaries[:-1][-10:]
            if s["calls"]["extracted"]]
    if prev:
        lo, hi = min(prev) * 0.5, max(prev) * 1.5
        if not lo <= rate <= hi:
            ok = False
            msgs.append(f"DRIFT: {rate:.2f} actionable findings/call vs recent band [{lo:.2f}, {hi:.2f}]")
    if last.get("degraded"):
        ok = False
        msgs.append("DEGRADED: clustering failed last run; duplicates were not merged and withdrawals were skipped")
    stale = last.get("event_counts", {}).get("extract.stale_fallback", 0)
    if stale:
        ok = False
        msgs.append(f"DEGRADED: {stale} calls reused an old extraction because the model call failed")
    if store is not None:
        stuck = [a["action_key"] for a in store.actions() if a["status"] in ("sending", "failed")]
        if stuck:
            ok = False
            msgs.append(f"DELIVERY: {len(stuck)} writes failed or unconfirmed (run dispatch to reconcile): {stuck[:5]}")
        waiting = [p for p in store.proposals("approved") if not any(
            a["proposal_key"] == p["key"] and a["status"] == "sent" for a in store.actions())]
        old = [p["key"] for p in waiting if p["decided_at"] and
               (datetime.now(timezone.utc) - datetime.fromisoformat(p["decided_at"])).total_seconds() > max_age_hours * 3600]
        if old:
            ok = False
            msgs.append(f"DELIVERY: {len(old)} approved proposals never dispatched (dispatch job not running?)")
    if c["extracted"] >= 10 and f["actionable"] == 0:
        ok = False
        msgs.append("STOPPED?: 10+ calls processed and zero actionable findings")
    k = last.get("counts", {})
    if ok:
        msgs.append(f"OK: run {last['run_id']} processed {c['extracted']} calls, {actionable if f['actionable'] else 0} "
                    f"actionable findings, {reject_rate:.0%} validator rejects, {age_h:.1f}h ago")
    if k:  # always print the counts, healthy or not, so a trend is visible run to run
        msgs.append(f"COUNTS: seen {k['seen']}, extracted {k['extracted']}, skipped {k['skipped_internal']}, "
                    f"failed {k['failed']}, validation_failed {k['validation_failed']}, dismissed {k['dismissed']}, "
                    f"new proposals {k['proposals_new']}, changed {k['proposals_changed']}, withdrawn {k['withdrawn']}")
    return ok, msgs
