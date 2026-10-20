"""accepted_differences.yaml — known, explained Excel↔MES differences.

    - body: "UP TO 5.5 CHILLER AND 2.3 WIDE"   # exact sheet name, trailer id, "*", or a list
      section: "SUB FRAME + LIGHT BOX ASSY"    # Excel or MES spelling (name-normalised), "*", or a list
      variant: "*"                              # as_sheet | all_pu | ... | "*" | a list
      cause: "TAPPING BLOCKS"                   # optional: only cells whose likely cause contains this
      kind: known_defect                        # known_defect | tolerated (default)
      reason: "one line — what differs and why (a diagnosed MES/Excel defect, or a tolerated quirk)"
      owner: "BA"
      review_by: 2026-12-31

`cause` (a string or a list of strings; case/space-insensitive substring of the
cell's likely cause) ties the acceptance to a MECHANISM, not just a section: a
cell in the same section that fails for a different reason stays a FLAG.
Without it a R60 tapping-block entry greyed a R23k PU error in the same
section — which is exactly what the first prod run showed.

From v1.57.2 an entry must also EXPLAIN the difference: on a FLAG cell (both
sides priced) the lines its cause names — across every in-scope entry — must
account for the section's net difference to within the tolerance, or the cell
stays a FLAG with the unexplained remainder in its reason. A R60 tapping-block
entry can no longer grey a section whose real difference is a missing EPS line.
PRESENCE / UNMAPPED cells (the whole section on one side only) are judged on
the reason text, as before.

An ACCEPTED cell does not fail CI. `tolerated` renders grey (a legitimate or
tolerated difference); `known_defect` renders amber and is listed under
"Known defects (tracked)" in every summary — the entry IS the work-order
list, and removing it once the fix lands makes CI enforce the fix. An entry
whose review_by has passed turns every cell it covers into EXPIRED — which
FAILS, so the acceptance is re-reviewed rather than forgotten (ratified
default 8).

RT7 (v1.61.1) — every PROD entry PINS ITS AMOUNTS. A cause alone once hid a
gap (an ICECREAM MEDIUM floor kept its acceptance while its difference moved),
so an entry now lists, per cell it accepts, the difference it accepted:

    amounts:                       # MES - Excel per cell, to 2 dp
      "ICECREAM_UP_TO_4.8~L3.6~W2.3~H2.26~as_sheet | FLOOR": -1914.11
    mechanism: probe_limit         # what the difference IS (MECHANISMS); `cause:` stays the line matcher
    refs: ["the probe ..."]        # what clears it (Burt's fix-list item, or the probe change)

A covered cell is ACCEPTED only when EVERY covering entry pins it at its
current difference within R0.01; otherwise it is a FLAG whose reason starts
ACCEPTED_AMOUNT_CHANGED and names the pinned and actual amounts (or "pins no
amount" for a cell that newly came into scope). A cell two entries explain is
pinned on both; one pin serves smoke and the full packs (same scenario ids).
The prod list (*.prod.yaml) refuses an entry without amounts, mechanism, refs
or review_by; the dev list stays unpinned. The prod list's header (`pair:`)
records the CI snapshot it was pinned against — test_rt7_pins.py asserts its
sha256 equals mes_snapshot/all.json, so the two move together or not at all.
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
    cause: str | list[str] | None = None
    # RT7 — the amount each accepted cell differs by, pinned: {"<scenario id> | <section>": rand}. None = the entry
    # pins nothing (a dev list); {} = it pins no cell, so it accepts none.
    amounts: dict[str, float] | None = None
    mechanism: str | None = None
    refs: list[str] | None = None

    def pinned(self, key: str) -> float | None:
        return None if self.amounts is None else self.amounts.get(key)

    def expired(self, today: date | None = None) -> bool:
        return self.review_by is not None and (today or date.today()) > self.review_by

    def cause_tokens(self) -> list[str]:
        return [t for t in (norm_name(c) for c in _as_list(self.cause)) if t] if self.cause else []

    def names_cause(self, text: str | None) -> bool:
        """True when the entry has no cause, or one of its cause tokens is in `text`."""
        toks = self.cause_tokens()
        if not toks:
            return True
        have = norm_name(text or "")
        return any(t in have for t in toks)

    def matches(self, *, sheet: str, trailer_id: int, section_names: list[str], variant: str,
                cause: str | None = None) -> bool:
        return (self.in_scope(sheet=sheet, trailer_id=trailer_id, section_names=section_names, variant=variant)
                and self.names_cause(cause))

    def in_scope(self, *, sheet: str, trailer_id: int, section_names: list[str], variant: str) -> bool:
        """Body, section and variant only — the cause is judged separately."""
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
        return {"index": self.index,
                "body": self.body, "section": self.section, "variant": self.variant, "kind": self.kind,
                "cause": self.cause, "mechanism": self.mechanism, "refs": self.refs,
                "reason": self.reason, "owner": self.owner,
                "review_by": self.review_by.isoformat() if self.review_by else None}


def _as_list(v) -> list[str]:
    """'a' | ['a', 'b'] -> list of stripped strings. Never split a string on
    commas: Burt's sheet names carry them ('icecream up to 3,2')."""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    return [str(v).strip()]


