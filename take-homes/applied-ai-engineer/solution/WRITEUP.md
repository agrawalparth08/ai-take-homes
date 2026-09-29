# June Tapes: write-up

## Results at a glance

Each number below comes from a committed file. `python solution/scripts/build_artifacts.py` rebuilds the files from the committed model outputs, with no API key. `solution/tests/test_artifacts.py` fails if a file goes missing or stops agreeing with the run.

**Full 140-call run** ([output/run-manifest.md](output/run-manifest.md): one row per transcript)

| transcripts | processed | skipped (internal-only) | failed | findings | actionable | rejected by evidence check | dismissed with reason | new tickets | grouped across calls | corroborations | enablement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 140 | 134 | 6 | 0 | 388 | 80 | 0 | 308 | 41 | 6 | 21 | 7 |

The run logged one warning. The grouping model left out one candidate (`call-115#f0`), and code kept it as its own card.

**Dev eval, calls 001-015** ([output/eval-numbers.json](output/eval-numbers.json), [output/eval-report.md](output/eval-report.md))

| | runs | case pass rate per run | mean | variance | cases passing every run | calls passing every run | junk writes | writes from injections |
|---|---|---|---|---|---|---|---|---|
| Prompt v4 (final), fresh model calls each run | 5 | 30/30, 30/30, 30/30, 30/30, 30/30 | 1.00 | 0.00 | 30/30 | 15/15 | 0 | 0 |
| Prompt v4, first check (1 cached + 2 fresh) | 3 | 30/30, 30/30, 30/30 | 1.00 | 0.00 | 30/30 | 15/15 | 0 | 0 |
| Prompt v3 (before the fix) | 1 | 29/30 | 0.97 | n/a | n/a | 13/15 | 2 | 0 |
| File nothing (floor) | n/a | 16/30 | | | | 3/15 | 0 | 0 |

In every final run, positive recall was 14/14 and new-ticket precision was 9/9. I tuned the prompt on these 15 calls, so read the dev numbers as an upper bound. The holdout has no labels here.

**Idempotency** ([output/idempotency-diff.md](output/idempotency-diff.md))

| step | writes sent | outbox records (jira / slack / corroborations) | outbox sha256 |
|---|---|---|---|
| run | 0 | 0 / 0 / 0 | `72cb15c431e34bf3` |
| dispatch #1 (3 tickets + 21 corroborations approved) | 50 | 3 / 26 / 21 | `2ebaa7d57ab7a5e2` |
| dispatch #2 | 0 | 3 / 26 / 21 | `2ebaa7d57ab7a5e2` |
| re-run of all 140 calls | 0 | 3 / 26 / 21 | `2ebaa7d57ab7a5e2` |
| dispatch #3 | 0 | 3 / 26 / 21 | `2ebaa7d57ab7a5e2` |

The hash stays the same after the first dispatch, so later steps appended no bytes to the outbox. The re-run produced 0 new proposals and left 45 unchanged. The stub outbox after the demo is also committed, in [output/outbox-after-demo/](output/outbox-after-demo/).

**Dedup: a repeat report attaches, it doesn't re-file** ([output/ledger-after-demo.json](output/ledger-after-demo.json))

- Three customers reported the search-lag bug (calls 006, 012 and 072). The ledger has one Jira write for it: `new:call-006#f0:jira → PROJ-1001`, 1 attempt. That Jira record lists `call-012` and `call-072` under `corroborating_sources`.
- call-004 reported the tracked timezone bug. The ledger has `corr:call-004:PROJ-101:corroboration`, sent once. The corroboration record holds the quote and a link to `transcripts/call-004.md#L26`, and no new ticket exists for it.
- All 50 ledger rows are `sent` with 1 attempt each, and there are exactly 3 Jira rows for 3 tickets.

## What I built

A batch CLI that turns the 140 transcripts into a review queue. Nothing reaches Jira or Slack until a person approves the exact payload. Re-runs are safe.

```
parse (code) → extract (model, 1 call per transcript, cached) → validate evidence (code)
→ catalogue policy (code) → group same issue across calls (model, output checked by code)
→ review packet → approve → dispatch through a delivery ledger (code) → Jira / Slack / corroboration stubs
```

