"""Behavioural tests with a fake model. Run from the exercise folder:
    python -m unittest discover -s solution/tests -t . -v
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from solution import dispatch as dp
from solution import extract as ex
from solution import pipeline, proposals
from solution.llm import FakeLLM, LLMError
from solution.obs import RunLog
from solution.store import Store
from solution.transcript import parse
from stubs import jira_stub, slack_stub

CATALOG = [
    {"key": "PROJ-101", "type": "Bug", "status": "Open", "summary": "Report times in UTC",
     "description": "Scheduled report timestamps off.", "reported_by_accounts": ["Acme"]},
    {"key": "PROJ-095", "type": "Feature", "status": "Shipped", "summary": "Bulk CSV export",
     "description": "Admin > Members > Export all.", "shipped_in": "4.3"},
]

CALLS = {
    "call-001": ("Acme", [
        ("EXTERNAL", "Dana", "The headline active members card says 280 but the teams below add up to 412."),
        ("INTERNAL", "Priya", "So the summary card disagrees with its own breakdown, let me file that."),
        ("EXTERNAL", "Dana", "Also the report timestamps are off by hours, but you already know that one."),
    ]),
    "call-002": ("Globex", [
        ("EXTERNAL", "Hank", "Our report timestamps show UTC instead of Pacific time every single morning."),
        ("EXTERNAL", "Hank", "And the active members card shows a different number than the team breakdown."),
    ]),
    "call-003": (None, [
        ("INTERNAL", "Sam", "Wouldn't it be nice to have a refresh button on the dashboard page?"),
    ]),
}


def write_transcript(root: Path, call_id: str, account: str | None, lines) -> None:
    title = f"# Call — {account} × BetterBark · Sync" if account else "# Call — BetterBark Internal · Prep"
    parts = " · ".join(f"[{r}] {n}, CSM" if r == "INTERNAL" else f"[{r}] {n}, Admin ({account})"
                       for n, r in dict((n, r) for r, n, _ in lines).items())
    body = "\n".join(f"[{r}] {n}: {t}" for r, n, t in lines)
    (root / "transcripts" / f"{call_id}.md").write_text(
        f"{title}\nDate: 2026-06-15 · Call ID: {call_id}\nParticipants: {parts}\n\n{body}\n")


def finding(line, quote, disposition="new", kind="bug", tracked=None, title="t", reason=None, severity="high"):
    return {"kind": kind, "disposition": disposition, "title": title, "description": "d", "line": line,
            "quote": quote, "context_lines": [], "tracked_key": tracked, "no_action_reason": reason,
            "related_line": None, "severity": severity, "severity_reason": "r", "match_note": "m"}


def default_responses():
    return {
        "call-001": [finding(5, "active members card says 280", title="Active members card mismatch"),
                     finding(7, "report timestamps are off by hours", "matches_tracked", tracked="PROJ-101")],
        "call-002": [finding(5, "report timestamps show UTC instead of Pacific", "matches_tracked", tracked="PROJ-101"),
                     finding(6, "active members card shows a different number", title="Members card != breakdown")],
    }


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        root = self.tmp / "ex"
        (root / "transcripts").mkdir(parents=True)
        (root / "data").mkdir()
        (root / "data" / "existing_issues.json").write_text(json.dumps(CATALOG))
        for cid, (acct, lines) in CALLS.items():
            write_transcript(root, cid, acct, lines)
        self.paths = pipeline.Paths(root=root, state=self.tmp / "var", cache=self.tmp / "cache",
                                    runs=self.tmp / "var" / "runs", out=self.tmp / "out")
        self.store = Store(self.paths.state)
        self.responses = default_responses()
        self.fail_calls: set[str] = set()
        self.cluster_answer = None
        self.llm = FakeLLM(self._respond)
        # Point the PROVIDED stubs at a temp outbox (their code is otherwise used unmodified).
        self.outbox = self.tmp / "outbox"
        self._saved = (jira_stub._OUTBOX, jira_stub._JIRA_LOG, slack_stub._OUTBOX, slack_stub._SLACK_LOG)
        jira_stub._OUTBOX = slack_stub._OUTBOX = str(self.outbox)
        jira_stub._JIRA_LOG, slack_stub._SLACK_LOG = str(self.outbox / "jira.jsonl"), str(self.outbox / "slack.jsonl")

    def tearDown(self):
        jira_stub._OUTBOX, jira_stub._JIRA_LOG, slack_stub._OUTBOX, slack_stub._SLACK_LOG = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _respond(self, tool, prompt):
        if tool == "report_groups":
            if self.cluster_answer is not None:
                return self.cluster_answer
            ids = json.loads(prompt[prompt.index("CANDIDATES:") + 11: prompt.rindex("]") + 1])
            return {"groups": [{"candidate_ids": [c["id"] for c in ids], "filed_key": None, "reason": "same card"}]}
        cid = prompt.split("Call: ")[1].split(" ")[0]
        if cid in self.fail_calls:
            raise LLMError("boom")
        return {"findings": self.responses.get(cid, [])}

    def run_pipeline(self, **kw):
        return pipeline.run(self.paths, self.llm, store=self.store, workers=1, **kw)

    def sinks(self, **override):
        s = dp.default_sinks()
        s.outbox = self.outbox
        for k, v in override.items():
            setattr(s, k, v)
        return s

    def dispatch(self, **override):
        return dp.dispatch(self.store, self.sinks(**override), RunLog(self.paths.runs, "dispatch"))

    def outbox_lines(self, name):
        p = self.outbox / name
        return p.read_text().splitlines() if p.exists() else []


class TestGrounding(Harness):
    def test_fabricated_quote_is_rejected(self):
        self.responses["call-001"] = [finding(5, "the card crashes the whole browser tab")]
        res = self.run_pipeline()
        f = next(f for f in res.findings if f.call_id == "call-001")
        self.assertFalse(f.valid)
        self.assertIn("not verbatim", f.reject_reason)
        self.assertFalse(any(p["kind"] == "new_ticket" and "call-001" in p["call_ids"] for p in res.proposals))

    def test_internal_speaker_cannot_be_evidence(self):
        self.responses["call-001"] = [finding(6, "the summary card disagrees with its own breakdown")]
        res = self.run_pipeline()
        self.assertIn("[INTERNAL]", res.findings[0].reject_reason)

    def test_unknown_tracked_key_rejected_and_shipped_is_enablement(self):
        self.responses["call-001"] = [finding(5, "active members card says 280", "matches_tracked", tracked="PROJ-999")]
        self.responses["call-002"] = [finding(5, "report timestamps show UTC", "matches_tracked", kind="feature",
                                              tracked="PROJ-095")]
        res = self.run_pipeline()
        by_call = {f.call_id: f for f in res.findings}
        self.assertFalse(by_call["call-001"].valid)
        self.assertEqual(by_call["call-002"].disposition, "shipped_feature")  # catalogue says Shipped
        self.assertEqual([p["kind"] for p in res.proposals], ["enablement"])

    def test_internal_only_call_never_reaches_model(self):
        self.run_pipeline()
        self.assertEqual(len(self.llm.calls), 3)  # call-001, call-002 extraction + one clustering call

    def test_account_already_on_tracked_issue_is_not_corroborated_again(self):
        res = self.run_pipeline()
        f = next(f for f in res.findings if f.call_id == "call-001" and f.tracked_key == "PROJ-101")
        self.assertEqual(f.no_action_reason, "already_attributed")
        corr = [p["key"] for p in res.proposals if p["kind"] == "corroborate"]
        self.assertEqual(corr, ["corr:call-002:PROJ-101"])  # Globex is new to PROJ-101; Acme isn't


class TestClustering(Harness):
    def test_same_issue_on_two_calls_is_one_ticket(self):
        res = self.run_pipeline()
        new = [p for p in res.proposals if p["kind"] == "new_ticket"]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["call_ids"], ["call-001", "call-002"])
        self.assertEqual(len(new[0]["jira"]["corroborating_sources"]), 1)

    def test_malformed_partition_falls_back_to_singletons(self):
        self.cluster_answer = {"groups": [{"candidate_ids": ["call-001#f0", "call-001#f0", "bogus"], "reason": "x"}]}
        res = self.run_pipeline()
        self.assertEqual(len([p for p in res.proposals if p["kind"] == "new_ticket"]), 2)


class TestGateAndIdempotency(Harness):
    def test_nothing_is_written_without_approval(self):
        self.run_pipeline()
        stats = self.dispatch()
        self.assertEqual(stats["sent"], 0)
        self.assertEqual(self.outbox_lines("jira.jsonl"), [])
        self.assertEqual(self.outbox_lines("slack.jsonl"), [])

    def approve_all(self):
        for p in self.store.proposals("proposed"):
            self.store.decide(p["key"], "approved", "tester")

    def test_rerun_and_redispatch_create_no_duplicates(self):
        self.run_pipeline()
        self.approve_all()
        first = self.dispatch()
        jira, slack = len(self.outbox_lines("jira.jsonl")), len(self.outbox_lines("slack.jsonl"))
        self.assertEqual(jira, 1)
        self.assertGreater(first["sent"], 0)
        res = self.run_pipeline()  # same transcripts again
        self.assertEqual(res.summary["proposals"]["new"], 0)
        second = self.dispatch()
        self.assertEqual(second["sent"], 0)
        self.assertEqual((len(self.outbox_lines("jira.jsonl")), len(self.outbox_lines("slack.jsonl"))), (jira, slack))

    def test_after_filing_later_calls_corroborate_and_edited_transcripts_do_not_refile(self):
        self.run_pipeline()
        self.approve_all()
        self.dispatch()
        filed = self.store.filed_tickets()[0]["key"]
        # 1. The same transcript edited on disk (new sha) and re-extracted with different wording.
        p = self.paths.root / "transcripts" / "call-002.md"
        p.write_text(p.read_text() + "[EXTERNAL] Hank: Thanks, talk soon.\n")
        self.responses["call-002"] = [finding(6, "active members card shows a different number",
                                              title="Dashboard headline count wrong")]
        # 2. A brand-new call reporting the same problem.
        write_transcript(self.paths.root, "call-004", "Initech",
                         [("EXTERNAL", "Joan", "The members card number is lower than the team rows added up.")])
        self.responses["call-004"] = [finding(5, "members card number is lower than the team rows")]
        self.cluster_answer = {"groups": [{"candidate_ids": ["call-002#f0", "call-004#f0"], "filed_key": filed,
                                           "reason": "same card mismatch"}]}
        res = self.run_pipeline(refresh=True)
        pending = [p for p in res.proposals if p["key"] not in {a["proposal_key"] for a in self.store.actions()}]
        self.assertEqual([(p["kind"], p["call_ids"]) for p in pending], [("corroborate", ["call-004"])])
        self.assertEqual(pending[0]["corroboration"]["issue_key"], filed)

    def test_edit_after_approval_blocks_dispatch_until_reapproved(self):
        self.run_pipeline()
        self.approve_all()
        key = next(p["key"] for p in self.store.proposals() if p["kind"] == "new_ticket")
        p = self.store.proposal(key)["payload"]
        p["jira"]["priority"] = "P4"
        self.store.edit_payload(key, p, proposals.sha(proposals.written_part(p)))
        self.dispatch()
        self.assertEqual(self.outbox_lines("jira.jsonl"), [])
        self.store.decide(key, "approved", "tester")
        self.dispatch()
        self.assertEqual(json.loads(self.outbox_lines("jira.jsonl")[0])["priority"], "P4")

    def test_payload_change_from_rerun_makes_approval_stale(self):
        self.run_pipeline()
        self.approve_all()
        self.responses["call-001"][0]["title"] = "Active members headline card undercounts"  # re-run rewords it
        self.run_pipeline(refresh=True)
        stats = self.dispatch()
        self.assertGreaterEqual(stats["stale_approval"], 1)
        self.assertEqual(self.outbox_lines("jira.jsonl"), [])


class TestPartialFailure(Harness):
    def test_one_bad_call_does_not_stop_the_others(self):
        self.fail_calls = {"call-001"}
        res = self.run_pipeline()
        self.assertEqual(res.summary["failed_calls"].keys(), {"call-001"})
        self.assertTrue(any("call-002" in p["call_ids"] for p in res.proposals))
        # Its proposals from a previous good run must not be withdrawn by the failed run.
        self.fail_calls = set()
        self.run_pipeline()
        self.fail_calls = {"call-001"}
        self.run_pipeline()
        self.assertTrue(any("call-001" in p["payload"]["call_ids"] and p["status"] == "proposed"
                            for p in self.store.proposals()))

    def test_crash_after_jira_write_reconciles_instead_of_duplicating(self):
        self.run_pipeline()
        for p in self.store.proposals("proposed"):
            self.store.decide(p["key"], "approved", "tester")

        def write_then_crash(payload):
            jira_stub.create_issue(payload)
            raise ConnectionError("socket closed before response")

        self.dispatch(jira_create=write_then_crash)
        self.assertEqual(len(self.outbox_lines("jira.jsonl")), 1)
        stats = self.dispatch()
        self.assertEqual(stats["reconciled"], 1)
        self.assertEqual(len(self.outbox_lines("jira.jsonl")), 1)  # adopted, not re-created

    def test_slack_failure_retries_only_slack(self):
        self.run_pipeline()
        for p in self.store.proposals("proposed"):
            self.store.decide(p["key"], "approved", "tester")

        def slack_down(payload):
            raise TimeoutError("slack 503")

        self.dispatch(slack_post=slack_down)
        self.assertEqual(len(self.outbox_lines("jira.jsonl")), 1)
        self.assertEqual(self.outbox_lines("slack.jsonl"), [])
        self.dispatch()
        self.assertEqual(len(self.outbox_lines("jira.jsonl")), 1)
        self.assertGreater(len(self.outbox_lines("slack.jsonl")), 0)
        jira_key = json.loads(self.outbox_lines("jira.jsonl")[0])["key"]
        self.assertTrue(any(jira_key in json.loads(l)["text"] for l in self.outbox_lines("slack.jsonl")))

    def test_concurrent_dispatch_is_refused(self):
        with self.store.exclusive("dispatch"):
            with self.assertRaises(RuntimeError):
                self.dispatch()


class TestParser(unittest.TestCase):
    def test_owner_is_the_csm(self):
        t = parse("# Call — Acme × BetterBark · Sync\nDate: 2026-06-01 · Call ID: call-009\n"
                  "Participants: [EXTERNAL] A B, VP (Acme) · [INTERNAL] Ravi Patel, Support Engineer · "
                  "[INTERNAL] Maya Chen, CSM\n\n[EXTERNAL] A: hi\n", "x.md")
        self.assertEqual(t.owner.name, "Maya Chen")
        self.assertEqual(t.account, "Acme")
        self.assertEqual(t.lines[0].no, 5)
        self.assertEqual(proposals.slack_handle("Tomás Vela"), "@tomas.vela")


if __name__ == "__main__":
    unittest.main()
