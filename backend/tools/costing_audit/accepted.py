"""accepted_differences.yaml — known, explained Excel↔MES differences.

    - body: "UP TO 5.5 CHILLER AND 2.3 WIDE"   # exact sheet name, trailer id, "*", or a list
      section: "SUB FRAME + LIGHT BOX ASSY"    # Excel or MES spelling (name-normalised), "*", or a list
      variant: "*"                              # as_sheet | all_pu | ... | "*" | a list
      kind: known_defect                        # known_defect | tolerated (default)
      reason: "one line — what differs and why (a diagnosed MES/Excel defect, or a tolerated quirk)"
      owner: "BA"
      review_by: 2026-12-31

An ACCEPTED cell does not fail CI. `tolerated` renders grey (a legitimate or
tolerated difference); `known_defect` renders amber and is listed under
"Known defects (tracked)" in every summary — the entry IS the work-order
list, and removing it once the fix lands makes CI enforce the fix. An entry
whose review_by has passed turns every cell it covers into EXPIRED — which
FAILS, so the acceptance is re-reviewed rather than forgotten (ratified
default 8).
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
    body: str | list[str]
    section: str | list[str]
    variant: str | list[str]
    reason: str
    owner: str
    review_by: date | None
    index: int
    kind: str = "tolerated"

    def expired(self, today: date | None = None) -> bool:
        return self.review_by is not None and (today or date.today()) > self.review_by

    def matches(self, *, sheet: str, trailer_id: int, section_names: list[str], variant: str) -> bool:
        bodies = _as_list(self.body)
        if "*" not in bodies and not any(norm_name(b) == norm_name(sheet) or b == str(trailer_id) for b in bodies):
            return False
        secs = _as_list(self.section)
        have = {norm_key(n) for n in section_names if n}
        if "*" not in secs and not any(norm_key(x) in have for x in secs):
            return False
        vars_ = _as_list(self.variant)
        return "*" in vars_ or variant in vars_

    def to_dict(self) -> dict:
        return {"body": self.body, "section": self.section, "variant": self.variant, "kind": self.kind,
                "reason": self.reason, "owner": self.owner,
                "review_by": self.review_by.isoformat() if self.review_by else None}


def _as_list(v) -> list[str]:
    """'a' | ['a', 'b'] -> list of stripped strings. Never split a string on
    commas: Burt's sheet names carry them ('icecream up to 3,2')."""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    return [str(v).strip()]


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
        kind = str(e.get("kind", "tolerated"))
        if kind not in ("tolerated", "known_defect"):
            raise ValueError(f"{p.name}: entry {i} kind must be tolerated | known_defect")
        def _field(v):
            return [str(x) for x in v] if isinstance(v, (list, tuple)) else str(v)
        out.append(Accepted(body=_field(e["body"]), section=_field(e["section"]),
                            variant=_field(e.get("variant", "*")), reason=str(e["reason"]),
                            owner=str(e.get("owner", "?")), review_by=rb, index=i, kind=kind))
    return out
