"""accepted_differences.yaml — known, explained Excel↔MES differences.

    - body: "UP TO 5.5 CHILLER AND 2.3 WIDE"   # exact sheet name, trailer id, or "*"
      section: "SUB FRAME + LIGHT BOX ASSY"    # Excel or MES spelling (name-normalised), or "*"
      variant: "*"                              # as_sheet | all_pu | ... | "*"
      reason: "one line — what differs and why it is right (or tolerated)"
      owner: "BA"
      review_by: 2026-12-31

An ACCEPTED cell renders grey and does not fail CI. An entry whose review_by
has passed turns every cell it covers into EXPIRED — which FAILS, so the
acceptance is re-reviewed rather than forgotten (ratified default 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from . import ACCEPTED_FILE
from .mapping import norm_key, norm_name


@dataclass
class Accepted:
    body: str
    section: str
    variant: str
    reason: str
    owner: str
    review_by: date | None
    index: int

    def expired(self, today: date | None = None) -> bool:
        return self.review_by is not None and (today or date.today()) > self.review_by

    def matches(self, *, sheet: str, trailer_id: int, section_names: list[str], variant: str) -> bool:
        b = self.body.strip()
        if b != "*" and norm_name(b) != norm_name(sheet) and b != str(trailer_id):
            return False
        s = self.section.strip()
        if s != "*" and norm_key(s) not in {norm_key(n) for n in section_names if n}:
            return False
        v = self.variant.strip()
        return v == "*" or v == variant

    def to_dict(self) -> dict:
        return {"body": self.body, "section": self.section, "variant": self.variant,
                "reason": self.reason, "owner": self.owner,
                "review_by": self.review_by.isoformat() if self.review_by else None}


def load_accepted(path: Path | None = None) -> list[Accepted]:
    p = Path(path or ACCEPTED_FILE)
    if not p.is_file():
        return []
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    if isinstance(doc, dict):
        doc = doc.get("accepted") or []
    out: list[Accepted] = []
    for i, e in enumerate(doc):
        if not isinstance(e, dict):
            raise ValueError(f"{p.name}: entry {i} is not a mapping")
        for k in ("body", "section", "reason"):
            if not e.get(k):
                raise ValueError(f"{p.name}: entry {i} needs '{k}'")
        rb = e.get("review_by")
        if isinstance(rb, str):
            rb = date.fromisoformat(rb)
        out.append(Accepted(body=str(e["body"]), section=str(e["section"]),
                            variant=str(e.get("variant", "*")), reason=str(e["reason"]),
                            owner=str(e.get("owner", "?")), review_by=rb, index=i))
    return out
