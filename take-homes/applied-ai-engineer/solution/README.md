# June Tapes: solution

Customer-call transcripts → grounded, de-duplicated issue proposals → human approval → Jira/Slack stubs, with no duplicate writes on re-run.
Design, results and trade-offs: [WRITEUP.md](WRITEUP.md). AI-tool disclosure: [AI_USE.md](AI_USE.md). Requirement → test map: [TRACEABILITY.md](TRACEABILITY.md).

## Run it (from `take-homes/applied-ai-engineer/`)

Python 3.11+. The pipeline code uses only the standard library. The model backend needs one dependency.

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r solution/requirements.txt
```

**No API key? Everything still runs.** `solution/cache/` holds the model's output for all 140 calls, keyed by transcript hash, so `--offline` replays them exactly.

```bash
python -m solution run --offline          # 140 calls -> solution/output/review.md (the human review packet)
python -m solution eval --offline         # dev-set eval replay (calls 001-015) -> solution/output/eval-report-replay.md
python -m unittest discover -s solution/tests -t . -v   # 41 behavioural tests, fake model
python solution/scripts/mutation_check.py              # breaks 29 guarantees, checks each test goes red
```

With a model (`ANTHROPIC_API_KEY` set → Anthropic SDK. Otherwise it falls back to a logged-in `claude` CLI):

```bash
python -m solution run --refresh          # re-extract every call instead of replaying the cache
python -m solution eval --runs 5 --refresh   # reliability: does each case pass in ALL 5 fresh runs?
```

## The review → write loop

```bash
python -m solution run --offline                 # proposes; writes nothing
# read solution/output/review.md
python -m solution approve new:call-006#f0       # one ticket
python -m solution approve --kind corroborate    # batch the cheap, reversible ones
python -m solution edit new:call-008#f1 --priority P4   # an edit voids the approval; approve again
python -m solution reject new:call-0xx#f0 --reason "dup of PROJ-131"
python -m solution dispatch                      # writes only approved, unchanged payloads
python -m solution dispatch                      # safe to repeat: 0 sent, all skipped
python -m solution status                        # proposals and ledger counts
python -m solution health                        # exit 1 if stopped, failing or drifting
```

The sinks write to `stubs/outbox/{jira,slack,corroborations}.jsonl`. The stubs have no comment API, so corroborations go to a local record. Local state (SQLite ledger, run logs) lives in `solution/var/` and is gitignored. Delete that folder to start fresh.

## Layout

| file | what | model? |
|---|---|---|
| `transcript.py` | parse header, speakers, line numbers, call owner | no |
| `llm.py`, `prompts.py` | the only model access: schema-constrained, no tools, bounded retries | **yes** |
| `extract.py` | per-call extraction (cached) + evidence validation | model proposes, code validates |
| `proposals.py` | catalogue policy, cross-call clustering, Jira/Slack payloads | clustering only, validated |
| `store.py` | SQLite: call status, proposals, approvals, delivery ledger | no |
| `dispatch.py` | approved → sinks, reconcile-before-retry | no |
| `review.py` | the review packet | no |
| `obs.py` | `runs/<id>/events.jsonl`, `summary.json`, `health` | no |
| `evaluate.py` | line-anchored dev eval, repeat-run reliability | no |
| `eval/dev_expectations.json` | the dev labels re-expressed with transcript line spans | data |
