# TDD log

The first build (commits `b34e51f`, `7fb1ca7`) did **not** follow strict red-green: tests were written alongside the code, and the review fixes got their tests right after each fix. This log recovers red evidence for that work and records everything after it test-first.

## 1. Red evidence for existing guarantees (mutation check)

`python solution/scripts/mutation_check.py` copies the code to a temp folder, breaks one guarantee at a time, and runs the test that claims to protect it. A test that stays green under its mutation is vacuous.

**First run (2026-09-23): 16/20 caught.** It exposed three problems:

| Mutation | Result | Cause | Action |
|---|---|---|---|
| dispatch visits every proposal, not just approved | survived | the approval-hash check still blocks the write (two guards) | recorded as GUARDED (defence in depth) |
| drop the payload-hash check | survived | the named edit test also resets status, so dispatch skips it anyway | pointed at `test_payload_change_from_rerun_makes_approval_stale`, which goes red |
| ignore settled (already filed) evidence | **survived** | **no test covered a reordered re-extraction after filing** | new test `test_reordered_reextraction_after_filing_proposes_nothing_new`: red under the mutation, green on the code |
| withdrawn proposals revive | skipped | the mutation anchor matched twice | anchor made unique |

**Second run: 20/20** (19 red, 1 held by a second guard).

## 2. Gap tests (TRACEABILITY.md T1-T5), written before any code change

`python -m unittest solution.tests.test_gaps -v`, first run 2026-09-23:

| Test | First run | Meaning |
|---|---|---|
| T1 Jira contract (fields, linked snippet), Slack to the CSM | green | behaviour already existed; needs mutation evidence |
| T2 corroborations batched, rejects visible | green | as above |
| **T2 each card has a copy-paste `approve '<key>'` line** | **RED** | new behaviour: the header had one generic command, so the reviewer had to build it |
| T3 an embedded instruction produces no proposal | green | |
| **T3 a fooled model can't write, and code flags instruction-like evidence on the card** | **RED** (on the flag; the no-write part holds) | new behaviour: a reviewer skimming 41 cards could approve a planted "P0" |
| T4 grader rules, table-driven (9 rows) + call-level garbage + cluster ref + one-prediction-one-case + diagnosis | green | the grader matched its docstring |
| T5 health: clean, 6 failure modes, `--only` masking, stuck delivery, event fields | green | |

**Waiting for review before implementing the two RED tests.**
