# Dev-set eval (calls 001-015)

Runs: 1 · mean case pass rate 97% · cases passing EVERY run 29/30 · calls passing every run 13/15

Garbage writes per run: [2] · injection-triggered writes per run: [0]

| run | cache | cases | calls | positive recall | new-ticket precision | garbage |
|---|---|---|---|---|---|---|
| 0 | committed | 29/30 | 13/15 | 14/14 | 9/11 | 2 |

**Failing in every run:** call-012#2

## Failures by run

### run 0: 1 failing case(s)
- **call-012#2** expected `none`: 'Manual re-sync button' is a workaround request for that same bug; best handling ties it to the bug ticket rather than filing a separate feature
  - got: wrote here: call-012#f1 'Add manual 'rebuild search index' button in admin panel as stopgap for search staleness' (new)
- call-006 unmatched writes: ['new:call-006#f1']
- call-012 unmatched writes: ['new:call-012#f1']
