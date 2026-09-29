"""The committed evidence must exist and agree with itself (reviewer feedback, 2026-09-29).

A static reviewer found "ARTIFACT STATS and EVAL NUMBERS empty". These tests pin the three artifacts that answer
it, so they can't go missing or drift from the run they describe. Regenerate with:
    python solution/scripts/build_artifacts.py
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "output"
TRANSCRIPTS = Path(__file__).resolve().parents[2] / "transcripts"


class RunManifest(unittest.TestCase):
    def setUp(self):
        self.m = json.loads((OUT / "run-manifest.json").read_text())

    def test_one_row_per_transcript(self):
        ids = [r["call_id"] for r in self.m["calls"]]
        self.assertEqual(ids, sorted(p.stem for p in TRANSCRIPTS.glob("call-*.md")))
        self.assertEqual(len(ids), 140)

    def test_totals_match_rows_and_the_review_queue(self):
        rows, t = self.m["calls"], self.m["totals"]
        self.assertEqual(t["processed"] + t["skipped_internal"] + t["failed"], 140)
        self.assertEqual(t["processed"], sum(r["status"] == "extracted" for r in rows))
        self.assertEqual(t["skipped_internal"], sum(r["status"] == "skipped_internal" for r in rows))
        for k in ("findings", "actionable", "rejected_by_validator", "dismissed"):
            self.assertEqual(t[k], sum(r[k] for r in rows), k)
        props = json.loads((OUT / "proposals.json").read_text())
        for kind in ("new_ticket", "corroborate", "enablement"):
            self.assertEqual(t[f"proposals_{kind}"], sum(p["kind"] == kind for p in props), kind)
        self.assertTrue((OUT / "run-manifest.md").exists())


class EvalNumbers(unittest.TestCase):
    def test_multi_run_numbers_and_variance_are_published(self):
        e = json.loads((OUT / "eval-numbers.json").read_text())
        final = e["final"]
        self.assertEqual(final["runs"], 5)
        self.assertEqual(len(final["per_run"]), 5)
        self.assertIn("case_pass_rate_variance", final)
        self.assertIn("cases_passing_every_run", final)
        self.assertTrue(e["history"], "the pre-fix run must be kept, not only the good numbers")


class IdempotencyDiff(unittest.TestCase):
    def test_second_dispatch_and_rerun_write_nothing(self):
        d = json.loads((OUT / "idempotency-diff.json").read_text())
        steps = {s["step"]: s for s in d["steps"]}
        first = steps["dispatch #1"]
        self.assertGreater(first["outbox_total"], 0)
        for later in ("dispatch #2", "re-run", "dispatch #3"):
            self.assertEqual(steps[later]["outbox_total"], first["outbox_total"], later)
            self.assertEqual(steps[later]["outbox_sha256"], first["outbox_sha256"], later)
            self.assertEqual(steps[later]["sent_this_step"], 0, later)
        self.assertTrue((OUT / "idempotency-diff.md").exists())



class DedupProof(unittest.TestCase):
    """Reviewer: 'show one ledger/corroboration record proving a repeat report did not re-file'."""

    def test_repeat_reports_attach_instead_of_refiling(self):
        led = json.loads((OUT / "ledger-after-demo.json").read_text())
        jira = [a for a in led["actions"] if a["sink"] == "jira"]
        self.assertEqual(len(jira), 3)
        self.assertEqual(len({a["proposal_key"] for a in jira}), 3)  # one Jira write per ticket, ever
        search = next(r for r in led["jira_records"] if "search" in r["summary"].lower())
        self.assertEqual({s["call_id"] for s in search["corroborating_sources"]}, {"call-012", "call-072"})
        corr = led["corroboration_records"]
        self.assertTrue(any(r["issue_key"] == "PROJ-101" and r["call_id"] == "call-004" for r in corr))
        self.assertTrue(all(a["status"] == "sent" for a in led["actions"]))


class ObservabilitySample(unittest.TestCase):
    """Reviewer: 'per-run log counts of extractions, validations failed, and withdrawals'."""

    def test_run_summary_carries_the_counts_an_operator_needs(self):
        s = json.loads((OUT / "last-run-summary.json").read_text())
        for k in ("extracted", "skipped_internal", "failed", "validation_failed", "dismissed",
                  "proposals_new", "withdrawn"):
            self.assertIn(k, s["counts"], k)
        sample = (OUT / "observability-sample.md").read_text()
        self.assertIn("withdrawn", sample)
        self.assertIn("MISFILING RISK", sample)  # an alarm example, not only the happy path


class ReviewStats(unittest.TestCase):
    """Reviewer: 'show one card example plus review time'."""

    def test_review_effort_is_measured_from_the_packet(self):
        r = json.loads((OUT / "review-stats.json").read_text())
        props = json.loads((OUT / "proposals.json").read_text())
        self.assertEqual(r["new_ticket_cards"], sum(p["kind"] == "new_ticket" for p in props))
        self.assertEqual(r["decisions_needed"], r["new_ticket_cards"] + 2)  # + 1 batch each for corr/enable
        self.assertGreater(r["median_words_per_card"], 0)



class WriteupQuotesTheArtifacts(unittest.TestCase):
    """The write-up quotes outbox hashes; they change whenever the artifacts are rebuilt (stub timestamps)."""

    def test_hashes_in_writeup_match_the_idempotency_diff(self):
        d = json.loads((OUT / "idempotency-diff.json").read_text())
        want = {s["outbox_sha256"][:16] for s in d["steps"]}
        import re
        got = set(re.findall(r"`([0-9a-f]{16})`", (OUT.parent / "WRITEUP.md").read_text()))
        self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
