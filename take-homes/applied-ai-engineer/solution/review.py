"""The human gate: a review packet a CSM lead can clear in minutes.

Design choices for speed:
- New tickets (the expensive, irreversible action) get one full card each, with the customer's own
  words, surrounding lines, the closest existing issue and why it's NOT that, and the exact
  Jira/Slack text that will be sent.
- Corroborations and enablement nudges (cheap, reversible) are one table row each and can be
  approved as a batch.
- Everything the system decided NOT to file is listed with its reason, so a reviewer can catch a
  miss without reading 140 transcripts.
"""

from __future__ import annotations

import json
from pathlib import Path

from .extract import Finding
from .proposals import sha, written_part
from .store import Store

LINK_PREFIX = "../../"  # output/review.md -> exercise root


def _src(link: str) -> str:
    call, line = link.split("/")[-1].split(".md#")
    return f"[{call} {line}]({LINK_PREFIX}{link})"


def render(store: Store, findings: list[Finding], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    props = [p for p in store.proposals() if p["status"] in ("proposed", "approved")]
    sent = {a["proposal_key"] for a in store.actions() if a["status"] == "sent"}
    pending = [p for p in props if p["key"] not in sent]
    new = [p for p in pending if p["kind"] == "new_ticket"]
    corr = [p for p in pending if p["kind"] == "corroborate"]
    enable = [p for p in pending if p["kind"] == "enablement"]
    rejected = [f for f in findings if not f.valid]
    dismissed = [f for f in findings if f.valid and f.disposition == "no_action"]

    L: list[str] = ["# June Tapes review queue", ""]
    L.append(f"**{len(new)} new tickets** to review · **{len(corr)} corroborations** · "
             f"**{len(enable)} enablement nudges** · {len(dismissed)} dismissed · "
             f"**{len(rejected)} need a look** (failed evidence checks)")
    L += ["", "Nothing below has been written anywhere. Approve with "
          "`python -m solution approve <key>`, then `python -m solution dispatch`. "
          "Batch: `python -m solution approve --kind corroborate`.", ""]

    L += ["## New tickets", ""]
    for i, p in enumerate(sorted(new, key=lambda p: (p["payload"]["jira"]["priority"], p["key"])), 1):
        L += _card(i, p)
    if not new:
        L += ["_None._", ""]

    L += ["## Corroborations (attach to an existing issue, no new ticket)", "",
          "| key | issue | account / evidence | why it matches | state |", "|---|---|---|---|---|"]
    for p in corr:
        r, e = p["payload"]["review"], p["payload"]["review"]["evidence"][0]
        L.append(f"| `{p['key']}` | {r['target']}: {r['target_summary']} | {e['account']}: \"{_esc(e['quote'])}\" "
                 f"{_src(e['link'])} | {_esc(r['match_note'])} | {_state(p)} |")
    L += ["", "## Enablement (already shipped: tell the customer, don't file)", "",
          "| key | shipped feature | customer ask | state |", "|---|---|---|---|"]
    for p in enable:
        r, e = p["payload"]["review"], p["payload"]["review"]["evidence"][0]
        L.append(f"| `{p['key']}` | {r['target']}: {r['target_summary']} | \"{_esc(e['quote'])}\" {_src(e['link'])} | {_state(p)} |")

    L += ["", "## Need a look: model proposed an issue but the evidence check failed", "",
          "These were NOT turned into proposals. Usually a paraphrased quote or a line spoken by our own staff.", "",
          "| finding | title | why rejected |", "|---|---|---|"]
    for f in rejected:
        L.append(f"| {_src(f'transcripts/{f.call_id}.md#L{f.line}')} | {_esc(f.title)} | {_esc(f.reject_reason or '')} |")
    L += ["", "<details><summary>Dismissed by triage (" + str(len(dismissed)) + "): not filed, with reason</summary>",
          "", "| finding | topic | reason |", "|---|---|---|"]
    for f in dismissed:
        L.append(f"| {_src(f'transcripts/{f.call_id}.md#L{f.line}')} | {_esc(f.title)} | "
                 f"{f.no_action_reason}{': ' + _esc(f.policy_note) if f.policy_note else ''} |")
    L += ["", "</details>", ""]

    path = out_dir / "review.md"
    path.write_text("\n".join(L))
    (out_dir / "proposals.json").write_text(json.dumps([p["payload"] for p in props], indent=1, ensure_ascii=False))
    return path


def _card(i: int, p: dict) -> list[str]:
    pl, r, j = p["payload"], p["payload"]["review"], p["payload"]["jira"]
    ev = r["evidence"]
    accounts = sorted({e["account"] for e in ev})
    L = [f"### {i}. {j['type']} · {j['priority']} · {j['summary']}", "",
         f"`{p['key']}` · {_state(p)} · {len(ev)} call(s), {len(accounts)} account(s): {', '.join(accounts)}", ""]
    for e in ev:
        L.append(f"> \"{e['quote']}\"  ({e['account']}, {e['date']}, {_src(e['link'])})")
        for c in e["context"]:
            if c["line"] != e["line"]:
                L.append(f">  - L{c['line']} {c['role'].lower()} {c['speaker']}: {_esc(c['text'][:220])}")
        L.append("")
    L += [f"- **Why new, not an existing issue:** {r['match_note']}",
          f"- **Priority {j['priority']} ({r['severity']}):** {r['severity_reason']}"]
    if len(ev) > 1:
        L.append(f"- **Grouped because:** {r['cluster_reason']}")
    if r.get("related"):
        L.append(f"- **Related asks folded in:** {'; '.join(r['related'])}")
    L.append(f"- **Slack:** {', '.join(m['channel'] for m in pl['slack'])}")
    L += ["", "<details><summary>Exact Jira payload</summary>", "", "```json",
          json.dumps(j, indent=1, ensure_ascii=False), "```", "</details>", ""]
    return L


def _state(p: dict) -> str:
    if p["status"] == "approved":
        fresh = p["approved_sha"] == sha(written_part(p["payload"]))
        return f"approved by {p['decided_by']}" if fresh else "**approval stale: payload changed**"
    return "awaiting review"


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")
