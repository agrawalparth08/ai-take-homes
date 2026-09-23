"""Red evidence for the test suite: break each guarantee on purpose and check the named test fails.

Works on a throwaway copy of the exercise folder, so the real code is never touched.
Run from take-homes/applied-ai-engineer/:  python solution/scripts/mutation_check.py
Exit 0 only if every mutation is caught (turns its test red) and the unmutated suite is green.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (guarantee, file, original text, broken text, test that must go red)
# GUARDED: mutations that are expected to survive because a second, independent guard still holds.
GUARDED = {"only approved proposals are dispatched"}  # the approval-hash check also blocks it
MUTATIONS = [
    ("evidence must be spoken by the customer", "extract.py",
     'if line.role != "EXTERNAL":', 'if False:', "test_internal_speaker_cannot_be_evidence"),
    ("quote must be verbatim", "extract.py",
     "if q not in normalize(line.text):", "if False:", "test_fabricated_quote_is_rejected"),
    ("catalogue decides 'shipped'", "extract.py",
     'if shipped and f.disposition == "matches_tracked":', "if False:",
     "test_unknown_tracked_key_rejected_and_shipped_is_enablement"),
    ("internal-only calls never reach the model", "pipeline.py",
     "if not t.has_external:", "if False:", "test_internal_only_call_never_reaches_model"),
    ("already-attributed account is not corroborated again", "proposals.py",
     "if t.account and t.account in issue.get", "if False and t.account in issue.get",
     "test_account_already_on_tracked_issue_is_not_corroborated_again"),
    ("only approved proposals are dispatched", "dispatch.py",
     'store.proposals("approved")', "store.proposals()", "test_nothing_is_written_without_approval"),
    ("approval bound to the exact payload", "dispatch.py",
     'if sha(written_part(payload)) != p["approved_sha"]:', "if False:",
     "test_payload_change_from_rerun_makes_approval_stale"),
    ("sent actions are never re-sent", "dispatch.py",
     'if row and row["status"] == "sent":', "if False:", "test_rerun_and_redispatch_create_no_duplicates"),
    ("reconcile from the outbox before retrying", "dispatch.py",
     'found = sinks.find(sink, body["idempotency_key"])', "found = None",
     "test_crash_after_jira_write_reconciles_instead_of_duplicating"),
    ("a failed write counts as possibly delivered", "store.py",
     '"SELECT 1 FROM actions WHERE proposal_key=? LIMIT 1"',
     "\"SELECT 1 FROM actions WHERE proposal_key=? AND status='sent' LIMIT 1\"",
     "test_failed_write_that_may_have_landed_is_never_withdrawn_or_refiled"),
    ("human edits survive re-runs", "store.py",
     'if row["human_edited"]:', "if False:", "test_scheduled_rerun_does_not_overwrite_a_human_edit"),
    ("withdrawn proposals revive", "store.py",
     'if row["status"] == "withdrawn":\n                db.execute(', "if False:\n                db.execute(", "test_withdrawn_proposal_comes_back_when_produced_again"),
    ("rejected proposals reopen on new evidence", "store.py",
     'if status == "rejected" and set(payload["call_ids"]) - old_calls:', "if False:",
     "test_rejected_proposal_reopens_when_a_new_call_reports_it"),
    ("one bad call doesn't stop the rest", "pipeline.py",
     'return t, None, f"{type(err).__name__}: {err}"', "raise", "test_one_bad_call_does_not_stop_the_others"),
    ("refresh failure falls back to the cache", "extract.py",
     "            if prev is None:\n                raise", "            raise",
     "test_refresh_failure_keeps_previous_extraction_and_approval"),
    ("clustering failure degrades", "pipeline.py",
     "except Exception as err:  # clustering down", "except ZeroDivisionError as err:  # clustering down",
     "test_clustering_failure_degrades_instead_of_crashing"),
    ("filed evidence is settled", "pipeline.py",
     "(f.call_id, ts[f.call_id].sha256[:12], f.line) not in settled", "True",
     "test_reordered_reextraction_after_filing_proposes_nothing_new"),
    ("same issue on two calls is one ticket", "pipeline.py",
     "groups = pr.cluster(cands, filed, llm, cache, log)",
     'groups = [pr.Group([f], None, "x") for f in cands]', "test_same_issue_on_two_calls_is_one_ticket"),
    ("dispatch is single-writer", "store.py",
     "fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)", "pass", "test_concurrent_dispatch_is_refused"),
    ("Slack retries without re-filing Jira", "dispatch.py",
     'if "jira" in payload:', 'if "jira" in payload and False:', "test_slack_failure_retries_only_slack"),
    # gap tests (TRACEABILITY.md T1-T5)
    ("Slack goes to the CSM", "transcript.py",
     'if "CSM" in p.title:', "if False:", "test_slack_goes_to_the_csm_not_the_support_engineer"),
    ("Jira body carries the linked snippet", "proposals.py",
     "{e['account']}, {e['call_id']} {e['date']}, {e['link']})", "{e['account']})",
     "test_jira_payload_has_required_fields_and_linked_snippet"),
    ("each card has its approve command", "review.py",
     "L.append(f\"- **Approve:** `python -m solution approve '{p['key']}'`\")", "pass",
     "test_each_new_ticket_card_is_self_contained_and_actionable"),
    ("code flags instruction-like evidence", "proposals.py",
     "flags = instruction_like(", "flags = [] and instruction_like(", "test_fooled_model_still_cannot_write_and_card_is_flagged"),
    ("grader checks the span", "evaluate.py",
     'return p.call_id == c["call_id"] and any(lo <= n <= hi for n in p.lines)',
     'return p.call_id == c["call_id"]', "test_rules"),
    ("grader fails a call with garbage", "evaluate.py",
     'and not extra, "extra_writes": extra}', ', "extra_writes": extra}',
     "test_unmatched_write_fails_the_call_even_if_cases_pass"),
    ("health flags validator reject spikes", "obs.py",
     "if reject_rate > 0.15:", "if False:", "test_each_failure_mode_is_flagged"),
    ("health ignores --only runs", "obs.py",
     ' and s.get("scope", "full") == "full"', "", "test_debug_only_run_does_not_mask_a_stale_full_run"),
    ("health flags stuck deliveries", "obs.py",
     'if a["status"] in ("sending", "failed")]', "if False]", "test_stuck_delivery_is_flagged"),
]


def run_tests(where: Path, name: str | None = None) -> bool:
    cmd = [sys.executable, "-W", "ignore", "-m", "unittest", "discover", "-s", "solution/tests", "-t", ".",
           "-k", name] if name else [sys.executable, "-W", "ignore", "-m", "unittest", "discover", "-s",
                                     "solution/tests", "-t", "."]
    return subprocess.run(cmd, cwd=where, capture_output=True).returncode == 0


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mutation-"))
    try:
        for part in ("solution", "stubs", "data"):
            shutil.copytree(ROOT / part, tmp / part, ignore=shutil.ignore_patterns("var", "cache", "output",
                                                                                    "__pycache__", ".venv"))
        if not run_tests(tmp):
            print("baseline suite is not green; fix that first")
            return 1
        caught = 0
        for guarantee, fname, old, new, test in MUTATIONS:
            path = tmp / "solution" / fname
            src = path.read_text()
            if src.count(old) != 1:
                print(f"SKIP  {guarantee}: mutation anchor not found exactly once in {fname}")
                continue
            path.write_text(src.replace(old, new))
            red = not run_tests(tmp, test)
            path.write_text(src)
            guarded = guarantee in GUARDED
            caught += red or guarded
            label = "RED " if red else ("GUARDED" if guarded else "MISS")
            print(f"{label:<7} {guarantee:<52} {test}")
        print(f"\n{caught}/{len(MUTATIONS)} mutations caught (or held by a second guard)")
        return 0 if caught == len(MUTATIONS) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
