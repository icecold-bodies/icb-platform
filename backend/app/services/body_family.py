"""RT3 — body families: the ONE place a body's family, its colour and the contrast rule live.

A body's family IS its trailer group (trailer_types.group_id -> trailer_groups), the same group that
picks its default quote template. Migration 0051 gave the group a colour ('#RRGGBB') and a sort_order.
Everything that shows a body (the BODY TYPE dropdowns, the costings list, the saved costing, Body
Templates, the audit report, ...) reads its family from here, through the bodies API (`family` on every
/api/trailers row) or the Jinja globals; no page hard-codes a colour beyond FALLBACK's grey.

THE LIGHT MES SKIN ONLY (RT3_RULING_1a): theme-mes.css is the one stylesheet the families are built for —
white inputs (#FFFFFF) on a #F5F7FB page. One stored colour per family colours bars, dots and borders, the
same everywhere, so it is learnt once (>= 3:1 on both backgrounds). Family TEXT uses ONE ink derived here from
the stored colour: the colour itself when it already clears 4.6:1 on both, else the nearest darker tint that
does. The admin colour warning (RT3_RULING_1 addition 1) uses `colour_check`, the same arithmetic.

The family object is {id, name, colour, ink, sort_order}. A body with no group shows as OTHER grey: the group
named OTHER when there is one, else FALLBACK.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import object_session

# The fallback family: a body with no group and no OTHER group to fall into. The only hard-coded colour.
FALLBACK_NAME = "OTHER"
FALLBACK_COLOUR = "#7D858C"
FALLBACK_SORT = 1000

# The backgrounds a family colour sits on — theme-mes.css: the inputs and the page.
LIGHT_BACKGROUNDS = ("#ffffff", "#f5f7fb")
BAR_MIN = 3.0          # WCAG 1.4.11: bars, dots, borders
INK_MIN = 4.6          # the text ink: WCAG 1.4.3's 4.5 plus headroom (RT3_RULING_1 Q6 / 1a)

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# A new body's family guessed from its typed name (the Trailer Designer pre-selects it; RT3_RULING_1 Q8).
# First match wins. EXPLOSIVE / MEAT / FREEZER are the startup bootstrap's own keywords; ORANGE comes
# first because Michael ruled Rhinorange is OTHER (its name would not otherwise match a family).
FAMILY_KEYWORDS = (
    (re.compile(r"ORANGE", re.I), "OTHER"),
    (re.compile(r"EXPLOSIVE", re.I), "EXPLOSIVE"),
    (re.compile(r"CHILL", re.I), "CHILLER"),
    (re.compile(r"FREEZ", re.I), "FREEZER"),
    (re.compile(r"MEAT", re.I), "MEAT"),
    (re.compile(r"ICE ?CREAM", re.I), "ICE CREAM"),
)


def _rgb(colour: str) -> tuple[int, int, int]:
    c = colour.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(x))):02X}" for x in rgb)


def _lin(x: float) -> float:
    x /= 255
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    r, g, b = (_lin(x) for x in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def worst(colour: str, backgrounds=LIGHT_BACKGROUNDS) -> float:
    """The colour's lowest contrast over the backgrounds (by default the MES skin's two)."""
    return min(contrast(colour, bg) for bg in backgrounds)


def ink(colour: str) -> str:
    """The family TEXT ink on the light MES skin: the stored colour itself when it already clears INK_MIN on
    both backgrounds, else the nearest darker tint (5 % steps toward black) that does."""
    base = _rgb(colour)
    for k in range(21):
        cand = _hex([x * (1 - k * 0.05) for x in base])
        if worst(cand) >= INK_MIN:
            return cand
    return "#000000"


def normalise(colour) -> str | None:
    """'#rrggbb' -> '#RRGGBB'; anything else (None, '', 'red', '#abc') -> None."""
    if not isinstance(colour, str) or not HEX.match(colour.strip()):
        return None
    return colour.strip().upper()


def colour_check(colour: str) -> dict:
    """The admin's warning (light skin only, RT3_RULING_1a 5): the colour's worst bar contrast on #FFFFFF /
    #F5F7FB (>= 3:1) and its derived ink's (>= 4.6:1). `ok` False -> the page warns and asks; it never blocks."""
    c = normalise(colour)
    if c is None:
        raise ValueError(f"not a #RRGGBB colour: {colour!r}")
    t = ink(c)
    bar, ink_cr = worst(c), worst(t)
    return {"colour": c, "bar": round(bar, 2), "bar_minimum": BAR_MIN, "ink": t, "ink_contrast": round(ink_cr, 2),
            "ink_minimum": INK_MIN, "ok": bar >= BAR_MIN and ink_cr >= INK_MIN}


def guess_family_name(body_name: str) -> str:
    for rx, fam in FAMILY_KEYWORDS:
        if rx.search(body_name or ""):
            return fam
    return FALLBACK_NAME


