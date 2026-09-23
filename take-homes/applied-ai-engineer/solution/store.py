"""SQLite workflow state: per-call status, proposals, approvals, and the delivery ledger.

This is the system of record for "what have we already done". The stubs are naive sinks;
every write to them goes through the `actions` ledger here.
"""

from __future__ import annotations

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  call_id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL,          -- extracted | skipped_internal | failed
  error TEXT,
  run_id TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
  key TEXT PRIMARY KEY,          -- stable identity, see proposals.py
  kind TEXT NOT NULL,            -- new_ticket | corroborate | enablement
  payload TEXT NOT NULL,         -- JSON: everything that would be written
  payload_sha TEXT NOT NULL,
  status TEXT NOT NULL,          -- proposed | approved | rejected | withdrawn
  approved_sha TEXT,             -- payload_sha at approval time; mismatch = stale approval
  decided_by TEXT,
  decided_at TEXT,
  note TEXT,
  run_id TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
  action_key TEXT PRIMARY KEY,   -- proposal_key + ':' + sink (+ recipient)
  proposal_key TEXT NOT NULL REFERENCES proposals(key),
  sink TEXT NOT NULL,            -- jira | slack | corroboration
  status TEXT NOT NULL,          -- sending | sent | failed
  sink_ref TEXT,                 -- e.g. the Jira key the stub assigned
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.dir = state_dir
        self.db = sqlite3.connect(state_dir / "state.db", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @contextmanager
    def exclusive(self, name: str) -> Iterator[None]:
        """Single-writer lock so two schedulers can't dispatch the same action concurrently."""
        with open(self.dir / f"{name}.lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(f"another '{name}' process holds the lock; refusing to run concurrently")
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # --- calls -------------------------------------------------------------
    def set_call(self, call_id: str, sha: str, status: str, run_id: str, error: str | None = None) -> None:
        with self.tx() as db:
            db.execute(
                "INSERT INTO calls VALUES (?,?,?,?,?,?) ON CONFLICT(call_id) DO UPDATE SET "
                "sha256=excluded.sha256, status=excluded.status, error=excluded.error, "
                "run_id=excluded.run_id, updated_at=excluded.updated_at",
                (call_id, sha, status, error, run_id, now()),
            )

    # --- proposals ---------------------------------------------------------
    def upsert_proposal(self, key: str, kind: str, payload: dict, sha: str, run_id: str) -> str:
        """Insert or refresh a proposal. Returns what happened: new | unchanged | changed | locked.

        A proposal that has already been dispatched is never rewritten (locked). If the payload of an
        approved-but-undispatched proposal changes, its approval goes stale automatically because
        approved_sha no longer equals payload_sha.
        """
        with self.tx() as db:
            row = db.execute("SELECT payload_sha, status FROM proposals WHERE key=?", (key,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO proposals (key, kind, payload, payload_sha, status, run_id, updated_at) "
                    "VALUES (?,?,?,?, 'proposed', ?, ?)",
                    (key, kind, json.dumps(payload, sort_keys=True), sha, run_id, now()),
                )
                return "new"
            if row["payload_sha"] == sha:
                return "unchanged"
            if self._dispatched(db, key):
                return "locked"
            db.execute(
                "UPDATE proposals SET payload=?, payload_sha=?, run_id=?, updated_at=? WHERE key=?",
                (json.dumps(payload, sort_keys=True), sha, run_id, now(), key),
            )
            return "changed"

    def withdraw_missing(self, live_keys: set[str], run_id: str) -> list[str]:
        """Proposals no longer produced by the pipeline (and never dispatched) are withdrawn, not deleted."""
        gone = []
        with self.tx() as db:
            for r in db.execute("SELECT key FROM proposals WHERE status IN ('proposed','approved')").fetchall():
                if r["key"] not in live_keys and not self._dispatched(db, r["key"]):
                    db.execute(
                        "UPDATE proposals SET status='withdrawn', run_id=?, updated_at=? WHERE key=?",
                        (run_id, now(), r["key"]),
                    )
                    gone.append(r["key"])
        return gone

    @staticmethod
    def _dispatched(db: sqlite3.Connection, key: str) -> bool:
        return db.execute(
            "SELECT 1 FROM actions WHERE proposal_key=? AND status IN ('sent','sending') LIMIT 1", (key,)
        ).fetchone() is not None

    def proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM proposals" + (" WHERE status=?" if status else "") + " ORDER BY key"
        rows = self.db.execute(q, (status,) if status else ()).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def proposal(self, key: str) -> dict[str, Any] | None:
        r = self.db.execute("SELECT * FROM proposals WHERE key=?", (key,)).fetchone()
        return {**dict(r), "payload": json.loads(r["payload"])} if r else None

    def decide(self, key: str, decision: str, who: str, note: str | None = None) -> None:
        assert decision in ("approved", "rejected", "proposed")
        with self.tx() as db:
            row = db.execute("SELECT payload_sha, status FROM proposals WHERE key=?", (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            if row["status"] == "withdrawn":
                raise ValueError(f"{key} was withdrawn by a later run; nothing to decide")
            db.execute(
                "UPDATE proposals SET status=?, approved_sha=?, decided_by=?, decided_at=?, note=? WHERE key=?",
                (decision, row["payload_sha"] if decision == "approved" else None, who, now(), note, key),
            )

    def edit_payload(self, key: str, payload: dict, sha: str) -> None:
        """Human edit. Any edit drops back to 'proposed': the approval must be for the exact payload."""
        with self.tx() as db:
            if self._dispatched(db, key):
                raise ValueError(f"{key} is already dispatched; edit it in Jira")
            db.execute(
                "UPDATE proposals SET payload=?, payload_sha=?, status='proposed', approved_sha=NULL, "
                "updated_at=? WHERE key=?",
                (json.dumps(payload, sort_keys=True), sha, now(), key),
            )

    # --- delivery ledger ---------------------------------------------------
    def action(self, action_key: str) -> dict[str, Any] | None:
        r = self.db.execute("SELECT * FROM actions WHERE action_key=?", (action_key,)).fetchone()
        return dict(r) if r else None

    def actions(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM actions ORDER BY action_key")]

    def mark_action(self, action_key: str, proposal_key: str, sink: str, status: str,
                    sink_ref: str | None = None, error: str | None = None) -> None:
        with self.tx() as db:
            db.execute(
                "INSERT INTO actions (action_key, proposal_key, sink, status, sink_ref, attempts, last_error, updated_at) "
                "VALUES (?,?,?,?,?, ?, ?, ?) ON CONFLICT(action_key) DO UPDATE SET status=excluded.status, "
                "sink_ref=COALESCE(excluded.sink_ref, actions.sink_ref), last_error=excluded.last_error, "
                "attempts=actions.attempts + (excluded.status='sending'), updated_at=excluded.updated_at",
                (action_key, proposal_key, sink, status, sink_ref, int(status == "sending"), error, now()),
            )

    def filed_tickets(self) -> list[dict[str, Any]]:
        """Tickets this system has created: they join the dedupe catalogue for later runs."""
        rows = self.db.execute(
            "SELECT a.sink_ref, p.payload FROM actions a JOIN proposals p ON p.key=a.proposal_key "
            "WHERE a.sink='jira' AND a.status='sent'"
        ).fetchall()
        out = []
        for r in rows:
            p = json.loads(r["payload"])
            out.append({"key": r["sink_ref"], "proposal_key": p["key"], "title": p["jira"]["summary"],
                        "description": p["jira"]["description"], "call_ids": p["call_ids"]})
        return out