# RT7 — what an entry's difference IS. `cause:` stays the LINE matcher (a substring of the triage line); the label
# lives here. A prod entry must name one of these.
MECHANISMS = {
    "mes_updated_ahead_of_burt": "Michael changed the MES on purpose; Burt's workbook has not caught up",
    "burt_sheet_formula_slip": "a formula in Burt's sheet points at the wrong cell; the MES is right",
    "burt_decision_pending": "Burt's sheet and the MES differ on a point Burt has been asked to decide",
    "burt_description_not_updated": "Burt re-pointed a price without updating its label (ruling 17 Sep 2026)",
    "probe_limit": "the audit probe cannot set what the calculator offers (e.g. a draft choice)",
    "known_mes_defect": "a diagnosed MES defect awaiting its work order",
}
PROD_LIST_SUFFIX = ".prod.yaml"


def requires_pins(path: Path) -> bool:
    """The PROD list pins every amount (RT7_RULING_1); the dev list (Michael's workbench) does not."""
    return Path(path).name.endswith(PROD_LIST_SUFFIX)


def load_accepted_doc(path: Path | None = None, *, require_pins: bool | None = None,
                      ignore_pins: bool = False) -> tuple[dict, list[Accepted]]:
    """(header, entries). The file is a list of entries, or a mapping {"pair": {...}, "accepted": [...]} whose
    `pair` records the CI snapshot it was pinned against (RT7: snapshot_sha256, exported_at, prod_code, alembic).

    `require_pins` (default: a *.prod.yaml file) refuses an entry without `amounts`, `mechanism` (one of MECHANISMS),
    `refs` and `review_by`. `ignore_pins` loads every entry with amounts=None — what `audit pin` needs to find the
    cells before it pins them."""
    p = Path(path or ACCEPTED_FILE)
    if not p.is_file():
        return {}, []
    strict = requires_pins(p) if require_pins is None else require_pins
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    header: dict = {}
    if isinstance(doc, dict):
        header = {k: v for k, v in doc.items() if k != "accepted"}
        doc = doc.get("accepted") or []
    entries = _parse(p, doc, strict=strict and not ignore_pins)
    if ignore_pins:
        for a in entries:
            a.amounts = None
    return header, entries


def load_accepted(path: Path | None = None, *, require_pins: bool | None = None) -> list[Accepted]:
    return load_accepted_doc(path, require_pins=require_pins)[1]


def _parse(p: Path, doc: list, *, strict: bool) -> list[Accepted]:
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
        cause = e.get("cause")
        amounts = e.get("amounts")
        if amounts is not None:
            if not isinstance(amounts, dict):
                raise ValueError(f"{p.name}: entry {i} amounts must be a mapping 'scenario | section': rand")
            amounts = {" | ".join(s.strip() for s in str(k).split("|", 1)): round(float(v), 2)
                       for k, v in amounts.items()}
        mech = str(e["mechanism"]) if e.get("mechanism") else None
        if mech is not None and mech not in MECHANISMS:
            raise ValueError(f"{p.name}: entry {i} mechanism {mech!r} is not one of {sorted(MECHANISMS)}")
        refs = e.get("refs")
        if refs is not None and not isinstance(refs, (list, tuple)):
            refs = [refs]
        if strict:
            missing = [k for k, v in (("amounts", amounts), ("mechanism", mech), ("refs", refs), ("review_by", rb))
                       if not v]
            if missing:
                raise ValueError(f"{p.name}: entry {i} ({_field(e['body'])} / {_field(e['section'])}) needs "
                                 f"{', '.join(missing)} — every prod entry pins its amounts, names its mechanism, "
                                 "what clears it and when it is reviewed (RT7_RULING_1)")
        out.append(Accepted(body=_field(e["body"]), section=_field(e["section"]),
                            variant=_field(e.get("variant", "*")), reason=str(e["reason"]),
                            owner=str(e.get("owner", "?")), review_by=rb, index=i, kind=kind,
                            cause=_field(cause) if cause else None, amounts=amounts,
                            mechanism=mech, refs=[str(r) for r in refs] if refs else None))
    return out
