# AI-tool use

The PDF asks for four things here. Which tools I used and for what. Where I wrote or designed and where I delegated. Where the AI got it wrong. One concrete case where I rejected its output. Each has a section below.

## How the work flowed

| Step | Who | Time | What came out |
|---|---|---|---|
| 1. Planning | Astra (GPT, via Codex) | 20 min | Three plan documents for a "Company Brain" built on Graphiti and Neo4j |
| 2. First pass | GPT-5.6 Luna (via Codex) | 10 min | A partial scaffold: models, a store, providers and one red test. No pipeline ran. |
| 3. Review and rebuild | Claude Code (Opus 5.5), directed by me | about 1 h 25 min, much of it waiting on model runs | The GPT plans discarded; a new plan; the pipeline, eval, tests and a full 140-call run |
| 4. Independent review | Fable 5 subagent | inside step 3 | 16 defects, most with repro scripts, all fixed with regression tests |
| 5. TDD pass | Claude Code, at my request | inside step 3 | Requirement traceability, mutation evidence (29 of 29 caught), gap tests written red first |
| My own time | me | about 1 h | Setting direction, reviewing plans, flows, outputs and these docs |

Total: about 2 h 55 min.

## Tools and what they did

| Tool | Used for |
|---|---|
| Astra and GPT-5.6 Luna (Codex) | Steps 1 and 2 above. **Nothing from them ships.** The scaffold is archived outside the repo. |
| Claude Code, Opus 5.5 | Most of the code, tests, eval harness and first drafts of these docs, working to my instructions |
| Claude Code subagent, Sonnet 5 | Drafted `eval/dev_expectations.json` (a line span for each dev label). It read only calls 001-015. |
| Claude Code subagent, Fable 5 | Independent code review. I keep a standing rule that a different model reviews the builder's work. |
| Claude Sonnet 5 (runtime) | The pipeline's own model: one extraction per call, one grouping call across calls |

## What I decided, and what I delegated

**My decisions:**

- I ran the GPT planning and first pass, then brought both to Claude Code with one instruction: check them against the PDF, throw them out if they don't fit, and build only what the submission needs.
- I held the scope to the brief. No graph, no agent framework, no extras.
- I chose Claude as the runtime model.
- I sent the code to a second model for review, so the builder did not grade its own work.
- Mid-build, I stopped feature work and required proper TDD, tied to the PDF's evaluation criteria and my own review. That produced `TRACEABILITY.md`, the mutation check and the red-first gap tests.
- I reviewed the flows and the two red gap tests before they were built: a copy-paste approve command on each card, and a code-side flag for instruction-like text.
- I set the readability bar for the docs (ASD-STE100 style, grade 8 or below).

**Proposed by Claude Code, reviewed and kept by me:** the pipeline shape; code deciding every fact while the model only judges language; approval bound to a payload hash; the ledger with an outbox check before any retry; eval spans anchored to transcript lines.

**Delegated:** the implementation, the eval span key and the bug hunt.

**How it was checked:**

- 41 behavioural tests that call the provided stubs
- a mutation check that breaks each of 29 guarantees and confirms its test fails
- 8 of the 30 eval spans spot-checked against the transcripts
- the dev eval run 1 + 2 + 5 times with fresh model calls
- a demo that re-runs and re-dispatches and checks the outbox line counts

## Where the AI got it wrong

1. **The GPT plans solved the wrong problem.** They built toward a "Company Brain" with Graphiti, Neo4j, an A/B test of retrievers, security scans and threat models. The brief asks for a 2-3 hour build and says "don't gold-plate". The catalogue has 15 issues, and they fit in one prompt. The plans also missed the label details that decide the grade: already attributed means no action, trivial means P4, shipped means enablement, and one ticket per cross-call cluster.
2. **Claude keyed filed findings by list position.** A re-extraction can reorder the list, so a finding could be skipped. A test caught it. The key is now (call, transcript hash, quoted line).
3. **Claude's first version had reliability holes.** The Fable review found them:
   - a withdrawn card never came back after a partial failure
   - a write marked `failed` but actually delivered could be filed again
   - a scheduled re-run overwrote a reviewer's edit
   - a failed grouping call crashed the whole run
4. **Claude's first tests were not test-first.** Some were also weak: the first mutation run caught 16 of 20. One real gap had no test at all (re-running after filing). My TDD request surfaced this. It is fixed and logged in `TDD_LOG.md`.
5. **The runtime model on prompt v3** filed a workaround ask as its own feature (call-012). It also filed a cosmetic remark that the customer declined (call-006). The prompt changed, and a code rule now folds workaround asks into their bug.

## Output I rejected

- **The GPT plan set and scaffold.** Three ideas survived: exact-quote evidence checks, approval bound to a hash, and a delivery ledger. The rest was archived. The build restarted from a plan that maps line by line to the brief.
- **One Fable review finding.** It argued that a correct write quoting a line just outside the labelled span should pass. The spans stay strict: a looser rule would make the grader a judgment call, and the brief asks for a rule a second engineer would agree with. The spans are wide, and each failure prints the finding and its line number, so a person can overrule a case quickly.

## A late look at other submissions

After the submission work above was finished, I asked a subagent to read the other June Tapes solutions that are public on GitHub (one PR on the upstream repo, four forks). The goal was to see how other people use AI-driven development on the same brief. No code, prompt or design came from them. The only changes after that look: I committed the post-demo stub outbox as evidence, and added two sentences to the write-up about behaviour the pipeline already had (per-transcript cache checkpointing, and grouping only after all extraction is in).