Main decisions:

- **One model call per transcript, not an agent.** The model reads the whole call once and returns every product topic the customer raised, including the ones it dismisses, with a reason for each. The dismissed list is the audit trail: a reviewer can see what was considered and why it wasn't filed.
- **The model never writes.** It has no tools. It returns JSON against a schema. Everything that touches a sink is deterministic code behind an approval.
- **Stable identity from the input, not the model.** Proposal keys come from the call id and the finding. Approvals are bound to a hash of exactly what gets written. Model output is cached by transcript hash + prompt version + catalogue hash, so the same input replays the same output.
- **SQLite as the system of record.** The stubs don't de-duplicate. The ledger does.

## Where AI is, and isn't

| Decision | Who | Why |
|---|---|---|
| Header, speakers, call owner, internal-only calls | code | Exact. Internal-only calls never reach the model (6 of 140). |
| Is this a genuine, actionable, first-hand customer issue? Bug or feature? Which tracked issue is it? | model | Language judgment. Rules can't separate a retracted gripe from a real bug. |
| Is the evidence real? | code | The quote must appear word for word on a cited `[EXTERNAL]` line. The transcript is the source of truth, and this check blocks invented or staff-spoken evidence. |
| Does the tracked issue exist? Is it shipped? Is this account already on it? | code | These are facts in the catalogue. The model's "matches" is overridden to "enablement" when the catalogue says Shipped, and to "no action" when the account is already attributed (call-001). |
| Same problem on two calls? | model, validated | Semantic. Code rejects any grouping that isn't a clean partition and falls back to one card each: a reviewer can merge two cards, but can't see an issue a bad merge swallowed. |
| Severity | model proposes, with a reason | Shown on the card. P4 for trivial defects. The customer's "P0!" framing is ignored by instruction. |
| Workaround asks ("give us a re-sync button") | model links, code enforces | Folded into the bug they work around (call-012), never a separate ticket. |
| Every write | code, after approval | Each card has a copy-paste approve command. Code flags instruction-like text in the evidence, whatever the model decided. |

**Where the rules live.** Each rule sits in one module, with a fixed number:

| Module | Rule | Value |
|---|---|---|
| `extract.validate` | A quote is evidence only if it is at least 4 words and appears word for word (after whitespace and quote-mark normalization) on the cited `[EXTERNAL]` line | 4 words minimum |
| `extract.validate` | Context lines kept per finding | at most 4 |
| `proposals.apply_policy` | An account already listed on the tracked issue means no action | exact account-name match |
| `proposals.PRIORITY` | Severity to priority | critical P1, high P2, medium P3, low P4 |
| `proposals.instruction_like` | Flag evidence that addresses an automated system | regex, 6 phrase patterns |
| `llm._retry` | Model call retries | 3 attempts, 2 s then 4 s backoff; 180 s API timeout, 300 s CLI timeout |
| `dispatch._once` | Rows in `sending` or `failed` are checked against the sink before any resend | every retry |
| `obs.health` | Alarms | no full run for 26 h; evidence-check rejects above 15%; findings per call outside 0.5x to 1.5x of the last 10 runs; 10+ calls with 0 findings |

Prompt injection (call-005, call-011) is handled twice. The prompt treats the transcript as data. Even if the model obeyed an injected instruction, the result could only become a card in the review queue, never a write.

## Hardest engineering problem: exactly-once effects on sinks that aren't idempotent

The stubs append whatever you send. Three things make "run it twice, get nothing new" hard:

1. **Crash windows.** Each write goes `sending` → sink call → `sent` in the ledger, and the `sending` row is committed before the call. If the process dies after the sink wrote but before `sent` was recorded, the next dispatch does not resend blindly. It searches the sink's own record for our idempotency key and adopts the record if it's there. In production that's a Jira JQL search on a label and Slack message metadata. Any row that ever reached `sending` or `failed` counts as possibly delivered: it's never withdrawn, rewritten or un-approved.
2. **Model drift between runs.** A re-extraction can reword or reorder findings. Evidence that's already filed is "settled" by (call, transcript hash, quoted line), not by list position. Tickets we've filed join the dedupe catalogue, so a later report of the same issue becomes a corroboration of our own ticket.
3. **Partial failure.** Each transcript runs in isolation, and one failure is logged and marked while the rest proceed. Each extraction is written to the cache (atomically) the moment it finishes, so a long run that dies resumes from the next unprocessed transcript. Extraction runs in parallel, but cross-call grouping runs once, after every extraction is in, so its input doesn't depend on which call finished first. A `--refresh` whose model call fails falls back to the last good extraction. If clustering fails, the run degrades to one card per candidate and skips all withdrawals. Proposals touching a failed call are never withdrawn. Jira and Slack are separate ledger rows, so a Slack outage retries only Slack.

