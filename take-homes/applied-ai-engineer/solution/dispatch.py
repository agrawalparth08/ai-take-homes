"""Approved proposals -> sinks, through the ledger. No model involvement.

Delivery protocol per action (jira | slack | corroboration):
  1. ledger row -> 'sending' (committed BEFORE the sink call)
  2. call the sink
  3. ledger row -> 'sent' with the sink's reference
A crash between 2 and 3 leaves 'sending'. On the next dispatch we do NOT blindly resend: we look
for our idempotency key in the sink's own record (the stub outbox; in production a Jira JQL search
on the label / Slack message metadata) and adopt it if present. Only if it is absent do we resend.
The stubs don't de-duplicate, so this ledger + reconcile step is the idempotency guarantee.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .obs import RunLog
from .proposals import sha, written_part
from .store import Store


@dataclass
class Sinks:
    jira_create: Callable[[dict], dict]
    slack_post: Callable[[dict], dict]
    corroborate: Callable[[dict], dict]
    outbox: Path

    def find(self, sink: str, idem: str) -> dict | None:
        path = self.outbox / {"jira": "jira.jsonl", "slack": "slack.jsonl", "corroboration": "corroborations.jsonl"}[sink]
        if not path.exists():
            return None
        for row in path.read_text().splitlines():
            if row.strip():
                rec = json.loads(row)
                if rec.get("idempotency_key") == idem:
                    return rec
        return None


def default_sinks() -> Sinks:
    from stubs import jira_stub, slack_stub  # the provided sinks, unmodified

    outbox = Path(jira_stub._OUTBOX)

    def corroborate(record: dict) -> dict:
        # The Jira stub has no comment/update API. Production: POST /issue/{key}/comment + add the
        # account to a "reported by" field. Here: an append-only local record in the same outbox.
        os.makedirs(outbox, exist_ok=True)
        with open(outbox / "corroborations.jsonl", "a") as fh:
            fh.write(json.dumps(record) + "\n")
        return record

    return Sinks(jira_stub.create_issue, slack_stub.post_message, corroborate, outbox)


def dispatch(store: Store, sinks: Sinks, log: RunLog) -> dict:
    stats = {"sent": 0, "reconciled": 0, "skipped_already_sent": 0, "stale_approval": 0, "failed": 0}
    with store.exclusive("dispatch"):
        for p in store.proposals("approved"):
            payload = p["payload"]
            if sha(written_part(payload)) != p["approved_sha"]:
                stats["stale_approval"] += 1
                log.event("dispatch", "blocked_stale_approval", proposal=p["key"])
                continue
            try:
                _deliver(store, sinks, log, p["key"], payload, stats)
            except Exception as e:  # one proposal failing must not stop the others
                stats["failed"] += 1
                log.event("dispatch", "failed", proposal=p["key"], error=f"{type(e).__name__}: {e}")
    return stats


def _deliver(store: Store, sinks: Sinks, log: RunLog, key: str, payload: dict, stats: dict) -> None:
    jira_key = None
    if "jira" in payload:
        rec = _once(store, sinks, log, key, f"{key}:jira", "jira", payload["jira"], sinks.jira_create, stats)
        jira_key = rec["key"] if isinstance(rec, dict) else rec
    if "corroboration" in payload:
        _once(store, sinks, log, key, f"{key}:corroboration", "corroboration", payload["corroboration"],
              sinks.corroborate, stats)
    for msg in payload.get("slack", []):
        body = dict(msg, text=msg["text"].replace("{jira_key}", jira_key or ""))
        _once(store, sinks, log, key, f"{key}:slack:{msg['channel']}", "slack", body, sinks.slack_post, stats)


def _once(store: Store, sinks: Sinks, log: RunLog, proposal_key: str, action_key: str, sink: str,
          body: dict, send: Callable[[dict], dict], stats: dict):
    row = store.action(action_key)
    if row and row["status"] == "sent":
        stats["skipped_already_sent"] += 1
        return row["sink_ref"]
    if row and row["status"] in ("sending", "failed"):  # a failed call may still have landed (timeouts)
        found = sinks.find(sink, body["idempotency_key"])
        if found is not None:
            ref = found.get("key") or found.get("ts") or body["idempotency_key"]
            store.mark_action(action_key, proposal_key, sink, "sent", sink_ref=ref)
            stats["reconciled"] += 1
            log.event("dispatch", "reconciled_from_outbox", proposal=proposal_key, action=action_key, ref=ref)
            return found if sink == "jira" else ref
        log.event("dispatch", "resend_after_crash", proposal=proposal_key, action=action_key)

    store.mark_action(action_key, proposal_key, sink, "sending")
    try:
        rec = send(body)
    except Exception as e:
        store.mark_action(action_key, proposal_key, sink, "failed", error=f"{type(e).__name__}: {e}")
        raise
    ref = rec.get("key") or rec.get("ts") or body["idempotency_key"]
    store.mark_action(action_key, proposal_key, sink, "sent", sink_ref=ref)
    stats["sent"] += 1
    log.event("dispatch", "sent", proposal=proposal_key, action=action_key, sink=sink, ref=ref)
    return rec if sink == "jira" else ref
