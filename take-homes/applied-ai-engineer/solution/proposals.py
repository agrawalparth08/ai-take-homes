"""Deterministic policy, cross-call clustering, and payload building.

Everything here is CODE except `cluster()`, which asks the model one question
("which of these candidates are the same problem?") and then validates the answer.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import prompts
from .extract import Finding
from .llm import LLM
from .transcript import Transcript

PRIORITY = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
SEV_ORDER = ["low", "medium", "high", "critical"]


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def slack_handle(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "@" + ".".join(ascii_name.lower().split())


def link(call_id: str, line: int) -> str:
    return f"transcripts/{call_id}.md#L{line}"


# --- policy -----------------------------------------------------------------

def apply_policy(f: Finding, t: Transcript, catalog_by_key: dict[str, dict]) -> None:
    """Rules that are facts about the catalogue, not judgment calls."""
    if not f.actionable or f.disposition != "matches_tracked":
        return
    issue = catalog_by_key[f.tracked_key]
    if t.account and t.account in issue.get("reported_by_accounts", []):
        f.disposition = "no_action"
        f.no_action_reason = "already_attributed"
        f.policy_note = f"{t.account} is already on {issue['key']}; nothing new to attach"


# --- clustering (model, validated) --------------------------------------------

@dataclass
class Group:
    members: list[Finding]
    filed_key: str | None
    reason: str


def cluster(cands: list[Finding], filed: list[dict], llm: LLM | None, cache_dir: Path,
            log: Any = None) -> list[Group]:
    if not cands:
        return []
    if len(cands) == 1 and not filed:
        return [Group(cands, None, "single candidate")]
    by_id = {f.id: f for f in cands}
    payload = [{"id": f.id, "type": f.kind, "title": f.title, "description": f.description} for f in cands]
    key = sha({"v": prompts.CLUSTER_VERSION, "c": payload, "f": [(x["key"], x["title"]) for x in filed]})[:16]
    path = cache_dir / f"cluster__{key}.json"
    if path.exists():
        out = json.loads(path.read_text())
    elif llm is None:
        raise RuntimeError("no cached clustering for this candidate set and no model configured")
    else:
        c = llm.complete(system=prompts.SYSTEM, prompt=prompts.cluster_prompt(payload, filed),
                         schema=prompts.CLUSTER_SCHEMA, tool_name="report_groups")
        out = c.data
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1))

    # Validate the model's partition. Anything malformed falls back to singletons (safe: a reviewer can
    # merge two cards, but can't see an issue that a bad merge swallowed).
    seen: set[str] = set()
    groups: list[Group] = []
    filed_keys = {x["key"] for x in filed}
    for g in out.get("groups", []):
        ids = [i for i in g.get("candidate_ids", []) if i in by_id and i not in seen]
        dropped = set(g.get("candidate_ids", [])) - set(ids)
        if dropped and log:
            log.event("cluster", "warn", detail=f"ignored unknown/duplicate ids {sorted(dropped)}")
        if not ids:
            continue
        seen.update(ids)
        fk = g.get("filed_key") if g.get("filed_key") in filed_keys else None
        if g.get("filed_key") and fk is None and log:
            log.event("cluster", "warn", detail=f"unknown filed_key {g.get('filed_key')!r}; treated as new")
        groups.append(Group([by_id[i] for i in sorted(ids)], fk, g.get("reason", "")))
    for f in cands:
        if f.id not in seen:
            if log:
                log.event("cluster", "warn", call_id=f.call_id, detail=f"{f.id} missing from grouping; kept alone")
            groups.append(Group([f], None, "not grouped by model; kept alone"))
    return groups


# --- payloads ----------------------------------------------------------------

def _evidence(f: Finding, t: Transcript) -> dict:
    ctx = []
    for n in sorted({f.line, *f.context_lines}):
        ln = t.line(n)
        if ln:
            ctx.append({"line": n, "role": ln.role, "speaker": ln.speaker, "text": ln.text})
    return {"finding_id": f.id, "call_id": f.call_id, "sha": t.sha256[:12], "account": t.account, "date": t.date,
            "line": f.line, "quote": f.quote, "link": link(f.call_id, f.line), "context": ctx}


def new_ticket(group: Group, ts: dict[str, Transcript], related: dict[str, list[Finding]]) -> dict:
    primary = group.members[0]
    severity = max((m.severity for m in group.members), key=SEV_ORDER.index)
    evidence = [_evidence(m, ts[m.call_id]) for m in group.members]
    accounts = sorted({e["account"] for e in evidence if e["account"]})
    key = f"new:{primary.id}"
    idem = "jt-" + sha(key)[:16]

    body = [primary.description, "",
            f"*Reported on {len(evidence)} call(s) by {len(accounts)} account(s):* {', '.join(accounts)}", ""]
    for e in evidence:
        body.append(f"> \"{e['quote']}\"  ({e['account']}, {e['call_id']} {e['date']}, {e['link']})")
    extras = [r for m in group.members for r in related.get(m.id, [])]
    if extras:
        body += ["", "*Related asks on the same call(s) (not filed separately):*"]
        body += [f"- {r.title} ({r.call_id} L{r.line})" for r in extras]
    body += ["", f"_Severity {severity}: {primary.severity_reason}_",
             "_Drafted by june-tapes from customer-call transcripts; reviewed and approved by a human before filing._"]

    jira = {
        "project": "PROJ",
        "type": "Bug" if primary.kind == "bug" else "Feature",
        "summary": primary.title[:120],
        "description": "\n".join(body),
        "priority": PRIORITY[severity],
        "labels": ["customer-call", "june-tapes"],
        "source": {"call_id": primary.call_id, "line": primary.line, "snippet": primary.quote,
                   "link": link(primary.call_id, primary.line)},
        "corroborating_sources": [{"call_id": e["call_id"], "line": e["line"], "snippet": e["quote"],
                                   "link": e["link"]} for e in evidence[1:]],
        "idempotency_key": idem,
    }
    slack_ctx = []
    for owner in _owners(group.members, ts):
        calls = [m.call_id for m in group.members if _owner_name(ts[m.call_id]) == owner]
        quote = primary.quote if primary.call_id in calls else _first(group.members, calls).quote
        slack_ctx.append({"channel": slack_handle(owner), "calls": calls, "quote": quote,
                          "idempotency_key": f"{idem}-{slack_handle(owner)[1:]}"})
    slack = new_ticket_slack(jira, slack_ctx)
    return {
        "key": key, "kind": "new_ticket", "call_ids": sorted({m.call_id for m in group.members}),
        "jira": jira, "slack": slack,
        "review": {"severity": severity, "severity_reason": primary.severity_reason,
                   "match_note": primary.match_note, "cluster_reason": group.reason,
                   "evidence": evidence, "related": [r.title for r in extras], "slack_ctx": slack_ctx},
    }


def new_ticket_slack(jira: dict, ctx: list[dict]) -> list[dict]:
    return [{"channel": c["channel"],
             "text": (f"New {jira['type'].lower()} filed from your call(s) {', '.join(c['calls'])}: "
                      f"{{jira_key}} [{jira['priority']}] {jira['summary']}. Customer quote: \"{c['quote']}\""),
             "idempotency_key": c["idempotency_key"]} for c in ctx]


def apply_edit(payload: dict, *, priority: str | None = None, title: str | None = None,
               type_: str | None = None, by: str = "reviewer") -> dict:
    """A reviewer edit keeps the whole bundle consistent: Jira fields, description footer and Slack text."""
    j = payload["jira"]
    if priority:
        j["priority"] = priority
    if title:
        j["summary"] = title
    if type_:
        j["type"] = type_
    lines = [l for l in j["description"].split("\n") if not l.startswith("_Severity ") and not l.startswith("_Edited ")]
    footer = lines.index(next(l for l in lines if l.startswith("_Drafted by")))
    lines.insert(footer, f"_Edited by {by}: {j['type']} {j['priority']} (model proposed {payload['review']['severity']}: "
                         f"{payload['review']['severity_reason']})_")
    j["description"] = "\n".join(lines)
    payload["slack"] = new_ticket_slack(j, payload["review"]["slack_ctx"])
    return payload


def corroboration(call_id: str, target: str, target_summary: str, members: list[Finding],
                  t: Transcript, target_is_ours: bool) -> dict:
    key = f"corr:{call_id}:{target}"
    idem = "jt-" + sha(key)[:16]
    f = members[0]
    record = {"issue_key": target, "call_id": call_id, "account": t.account, "date": t.date,
              "line": f.line, "snippet": f.quote, "link": link(call_id, f.line), "idempotency_key": idem}
    owner = _owner_name(t)
    slack = [{"channel": slack_handle(owner),
              "text": (f"FYI: {t.account}'s report on {call_id} was attached to {target} ({target_summary}) "
                       f"instead of opening a new ticket. Quote: \"{f.quote}\""),
              "idempotency_key": f"{idem}-slack"}] if owner else []
    return {"key": key, "kind": "corroborate", "call_ids": [call_id], "corroboration": record, "slack": slack,
            "review": {"target": target, "target_summary": target_summary, "target_is_ours": target_is_ours,
                       "match_note": f.match_note, "evidence": [_evidence(m, t) for m in members]}}


def enablement(f: Finding, issue: dict, t: Transcript) -> dict:
    key = f"enable:{f.call_id}:{issue['key']}"
    owner = _owner_name(t)
    slack = [{"channel": slack_handle(owner),
              "text": (f"{t.account} asked for \"{f.title}\" on {f.call_id}. That already shipped: {issue['key']} "
                       f"{issue['summary']} ({issue.get('shipped_in', 'shipped')}). {issue['description']} "
                       f"Worth confirming they found it; no ticket filed."),
              "idempotency_key": "jt-" + sha(key)[:16] + "-slack"}] if owner else []
    return {"key": key, "kind": "enablement", "call_ids": [f.call_id], "slack": slack,
            "review": {"target": issue["key"], "target_summary": issue["summary"], "match_note": f.match_note,
                       "evidence": [_evidence(f, t)]}}


def written_part(p: dict) -> dict:
    """The part of a proposal that reaches a sink. Approval is bound to the hash of exactly this."""
    return {k: p[k] for k in ("jira", "slack", "corroboration") if k in p}


def _owner_name(t: Transcript) -> str | None:
    return t.owner.name if t.owner else None


def _owners(members: list[Finding], ts: dict[str, Transcript]) -> list[str]:
    out: list[str] = []
    for m in members:
        o = _owner_name(ts[m.call_id])
        if o and o not in out:
            out.append(o)
    return out


def _first(members: list[Finding], calls: list[str]) -> Finding:
    return next(m for m in members if m.call_id in calls)
