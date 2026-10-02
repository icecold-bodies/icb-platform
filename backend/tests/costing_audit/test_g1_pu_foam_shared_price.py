"""RT2 G1 — every ACTIVE PU foam cost line follows the shared PU price and works out its own volume.

Burt's model (RT2_DISPATCH Part 3, ratified): the shared PU foam material holds his price (R4 100 = 32D), each
line's formula works out the volume from the panel's thickness (his row term for term, /2.98), and the quote's
foam grade applies 4G. A line with its OWN price ignores the shared one (RT1 found 57); a line with no thickness
term counts sheets at a per-m3 price (how the MEAT HANGERs reached R343k). Either is a pricing defect.

This guard reads the COMMITTED prod snapshot (tests/costing_audit/mes_snapshot/all.json — RT2 R8: the 15 bodies
that carry PU foam lines, all 86 active ones). It fails when an active PU foam line (material named PU / PU
FOAM, not a body option, on an active body) carries its own price or has no {SEC PU} term — unless it is:

  * a NAMED EXCEPTION, ratified by the BA (RT2_RULING_1 R8): the 18 chiller PU lines — PU is not offered on
    chillers (Burt, 1 Oct); the drafts no longer show it, so the lines are unreachable and left as they are;
  * PENDING Manifest P: until the snapshot is re-taken after the v1.59.3 window, P's lines may still sit at
    EXACTLY P's guard values (manifest_p.yaml `current`). A line half-way (formula moved, own price not, or
    the other way round) fails, and so does any line P does not name. The allowance is removed with the
    post-window snapshot (RT2 close).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "mes_snapshot" / "all.json"
MANIFEST_P = HERE.parents[2] / "docs" / "audit" / "rt2_2026-10" / "manifest_p" / "manifest_p.yaml"
PU_FOAM = ("PU", "PU FOAM")
TOKEN = re.compile(r"\{\s*(FRONT|DRD|SRD|SIDES|ROOF|FLOOR)\s+PU\s*\}", re.I)
RT2_BODIES = {12, 15, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 34, 36, 37}

# RT2_RULING_1 R8 — "PU not offered on chillers, Burt 1 Oct". bom id -> body.
EXCEPTIONS = {
    3692: "CHILLER 2.3 METER", 3699: "CHILLER 2.3 METER", 3723: "CHILLER 2.3 METER",
    3743: "CHILLER 2.3 METER", 3751: "CHILLER 2.3 METER", 3759: "CHILLER 2.3 METER",
    3170: "CHILLER MEDIUM", 3179: "CHILLER MEDIUM", 3205: "CHILLER MEDIUM",
    3227: "CHILLER MEDIUM", 3237: "CHILLER MEDIUM", 3245: "CHILLER MEDIUM",
    3310: "CHILLER LARGE", 3319: "CHILLER LARGE", 3345: "CHILLER LARGE",
    3367: "CHILLER LARGE", 3377: "CHILLER LARGE", 3385: "CHILLER LARGE",
}


def _tables(path: Path = SNAPSHOT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["tables"]


def _pu_foam_lines(tables: dict) -> dict[int, dict]:
    mats = {m["id"]: m for m in tables["materials"]}
    tts = {t["id"]: t for t in tables["trailer_types"]}
    out = {}
    for b in tables["bill_of_materials"]:
        m = mats.get(b["material_id"]) or {}
        if (m.get("name") or "").strip().upper() not in PU_FOAM or b["is_body_option"]:
            continue
        t = tts.get(b["trailer_type_id"]) or {}
        if t.get("is_active"):
            out[b["id"]] = dict(b, _body=t.get("name"))
    return out


def _violates(r: dict) -> list[str]:
    why = []
    if r["unit_price_override"] is not None:
        why.append(f"own price R{r['unit_price_override']}")
    if not TOKEN.search(r["formula_expression"] or ""):
        why.append(f"no thickness term in `{r['formula_expression']}`")
    return why


def _manifest_p() -> dict[int, dict[str, tuple]]:
    """bom id -> {field: (current, new)} from Manifest P."""
    out: dict[int, dict[str, tuple]] = {}
    for e in (yaml.safe_load(MANIFEST_P.read_text(encoding="utf-8")) or {}).get("changes") or []:
        out.setdefault(int(e["bom_id"]), {})[e["field"]] = (e["current"], e["new"])
    return out


def _pending(r: dict, p: dict[str, tuple]) -> bool:
    """The line sits at EXACTLY Manifest P's guard values — every field P names, none moved."""
    return bool(p) and all(r[f] == cur for f, (cur, _new) in p.items())


def test_the_snapshot_covers_every_body_with_pu_foam_lines():
    """R8 — the committed snapshot carries the 15 bodies, so G1 sees all 86 active PU foam lines."""
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert RT2_BODIES <= set(doc["trailer_ids"]), sorted(RT2_BODIES - set(doc["trailer_ids"]))
    assert len(_pu_foam_lines(doc["tables"])) == 86


def test_every_active_pu_foam_line_follows_the_shared_price():
    lines, p = _pu_foam_lines(_tables()), _manifest_p()
    failures = []
    for bid, r in sorted(lines.items()):
        why = _violates(r)
        if not why or bid in EXCEPTIONS:
            continue
        if bid in p and _pending(r, p[bid]):
            continue                                  # Manifest P pending — exactly at its guard
        failures.append(f"bom {bid} {r['_body']} {r['bom_section']}: " + "; ".join(why))
    assert not failures, "active PU foam lines off the shared price:\n  " + "\n  ".join(failures)


def test_the_exceptions_are_exactly_the_ratified_chiller_lines():
    """The list can never quietly cover another line: each exception is that chiller's PU foam line."""
    lines = _pu_foam_lines(_tables())
    for bid, body in EXCEPTIONS.items():
        assert bid in lines, f"exception bom {bid} is not an active PU foam line in the snapshot"
        assert lines[bid]["_body"] == body, (bid, lines[bid]["_body"], body)
    assert not set(EXCEPTIONS) & set(_manifest_p()), "an exception is also a Manifest P line"


def test_manifest_p_leaves_only_the_exceptions():
    """P is complete: with P's new values applied in memory, the only violators are the 18 chillers."""
    lines, p = _pu_foam_lines(_tables()), _manifest_p()
    for bid, fields in p.items():
        assert bid in lines, f"Manifest P names bom {bid}, not an active PU foam line in the snapshot"
        for f, (_cur, new) in fields.items():
            lines[bid][f] = new
        assert "unit_price_override" in fields, f"bom {bid}: P must remove the own price, every time"
    left = {bid for bid, r in lines.items() if _violates(r)}
    assert left == set(EXCEPTIONS), sorted(left ^ set(EXCEPTIONS))


def test_the_guard_catches_a_known_hit():
    """Negative control: an own price on a shared-price line, and a sheet-count formula, both fail."""
    lines = _pu_foam_lines(_tables())
    bid = next(b for b, r in lines.items() if b not in EXCEPTIONS and not _violates(r)
               and b not in _manifest_p())
    r = dict(lines[bid], unit_price_override=4100.0)
    assert _violates(r) and not _pending(r, _manifest_p().get(bid, {}))
    r = dict(lines[bid], formula_expression="1.22*2.44*2")
    assert any("no thickness term" in w for w in _violates(r))
