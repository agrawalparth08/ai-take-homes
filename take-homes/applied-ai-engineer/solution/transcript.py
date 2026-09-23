"""Transcript parsing. Deterministic: no model involved.

The raw transcript is the source of truth. We keep every line with its 1-indexed
file line number so evidence can be checked against (and linked back to) the file.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

_LINE = re.compile(r"^\[(EXTERNAL|INTERNAL)\] ([^:]{1,80}): (.*)$")
_TITLE = re.compile(r"^# Call — (.+?) × BetterBark(?: · (.+))?$")
_PARTICIPANT = re.compile(r"\[(EXTERNAL|INTERNAL)\] ([^,·]+?)(?:, ([^·]+?))?\s*(?:·|$)")


class TranscriptError(ValueError):
    """The file does not look like a call transcript. Fail this call, not the run."""


@dataclass(frozen=True)
class Line:
    no: int  # 1-indexed line number in the .md file
    role: str  # EXTERNAL | INTERNAL
    speaker: str
    text: str


@dataclass(frozen=True)
class Participant:
    role: str
    name: str
    title: str


@dataclass(frozen=True)
class Transcript:
    call_id: str
    path: str
    sha256: str
    account: str | None  # None for internal-only calls
    call_type: str
    date: str
    participants: tuple[Participant, ...]
    lines: tuple[Line, ...] = field(repr=False)

    @property
    def has_external(self) -> bool:
        return any(p.role == "EXTERNAL" for p in self.participants) or any(
            l.role == "EXTERNAL" for l in self.lines
        )

    @property
    def owner(self) -> Participant | None:
        """Call owner = the CSM on the call, else the first internal participant."""
        internal = [p for p in self.participants if p.role == "INTERNAL"]
        for p in internal:
            if "CSM" in p.title:
                return p
        return internal[0] if internal else None

    def line(self, no: int) -> Line | None:
        for l in self.lines:
            if l.no == no:
                return l
        return None

    def numbered(self) -> str:
        """The form the model sees: line number, role, speaker, text."""
        return "\n".join(f"L{l.no} [{l.role}] {l.speaker}: {l.text}" for l in self.lines)


def parse(raw: str, path: str) -> Transcript:
    rows = raw.splitlines()
    if len(rows) < 4:
        raise TranscriptError(f"{path}: too short to be a transcript")
    title = _TITLE.match(rows[0].strip())
    call_id_m = re.search(r"Call ID: (call-\d{3})", rows[1])
    date_m = re.search(r"Date: (\d{4}-\d{2}-\d{2})", rows[1])
    if not call_id_m or not rows[2].startswith("Participants:"):
        raise TranscriptError(f"{path}: missing Call ID or Participants header")

    participants = tuple(
        Participant(role=m.group(1), name=m.group(2).strip(), title=(m.group(3) or "").strip())
        for m in _PARTICIPANT.finditer(rows[2][len("Participants:"):])
    )
    lines = []
    for i, row in enumerate(rows[3:], start=4):
        m = _LINE.match(row)
        if m:
            lines.append(Line(no=i, role=m.group(1), speaker=m.group(2).strip(), text=m.group(3)))
    if not lines:
        raise TranscriptError(f"{path}: no speaker lines")

    return Transcript(
        call_id=call_id_m.group(1),
        path=path,
        sha256=hashlib.sha256(raw.encode()).hexdigest(),
        account=title.group(1).strip() if title else None,
        call_type=(title.group(2) or "").strip() if title else rows[0].lstrip("# ").strip(),
        date=date_m.group(1) if date_m else "",
        participants=participants,
        lines=tuple(lines),
    )


def load(path: Path) -> Transcript:
    return parse(path.read_text(encoding="utf-8"), path.name)


def normalize(s: str) -> str:
    """Whitespace/quote-insensitive form used for verbatim-quote checks."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-").replace("…", "...")
    return re.sub(r"\s+", " ", s).strip().lower()
