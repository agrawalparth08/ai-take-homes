# AI-tool use

## Tools and what they did

| Tool | Used for |
|---|---|
| **ChatGPT / Codex (GPT)** | An earlier planning pass: three plan documents and a partial code scaffold built around a Graphiti/Neo4j knowledge graph. **Discarded** (see below). None of that code is in this submission. |
| **Claude Code, Opus 5.5** (main session) | Reviewed the GPT plans and recommended discarding them. Wrote the replacement plan and nearly all of the code, tests, eval harness and first drafts of these docs, working to my direction and review. |
| **Claude Code subagent, Sonnet 5** | Drafted `eval/dev_expectations.json`: line spans for each dev label. It read only calls 001-015. |
| **Claude Code subagent, Fable 5** | An independent code review, on a different model from the builder. It found 16 defects and reproduced most with scripts. |
| **Claude Sonnet 5** (runtime) | The pipeline's own model: per-call extraction and cross-call grouping. |

## Wrote / designed vs delegated

This build was heavily delegated, and I'd rather say so plainly than overstate my share.

- **What I decided:** to throw away the GPT plans unless they held up against the brief (they didn't); to build exactly what the brief asks and stop there; to route the code review to a different model from the one that built it; to run Claude as the runtime model.
- **What Claude Code proposed and I accepted:** the pipeline shape; code deciding everything factual while the model only judges language; approval bound to a payload hash; the ledger with reconcile-before-retry; eval spans anchored to transcript lines.
- **What was fully delegated:** the implementation, the span key (a subagent) and the bug hunt (the Fable reviewer).
- **How it was checked:** 24 behavioural tests that call the provided stubs; 8 of the 30 eval spans spot-checked against the transcripts; the dev eval run 1 + 2 + 5 times with fresh model calls; an end-to-end demo that re-runs and re-dispatches and checks outbox line counts. I read the review packet and the demo transcript myself.

## Where the AI got it wrong

1. **The GPT plans were built for the wrong problem.** They targeted a "Company Brain" with Graphiti, Neo4j, an A/B test between retrievers, a security-scan workflow and threat models. The brief asks for a tight 2-3 hour build and says "don't gold-plate". The catalogue holds 15 issues, which fit in one prompt. The plans also missed the label details that decide the grade: an account already attributed means no action, trivial means P4, shipped means enablement, and one ticket per cross-call cluster.
2. **Opus keyed "already handled" findings by list position.** A re-extraction can reorder the list, so a finding could be silently skipped. The test suite caught it. The fix keys on (call, transcript hash, quoted line).
3. **The Opus-built code had real reliability holes** that the Fable review found. A withdrawn proposal never came back after a partial failure. A write marked `failed` but actually delivered could be re-filed. Scheduled re-runs overwrote reviewer edits. A clustering failure crashed the whole run. All are fixed, each with a regression test.
4. **The runtime model (prompt v3)** filed a workaround ask as its own feature (call-012) and a cosmetic remark the customer explicitly declined (call-006). The prompt was fixed, and a code rule added for workaround asks.

## A case where I rejected the output

- **Rejected: the whole GPT plan set, and its partial code.** Three ideas survived: exact-quote evidence checks, approval bound to a hash, and a delivery ledger. The rest was archived outside the repo, and the build restarted from a plan that maps line by line to the brief.
- **Rejected: one of the Fable reviewer's findings.** It argued that a correct corroboration quoting a line just outside the labelled span should pass. Strict spans were kept. Loosening the rule makes the grader depend on judgment, which is exactly what the brief asks us to avoid. Instead the spans are wide, and the failure report prints the finding and its line number, so a human can overrule a case in seconds.
