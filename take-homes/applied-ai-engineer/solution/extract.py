"""Per-call extraction (MODEL) followed by evidence validation (CODE).

The model proposes; code decides whether the proposal is grounded in the raw transcript.
Extractions are cached on disk keyed by transcript sha256 + prompt version, so a re-run over
unchanged transcripts replays the exact same model output (the basis of idempotent re-runs),
and the cache doubles as an audit record of what the model said.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import prompts
from .llm import LLM, Completion
from .transcript import Transcript, normalize

ACTIONABLE_DISPOSITIONS = {"new", "matches_tracked", "shipped_feature"}


@dataclass
class Finding:
    call_id: str
    idx: int  # position in the model's list; with the cache, stable across re-runs
    kind: str
    disposition: str
    title: str
    description: str
    line: int
    quote: str
    severity: str
    severity_reason: str
    match_note: str
    context_lines: list[int] = field(default_factory=list)
    tracked_key: str | None = None
    no_action_reason: str | None = None
    related_line: int | None = None
    # set by code:
    valid: bool = True
    reject_reason: str | None = None
    policy_note: str | None = None

    @property
    def id(self) -> str:
        return f"{self.call_id}#f{self.idx}"

    @property
    def actionable(self) -> bool:
        return self.valid and self.disposition in ACTIONABLE_DISPOSITIONS


@dataclass
class Extraction:
    call_id: str
    sha256: str
    prompt_version: str
    model: str
    cached: bool
    findings: list[Finding]
    usage: dict[str, Any]


def cache_path(cache_dir: Path, t: Transcript) -> Path:
    return cache_dir / f"{t.call_id}__{t.sha256[:12]}__{prompts.PROMPT_VERSION}.json"


def extract(t: Transcript, llm: LLM | None, catalog: list[dict], cache_dir: Path, refresh: bool = False) -> Extraction:
    path = cache_path(cache_dir, t)
    if path.exists() and not refresh:
        rec = json.loads(path.read_text())
        cached = True
    else:
        if llm is None:
            raise RuntimeError(f"{t.call_id}: no cached extraction and no model configured (offline mode)")
        prompt = prompts.EXTRACT_TEMPLATE.format(
            account=t.account, call_id=t.call_id, call_type=t.call_type, date=t.date,
            catalog=prompts.catalog_block(catalog), transcript=t.numbered(),
        )
        c: Completion = llm.complete(
            system=prompts.SYSTEM, prompt=prompt, schema=prompts.EXTRACT_SCHEMA, tool_name="report_findings"
        )
        rec = {
            "call_id": t.call_id, "sha256": t.sha256, "prompt_version": prompts.PROMPT_VERSION,
            "model": c.model, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "usage": {"input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                      "latency_s": round(c.latency_s, 2), "attempts": c.attempts},
            "output": c.data,
        }
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1))
        tmp.replace(path)  # atomic: a crash never leaves a half-written cache entry
        cached = False

    raw = rec["output"].get("findings")
    if not isinstance(raw, list):
        raise ValueError(f"{t.call_id}: model output has no findings list")
    findings = [_to_finding(t.call_id, i, r) for i, r in enumerate(raw)]
    return Extraction(t.call_id, t.sha256, rec["prompt_version"], rec["model"], cached, findings, rec.get("usage", {}))


def _to_finding(call_id: str, idx: int, r: dict) -> Finding:
    known = {f for f in Finding.__dataclass_fields__} - {"call_id", "idx", "valid", "reject_reason", "policy_note"}
    return Finding(call_id=call_id, idx=idx, **{k: v for k, v in r.items() if k in known})


def validate(t: Transcript, f: Finding, catalog_by_key: dict[str, dict]) -> None:
    """Deterministic grounding checks. Mutates f.valid / f.reject_reason. Only actionable findings
    are held to the evidence bar; dismissed ones are kept for the audit trail as-is."""

    def reject(why: str) -> None:
        f.valid, f.reject_reason = False, why

    if f.disposition not in ACTIONABLE_DISPOSITIONS:
        return
    if f.kind not in ("bug", "feature"):
        return reject(f"disposition {f.disposition} but kind {f.kind}")

    line = t.line(f.line)
    if line is None:
        return reject(f"cited line L{f.line} does not exist")
    if line.role != "EXTERNAL":
        return reject(f"cited line L{f.line} is spoken by [INTERNAL] {line.speaker}, not the customer")
    q = normalize(f.quote)
    if len(q.split()) < 4:
        return reject("quote too short to be evidence")
    if q not in normalize(line.text):
        return reject(f"quote is not verbatim on L{f.line}")
    f.context_lines = [n for n in f.context_lines if t.line(n) is not None][:4]

    if f.disposition in ("matches_tracked", "shipped_feature"):
        issue = catalog_by_key.get(f.tracked_key or "")
        if issue is None:
            return reject(f"tracked_key {f.tracked_key!r} is not in the catalogue")
        # The catalogue, not the model, says whether something shipped.
        shipped = issue.get("status") == "Shipped"
        if shipped and f.disposition == "matches_tracked":
            f.disposition, f.policy_note = "shipped_feature", f"{issue['key']} is Shipped: enablement, not a ticket"
        elif not shipped and f.disposition == "shipped_feature":
            f.disposition, f.policy_note = "matches_tracked", f"{issue['key']} is {issue['status']}, not Shipped"


def to_json(f: Finding) -> dict:
    return asdict(f)
