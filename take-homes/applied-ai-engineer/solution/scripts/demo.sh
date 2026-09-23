#!/usr/bin/env bash
# Review -> approve -> dispatch -> re-run -> re-dispatch, against the provided stubs.
# Run from take-homes/applied-ai-engineer/ after `python -m solution run --offline`. Resets the stub outbox.
# Every model output it needs is in solution/cache, so it also runs with no API key.
set -u
PY=${PY:-python3}
c(){ echo "\$ python -m solution $*"; $PY -m solution "$@" 2>&1 | sed "s|$PWD/||"; echo; }
rm -f stubs/outbox/*.jsonl
c status
c approve 'new:call-006#f0' 'new:call-010#f3'
c approve --kind corroborate
c edit 'new:call-008#f1' --priority P4 --title 'Typo "BetterBrak" in confirmation email footer'
c approve 'new:call-008#f1'
c dispatch
echo '$ wc -l stubs/outbox/*.jsonl'; wc -l stubs/outbox/*.jsonl; echo
c dispatch
c run --offline   # re-run after filing: filed tickets join the dedupe catalogue
c dispatch
echo '$ wc -l stubs/outbox/*.jsonl   # unchanged after a re-run and two re-dispatches'; wc -l stubs/outbox/*.jsonl; echo
c status
c health
echo '$ head -1 stubs/outbox/jira.jsonl'; head -1 stubs/outbox/jira.jsonl | $PY -m json.tool
echo '$ cat stubs/outbox/slack.jsonl | head -2'; head -2 stubs/outbox/slack.jsonl