def _payload(gid, name, colour, sort_order) -> dict:
    c = normalise(colour) or FALLBACK_COLOUR
    return {"id": gid, "name": name, "colour": c, "ink": ink(c), "sort_order": sort_order}


def group_family(group) -> dict:
    """{id, name, colour, ink, sort_order} for one trailer_groups row."""
    return _payload(group.id, group.name, group.colour,
                    group.sort_order if group.sort_order is not None else 100)


def fallback_family() -> dict:
    return _payload(None, FALLBACK_NAME, FALLBACK_COLOUR, FALLBACK_SORT)


def _other_group(session):
    """The group named OTHER, looked up once per session (session.info caches it)."""
    if session is None:
        return None
    key = "rt3_other_group"
    if key not in session.info:
        from ..database import TrailerGroup
        from sqlalchemy import func
        session.info[key] = (session.query(TrailerGroup)
                             .filter(func.upper(TrailerGroup.name) == FALLBACK_NAME).order_by(TrailerGroup.id).first())
    return session.info[key]


def body_family(tt) -> dict:
    """The family of one body (a TrailerType): its group, else OTHER (the OTHER group, else FALLBACK)."""
    if tt is not None and tt.group is not None:
        return group_family(tt.group)
    other = _other_group(object_session(tt)) if tt is not None else None
    return group_family(other) if other is not None else fallback_family()


def group_bodies(trailers) -> list[tuple[dict, list]]:
    """The bodies grouped by family, families in (sort_order, name) order; each family keeps the order the
    bodies came in (the callers pass them sorted by name). Only families with a body appear. A body is a
    TrailerType, or a dict that already carries its "family" (a page that also hands its list to JS)."""
    fams: dict = {}
    for t in trailers:
        f = t["family"] if isinstance(t, dict) else body_family(t)
        key = (f["id"], f["name"])
        fams.setdefault(key, (f, []))[1].append(t)
    return sorted(fams.values(), key=lambda fb: (fb[0]["sort_order"], fb[0]["name"].upper()))


def all_families(db) -> list[dict]:
    """Every family (trailer group) in dropdown order, with its active-body count."""
    from ..database import TrailerGroup, TrailerType
    from sqlalchemy import func
    counts = dict(db.query(TrailerType.group_id, func.count(TrailerType.id))
                  .filter(TrailerType.is_active.is_(True)).group_by(TrailerType.group_id).all())
    out = []
    for g in db.query(TrailerGroup).order_by(TrailerGroup.sort_order, TrailerGroup.name).all():
        out.append(dict(group_family(g), active_bodies=counts.get(g.id, 0),
                        report_template_id=g.report_template_id,
                        rule_note=normalise_rule_note(g.rule_note)))   # RT5
    return out


# RT5 (migration 0052) — the family's RULE NOTE: Burt's product rule for every body of the family ("No PU insulation
# for Chillers"), shown in red under BODY OPTIONS (the calculator) and under the body's header (Body Templates).
# Plain text, several lines allowed; every page writes it as TEXT (textContent / Jinja autoescape), never as HTML.
# Its red is the MES skin's own --red darkened by ink() until it reads on both light backgrounds (#DC2626 alone is
# 4.50:1 on #F5F7FB, under INK_MIN). Never on a customer document or an export.
SKIN_RED = "#DC2626"
RULE_NOTE_INK = ink(SKIN_RED)
RULE_NOTE_MAX = 500


def normalise_rule_note(text) -> str | None:
    """The stored form of a note: Windows and old-Mac line ends become LF, trailing spaces are trimmed per line,
    blank lines at either end are dropped; None when nothing is left. ValueError when longer than RULE_NOTE_MAX."""
    if text is None:
        return None
    lines = [ln.rstrip() for ln in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out = "\n".join(lines)
    if not out:
        return None
    if len(out) > RULE_NOTE_MAX:
        raise ValueError(f"A rule note is at most {RULE_NOTE_MAX} characters (this one is {len(out)}).")
    return out


def rule_note_of(tt) -> str | None:
    """The rule note a body shows: its family's — the same family body_family() resolves (its group, else the
    OTHER group). None when the family has none."""
    if tt is None:
        return None
    g = tt.group if tt.group is not None else _other_group(object_session(tt))
    return normalise_rule_note(g.rule_note) if g is not None else None


def default_group(db, body_name: str):
    """The group a NEW body lands in when nobody picked one (RT3_RULING_1 Q8: a new body never lands grey by
    accident): the family its name suggests (FAMILY_KEYWORDS), else OTHER. None when neither group exists."""
    from ..database import TrailerGroup
    from sqlalchemy import func
    for name in (guess_family_name(body_name), FALLBACK_NAME):
        g = (db.query(TrailerGroup).filter(func.upper(TrailerGroup.name) == name)
             .order_by(TrailerGroup.id).first())
        if g is not None:
            return g
    return None