A Fable-model review of my first version found 16 defects here, most with repro scripts. Examples: a withdrawn proposal never came back, a `failed` write that had actually landed could be re-filed, and a scheduled re-run silently overwrote a reviewer's edit. All are fixed, each with a regression test.

Two further rules. Reviewer edits win over regenerated payloads, and an edit voids the approval. A rejected proposal reopens if a *new* call reports the same issue. `run` and `dispatch` share a file lock.

## The human gate

What the reviewer sees is in [output/example-card.md](output/example-card.md). That file is one real card, copied from the queue. Trimmed, it looks like this:

> **25. Bug · P3 · Search index lags ~10 minutes after team rename or member move**
> `new:call-006#f0` · awaiting review · 3 call(s), 3 account(s): Copperline Energy, Gable Group, Harborline Media
> "...After we rename a team or move a member, search keeps returning the old state for about ten minutes." (Harborline Media, [call-006 L24](../transcripts/call-006.md#L24)), plus the quote and 4 context lines from each of the other two calls
> **Why new:** distinct from PROJ-131 (new invites not searchable until the next day's index build): this is a ~10-minute lag on renames and moves.
> **Priority P3 (medium):** reproducible and creates support tickets, but self-corrects in ~10 minutes, with a known workaround.
> **Slack:** @tomas.vela, @sam.oduya, @maya.chen · **Approve:** `python -m solution approve 'new:call-006#f0'`

**Review effort** ([output/review-stats.json](output/review-stats.json)): the full run needs 43 decisions. That is one approve for each of the 41 new-ticket cards, plus one batch approve for the 21 corroborations and one for the 7 enablement nudges. A card has a median of 312 visible words (at most 965), and the Jira payload is folded away. I spent about 1 h in total on direction and review, including reading this queue. I did not time each card, so I don't claim a per-card median.

## The eval

`eval/dev_expectations.json` restates each of the 30 dev labels with the **transcript line span** where it's discussed, so a second engineer can check the key by opening the file. The pass/fail rules are mechanical (full text in `evaluate.py`):

- `file-new`: a new ticket of the right type quotes a line inside the span. `file-new-low` also needs P4.
- `corroborate`: a corroboration to that exact issue quotes a line inside the span. `cluster:<case>` needs the same ticket as the referenced case.
- `none`: no unmatched write quotes a line inside the span.
- A call passes only if all its cases pass **and** it produced no unmatched write (no garbage).

**Results (calls 001-015, `claude-sonnet-5`):**

| | cases | calls | garbage writes | injection writes |
|---|---|---|---|---|
| File nothing (floor) | 16/30 | 3/15 | 0 | 0 |
| Prompt v3, 1 run | 29/30 | 13/15 | 2 | 0 |
| Prompt v4, 3 runs (1 cached + 2 fresh) | 30/30 every run | 15/15 every run | 0 | 0 |
| Prompt v4, 5 fresh runs | 30/30 every run (pass^5) | 15/15 every run | 0 | 0 |

The v3 failures were a workaround ask filed as its own feature (call-012) and a font gripe the customer explicitly declined (call-006). I changed the prompt, and added the code rule for linked workaround asks. **Those changes were tuned on the dev set, so 30/30 is optimistic.**

**Reliability across runs:** `eval --runs N --refresh` calls the model fresh each time. It reports the mean pass rate and, more usefully, how many cases passed in *every* run (pass^N), plus a list of flaky cases. A case that passes once but not every time is a bug to fix, not noise to average away.

**What the eval catches:** missed issues, wrong target, a known issue filed as new, a split cluster, garbage filings, writes triggered by injections, a wrong type, and a trivial bug not given P4.
**What slips through:** ticket wording and severity (except P4) aren't graded. Only 15 calls are labelled. A correct write that quotes a line just outside the span counts as a miss. I kept the spans strict on purpose and wrote them generously. Failing cases print the stage that lost them: never extracted, dismissed (with reason), rejected by the validator, matched to the wrong issue, or merged. That's how you tell a genuine miss from a bad key.

**Holdout (125 calls, unlabelled):** 120 external calls produced 0 validator rejects and 0 failures. Across all 140: 41 new tickets (6 grouped across 2 to 4 calls), 21 corroborations, 7 shipped-feature nudges. On the holdout I expect lower precision than on dev, mainly from borderline feature asks and severity calibration. Recall of clear bugs should hold. I haven't tuned anything against the holdout.

## Observability

Every run writes `var/runs/<id>/events.jsonl` (one event per call per stage, with the model, prompt version, tokens, latency and cache hit) and `summary.json`. `python -m solution health` exits 1 in these cases:

- **Silent stop:** no full run in 26h; zero transcripts seen; 10+ calls with zero findings.
- **Silent mis-filing:** validator rejects above 15%, meaning the model has started quoting loosely or attributing staff lines to customers; findings-per-call drifting outside the recent band; degraded clustering; stale-extraction fallbacks.
- **Silent non-delivery:** writes stuck in `sending`/`failed`; approvals never dispatched.

Every `summary.json` also has a flat `counts` block: seen, extracted, skipped, failed, validation_failed, dismissed, new and changed proposals, and withdrawn. `health` prints it on every run, healthy or not, so a sudden change is visible between runs. [output/observability-sample.md](output/observability-sample.md) shows the full run's counts and `health` output, and what each alarm prints.

I've seen it work: an offline re-run after filing couldn't cluster and `health` reported `DEGRADED` instead of passing.

## Validation

49 tests: 42 behavioural tests on a fake model, plus 7 that pin the committed evidence files. The behavioural tests are traced to each PDF requirement in [TRACEABILITY.md](TRACEABILITY.md). A mutation check (`scripts/mutation_check.py`) breaks each of 29 guarantees in a temp copy and confirms its test fails; the first build was not test-first, and [TDD_LOG.md](TDD_LOG.md) records how that was made good. The tests cover the gate, re-runs, crash-after-write, Slack failure, concurrent dispatch, partial failure, stale approval, human edits, revive/reopen, invented and staff-spoken quotes, and the fold rules. The dev eval ran 1 + 2 + 5 times with fresh model calls. The full 140-call run is committed. `scripts/demo.sh` (transcript in `output/demo-session.txt`) approves 3 tickets (one after a reviewer edit) and 21 corroborations, dispatches 50 writes, re-runs, dispatches twice more, and the outbox stays at 50. The resulting stub outbox is committed in `output/outbox-after-demo/`. Everything replays offline from `solution/cache/`.

## Prototype vs production

Production would run on a scheduler (cron, or Airflow if it grows) with Postgres for the ledger, pull from the Gong API instead of files, and use Jira's comment API for corroborations. The idempotency key would go in as a Jira label and in Slack message metadata. The review would happen in Slack or a small web page with approve buttons, not a markdown file. Cost here: about 20k input and 4k output tokens per call on Sonnet 5, roughly $0.08 per transcript at list price, with a median of 48 s per call.

## Another day, and what I left out

Next: calibrate severity against a labelled sample; add a slice of the holdout for hand-labelling to measure real precision; let reviewers merge or split clusters from the CLI; move the review packet to Slack buttons.
Left out on purpose: a knowledge graph or vector store (15 tracked issues fit in the prompt), an agent framework (one structured call per transcript is enough and is easier to test), and automatic filing of anything.

Time: about 2 h 55 min in total. That is 20 min of planning with Astra and 10 min of a first pass with Luna (both GPT, both discarded), about 1 h 25 min in the Claude Code session (much of it waiting on model runs), and about 1 h of my own direction and review. AI use is disclosed in [AI_USE.md](AI_USE.md).
