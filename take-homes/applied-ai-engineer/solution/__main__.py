"""CLI. Run from the exercise folder (take-homes/applied-ai-engineer/):

  python -m solution run [--only call-001,call-002] [--refresh] [--offline]
  python -m solution review                       # re-render output/review.md from state
  python -m solution approve <key>... | --kind corroborate [--by NAME]
  python -m solution reject <key> --reason "..."
  python -m solution edit <key> [--priority P3] [--title "..."]
  python -m solution dispatch                     # writes ONLY approved, unchanged payloads
  python -m solution status                       # ledger / proposal counts
  python -m solution health                       # exit 1 if stopped or drifting
  python -m solution eval [--runs 5] [--refresh]  # dev-set eval, reliability across runs
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections import Counter
from pathlib import Path

from . import dispatch as dp
from . import evaluate, llm, obs, pipeline, review
from . import proposals
from .proposals import sha, written_part
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m solution")
    ap.add_argument("--backend", choices=["api", "cli"], help="model backend (default: api if ANTHROPIC_API_KEY else cli)")
    ap.add_argument("--model")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--only", help="comma-separated call ids")
    r.add_argument("--refresh", action="store_true", help="ignore cached extractions and call the model again")
    r.add_argument("--offline", action="store_true", help="never call the model; cached extractions only")
    r.add_argument("--workers", type=int, default=4)

    sub.add_parser("review")
    a = sub.add_parser("approve")
    a.add_argument("keys", nargs="*")
    a.add_argument("--kind", choices=["new_ticket", "corroborate", "enablement"])
    a.add_argument("--by", default=getpass.getuser())
    rj = sub.add_parser("reject")
    rj.add_argument("key")
    rj.add_argument("--reason", required=True)
    rj.add_argument("--by", default=getpass.getuser())
    e = sub.add_parser("edit")
    e.add_argument("key")
    e.add_argument("--priority", choices=["P1", "P2", "P3", "P4"])
    e.add_argument("--title")
    e.add_argument("--type", choices=["Bug", "Feature"])
    sub.add_parser("dispatch")
    sub.add_parser("status")
    h = sub.add_parser("health")
    h.add_argument("--max-age-hours", type=float, default=26.0)
    ev = sub.add_parser("eval")
    ev.add_argument("--runs", type=int, default=1)
    ev.add_argument("--refresh", action="store_true")
    ev.add_argument("--offline", action="store_true")

    args = ap.parse_args(argv)
    paths = pipeline.Paths.default(ROOT)

    if args.cmd == "run":
        model = None if args.offline else llm.make(args.backend, args.model)
        only = set(args.only.split(",")) if args.only else None
        store = Store(paths.state)
        res = pipeline.run(paths, model, only=only, refresh=args.refresh, workers=args.workers, store=store)
        out = review.render(store, res.findings, paths.out)
        (paths.out / "last-run-summary.json").write_text(json.dumps(res.summary, indent=1))
        s = res.summary
        print(f"run {s['run_id']}: {s['calls']} | proposals {s['proposals']} | findings {s['findings']}")
        if s["failed_calls"]:
            print("FAILED CALLS:", json.dumps(s["failed_calls"], indent=1), file=sys.stderr)
        print(f"review packet: {out}")
        return 2 if s["failed_calls"] else 0

    store = Store(paths.state)
    try:
        return _cmd(args, paths, store)
    except (KeyError, ValueError) as e:  # unknown key, withdrawn, partly delivered...
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return 1


def _cmd(args, paths: pipeline.Paths, store: Store) -> int:
    if args.cmd == "review":
        print(review.render(store, _last_findings(paths), paths.out))
    elif args.cmd == "approve":
        keys = list(args.keys)
        if args.kind:
            keys += [p["key"] for p in store.proposals("proposed") if p["kind"] == args.kind]
        for k in keys:
            store.decide(k, "approved", args.by)
            print(f"approved {k}")
        review.render(store, _last_findings(paths), paths.out)
    elif args.cmd == "reject":
        store.decide(args.key, "rejected", args.by, note=args.reason)
        print(f"rejected {args.key}")
        review.render(store, _last_findings(paths), paths.out)
    elif args.cmd == "edit":
        p = store.proposal(args.key)
        if not p or "jira" not in p["payload"]:
            print(f"{args.key}: not an editable new-ticket proposal", file=sys.stderr)
            return 1
        pl = proposals.apply_edit(p["payload"], priority=args.priority, title=args.title, type_=args.type,
                                  by=getpass.getuser())
        store.edit_payload(args.key, pl, sha(written_part(pl)))
        print(f"edited {args.key}; it needs approval again")
        review.render(store, _last_findings(paths), paths.out)
    elif args.cmd == "dispatch":
        log = obs.RunLog(paths.runs, "dispatch")
        try:
            stats = dp.dispatch(store, dp.default_sinks(), log)
        except RuntimeError as e:  # lock held by a running `run`/`dispatch`
            log.finish(error=str(e))
            print(e, file=sys.stderr)
            return 3
        log.finish(dispatch=stats)
        print(f"dispatch: {stats}")
        review.render(store, _last_findings(paths), paths.out)
        return 1 if stats["failed"] else 0
    elif args.cmd == "status":
        print("proposals:", dict(Counter((p["kind"], p["status"]) for p in store.proposals())))
        print("actions:  ", dict(Counter((a["sink"], a["status"]) for a in store.actions())))
    elif args.cmd == "health":
        ok, msgs = obs.health(paths.runs, args.max_age_hours, store)
        print("\n".join(msgs))
        return 0 if ok else 1
    elif args.cmd == "eval":
        if args.offline and (args.runs > 1 or args.refresh):
            print("--offline replays the cache, so it can only do a single run without --refresh", file=sys.stderr)
            return 1
        model = None if args.offline else llm.make(args.backend, args.model)
        rep = evaluate.run_eval(ROOT, model, args.runs, args.refresh, paths.out,
                                name="eval-report-replay" if args.offline else "eval-report")
        print(json.dumps({k: v for k, v in rep.items() if k != "per_run"}, indent=1))
        print(f"report: {paths.out / ('eval-report-replay.md' if args.offline else 'eval-report.md')}")
    return 0


def _last_findings(paths: pipeline.Paths):
    return pipeline.last_findings(paths)


if __name__ == "__main__":
    sys.exit(main())
