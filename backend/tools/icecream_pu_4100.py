r"""
tools/icecream_pu_4100.py
─────────────────────────
Re-anchor the ICECREAM bodies' PU insulation lines on the RAW September sheet
price (R4100 = PRICE 2017 MARCH.xlsx, PU!C17) with quantity formulas that
mirror Burt's workbook rows term-for-term (Michael, 4 Sep — after the SIDES/
FLOOR pilot on ICECREAM BODY SMALL).

Per Burt's September sheets, decoded row-by-row (formulas + cached values):

  H = G x F x I x C   where G = 1.22*2.44*<thickness>*4100/2.98
    * length-driven rows (SIDES/ROOF/FLOOR): C = (C4 + 0.05) / 1.22 sheets
    * fixed rows (FRONT everywhere; DRD small+large; SRD medium): 2 sheets
    * unused rows (thickness 0, toggle N): SRD small+large, DRD medium —
      NOT TOUCHED by this tool.

MES translation, unit price R4100.00 on the line (the "EDIT permanently
(this section)" price), formula carrying everything else:

  length rows:  (1.22*2.44*{<SEC> PU}/2.98)*(1.22*2.44)*((length+{Waste})/1.22)
  2-sheet rows: (1.22*2.44*{<SEC> PU}/2.98)*(1.22*2.44)*2

The {<SEC> PU} thickness variables are synced to Burt's C-cells where they
differ (that IS the September sheet's data; without it the totals cannot land).
The SIDES section's x2 multiplier stays the both-sides doubling (Burt's K
column); FRONT's "2" is a SHEET COUNT inside the quantity, not a section
multiplier.

Modes: dry-run (default) / --apply (one transaction, journaled) /
--revert J.json / --verify (real engine per body: PU radios selected per the
sheet's toggles, each PU line asserted against Burt's H x section multiplier).
Delta-driven: a second run finds nothing. Michael's manual pilot edits on
prod (SIDES/FLOOR of the small body) simply produce no delta.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

BATCH_NOTE = "September 2026 PU re-anchor R4100 (icecream bodies)"
PRICE = 4100.0
PU_NAMES = {"PU", "PU FOAM"}

# Generated from the September workbook (scripted read of C/F/G/H/I per PU row).
# expected_h is Burt's cached H at the sheet's own dims (C4 below) — the
# --verify mode asserts the engine reproduces it at the trailer's defaults.
SPEC = {
    # 'icecream up to 3,2' (C4=3.2, +0.05 waste) — prod name ICECREAM BODY SMALL
    16: {"_c4": 3.2, "_sheet": "icecream up to 3,2",
         "FRONT": dict(kind="sheets2", thickness=0.1, expected_h=2438.354818),
         "DRD": dict(kind="sheets2", thickness=0.1, expected_h=2438.354818),
         "SIDES": dict(kind="length", thickness=0.1, expected_h=3247.808671),
         "ROOF": dict(kind="length", thickness=0.1, expected_h=3247.808671),
         "FLOOR": dict(kind="length", thickness=0.1, expected_h=3247.808671)},
    # 'icecream up to 4.8' (C4=5.3) — prod name ICECREAM BODY MEDIUM
    17: {"_c4": 5.3, "_sheet": "icecream up to 4.8",
         "FRONT": dict(kind="sheets2", thickness=0.12, expected_h=2926.025781),
         "SRD": dict(kind="sheets2", thickness=0.12, expected_h=2926.025781),
         "SIDES": dict(kind="length", thickness=0.12, expected_h=6415.671283),
         "ROOF": dict(kind="length", thickness=0.145, expected_h=7752.269467),
         "FLOOR": dict(kind="length", thickness=0.145, expected_h=7752.269467)},
    # ' icecream 4.9 up' (C4=6.7) — prod name ICECREAM BODY LARGE
    18: {"_c4": 6.7, "_sheet": " icecream 4.9 up",
         "FRONT": dict(kind="sheets2", thickness=0.12, expected_h=2926.025781),
         "DRD": dict(kind="sheets2", thickness=0.12, expected_h=2926.025781),
         "SIDES": dict(kind="length", thickness=0.12, expected_h=8094.538534),
         "ROOF": dict(kind="length", thickness=0.125, expected_h=8431.810973),
         "FLOOR": dict(kind="length", thickness=0.1, expected_h=6745.448779)},
}


def target_formula(sec: str, kind: str) -> str:
    g = f"(1.22*2.44*{{{sec} PU}}/2.98)*(1.22*2.44)"
    return f"{g}*2" if kind == "sheets2" else f"{g}*((length+{{Waste}})/1.22)"


def normf(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def spec_selfcheck():
    """Every expected_h must be reproducible from (PRICE, thickness, kind, C4)."""
    for tid, body in SPEC.items():
        c4 = body["_c4"]
        for sec, s in body.items():
            if sec.startswith("_"):
                continue
            rate = 1.22 * 2.44 * s["thickness"] * PRICE / 2.98
            sheets = 2 if s["kind"] == "sheets2" else (c4 + 0.05) / 1.22
            h = rate * sheets * 2.9768
            if abs(h - s["expected_h"]) > 0.01:
                raise SystemExit(f"SPEC self-check failed {tid}/{sec}: {h} != {s['expected_h']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="JOURNAL_JSON")
    ap.add_argument("--verify", action="store_true",
                    help="engine check only: PU radios per the sheet's toggles, "
                         "assert every PU line equals Burt's H x section multiplier")
    args = ap.parse_args()
    if not args.db:
        raise SystemExit("no DATABASE_URL — refusing to guess a database.")
    spec_selfcheck()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    eng = sa.create_engine(args.db)

    if args.revert:
        with eng.begin() as conn:
            j = json.loads(Path(args.revert).read_text())
            for ln in j["lines"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET formula_expression=:f, "
                    "unit_price_override=:o, price_updated_at=:t WHERE id=:i"),
                    {"f": ln["before"]["formula"], "o": ln["before"]["override"],
                     "t": ln["before"]["price_updated_at"], "i": ln["bom_id"]})
            for v in j["vars"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET variable_value=:v WHERE id=:i"),
                    {"v": v["before"], "i": v["bom_id"]})
            for oh in j["override_history_ids"]:
                conn.execute(sa.text("DELETE FROM bom_override_history WHERE id=:i"), {"i": oh})
        print(f"reverted {args.revert}")
        return 0

    if args.verify:
        return verify(args.db)

    with eng.begin() as conn:
        deltas_line, deltas_var, problems = [], [], []
        for tid, body in SPEC.items():
            tname = conn.execute(sa.text(
                "SELECT name FROM trailer_types WHERE id=:t"), {"t": tid}).scalar()
            dflt_len = conn.execute(sa.text(
                "SELECT default_length FROM trailer_types WHERE id=:t"), {"t": tid}).scalar()
            if dflt_len is not None and abs(float(dflt_len) - body["_c4"]) > 1e-6:
                problems.append(f"trailer {tid} {tname!r}: default_length {dflt_len} != "
                                f"sheet C4 {body['_c4']} — formulas still correct (they "
                                f"scale with the typed length); --verify uses the default")
            for sec, s in body.items():
                if sec.startswith("_"):
                    continue
                rows = conn.execute(sa.text("""
                    SELECT b.id, b.formula_expression, b.unit_price_override,
                           b.price_updated_at, m.name AS mat
                    FROM bill_of_materials b JOIN materials m ON m.id=b.material_id
                    WHERE b.trailer_type_id=:t AND NOT COALESCE(b.is_body_option, FALSE)
                      AND b.bom_section=:s AND UPPER(BTRIM(m.name)) IN ('PU','PU FOAM')
                      AND b.body_option_linked = :lnk"""),
                    {"t": tid, "s": sec, "lnk": f"{sec} PU"}).mappings().all()
                if len(rows) != 1:
                    problems.append(f"trailer {tid} {tname!r} {sec}: {len(rows)} PU lines "
                                    f"linked to '{sec} PU' — skipped, nothing touched")
                    continue
                b = rows[0]
                tf = target_formula(sec, s["kind"])
                f_ok = normf(b["formula_expression"]) == normf(tf)
                p_ok = b["unit_price_override"] is not None and \
                    abs(b["unit_price_override"] - PRICE) < 0.005
                if not (f_ok and p_ok):
                    deltas_line.append({"tid": tid, "tname": tname, "sec": sec,
                                        "bom_id": b["id"], "formula_before": b["formula_expression"],
                                        "formula_after": tf,
                                        "override_before": b["unit_price_override"],
                                        "price_updated_at_before": (b["price_updated_at"].isoformat()
                                                                    if b["price_updated_at"] else None),
                                        "f_ok": f_ok, "p_ok": p_ok})
                vrow = conn.execute(sa.text("""
                    SELECT b.id, b.variable_value FROM bill_of_materials b
                    JOIN materials m ON m.id=b.material_id
                    WHERE b.trailer_type_id=:t AND b.is_body_option
                      AND UPPER(BTRIM(m.name)) = :n"""),
                    {"t": tid, "n": f"{sec} PU"}).mappings().all()
                if len(vrow) != 1:
                    problems.append(f"trailer {tid} {sec}: {len(vrow)} '{sec} PU' option rows")
                elif vrow[0]["variable_value"] is None or \
                        abs(float(vrow[0]["variable_value"]) - s["thickness"]) > 1e-9:
                    deltas_var.append({"tid": tid, "tname": tname, "sec": sec,
                                       "bom_id": vrow[0]["id"],
                                       "before": vrow[0]["variable_value"],
                                       "after": s["thickness"]})
        w = conn.execute(sa.text(
            "SELECT value FROM global_variables WHERE name='Waste'")).scalar()
        if w is None or abs(float(w) - 0.05) > 1e-9:
            problems.append(f"global {{Waste}} = {w!r}, expected 0.05 — Burt's +0.05 side "
                            f"length depends on it; totals will be off until it is 0.05")

        print(f"icecream PU re-anchor: {len(deltas_line)} line deltas, "
              f"{len(deltas_var)} thickness-variable deltas, {len(problems)} notes")
        for d in deltas_line:
            print(f"  line bom={d['bom_id']} {d['tname']!r} {d['sec']}: "
                  f"price {d['override_before']} -> {PRICE}"
                  + ("" if d["f_ok"] else f"\n        formula {d['formula_before']!r}\n"
                                          f"             -> {d['formula_after']!r}"))
        for d in deltas_var:
            print(f"  thickness bom={d['bom_id']} {d['tname']!r} {{{d['sec']} PU}}: "
                  f"{d['before']} -> {d['after']}")
        for p in problems:
            print(f"  NOTE: {p}")

        if not args.apply:
            print("(DRY RUN — nothing written. --apply to commit, then --verify.)")
            return 0
        if not (deltas_line or deltas_var):
            print("nothing to apply.")
            return 0

        batch = datetime.now(timezone.utc)
        journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE,
                   "lines": [], "vars": [], "override_history_ids": []}
        for d in deltas_line:
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET formula_expression=:f, "
                "unit_price_override=:p, price_updated_at=:now WHERE id=:i"),
                {"f": d["formula_after"], "p": PRICE, "now": batch, "i": d["bom_id"]})
            ohid = conn.execute(sa.text("""
                INSERT INTO bom_override_history
                    (bom_id, trailer_type_id, trailer_type_name, material_name,
                     old_price, new_price, changed_at, batch_at)
                VALUES (:b, :t, :tn, 'PU', :o, :n, :now, :now) RETURNING id"""),
                {"b": d["bom_id"], "t": d["tid"], "tn": d["tname"],
                 "o": d["override_before"], "n": PRICE, "now": batch}).scalar()
            journal["override_history_ids"].append(ohid)
            journal["lines"].append({"bom_id": d["bom_id"],
                                     "before": {"formula": d["formula_before"],
                                                "override": d["override_before"],
                                                "price_updated_at": d["price_updated_at_before"]}})
        for d in deltas_var:
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET variable_value=:v WHERE id=:i"),
                {"v": d["after"], "i": d["bom_id"]})
            journal["vars"].append({"bom_id": d["bom_id"], "before": d["before"],
                                    "after": d["after"]})
        ts = batch.strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"icecream_pu_4100_journal_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str))
        print(f"APPLIED. lines={len(journal['lines'])}, vars={len(journal['vars'])}, "
              f"journal: {jpath}")
    return 0


def verify(db_url: str) -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ["DATABASE_URL"] = db_url
    from app.database import SessionLocal, TrailerType, BillOfMaterial
    from app.routers.calculator import (_build_bom_items, _build_body_variables,
                                        _bom_load_options, get_formula_lib,
                                        get_global_vars, get_section_snapshot)
    from app.formula_engine import calculate_bom

    db = SessionLocal()
    failures = 0
    try:
        eng2 = sa.create_engine(db_url)
        with eng2.connect() as c:
            mult = {r.name: float(r.multiplier or 1.0) for r in
                    c.execute(sa.text("SELECT name, multiplier FROM bom_sections"))}
        for tid, body in SPEC.items():
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=tid)
                    .options(*_bom_load_options()).all())
            dims = {"length": body["_c4"], "width": float(tt.default_width or 2.1),
                    "height": float(tt.default_height or 2.0), "floor_thickness": 0.06,
                    "panel_thickness": 0.042, "insulation_thickness": 0.06,
                    "num_axles": 2, "num_doors": 2}
            used = {f"{s} PU" for s in body if not s.startswith("_")}
            sel = {}
            for r in rows:
                if not r.is_body_option:
                    continue
                nm = (r.material.name or "").strip().upper()
                if nm.endswith(" PU"):
                    sel[str(r.id)] = nm in used
                elif nm.endswith(" EPS"):
                    sel[str(r.id)] = nm.replace(" EPS", " PU") not in used
                else:
                    sel[str(r.id)] = bool(r.body_option_default)
            items = _build_bom_items(rows, dims, {}, sel, db, trailer=tt,
                                     insulation_foam="32D")
            res = calculate_bom(items, dims, _build_body_variables(rows),
                                get_formula_lib(), get_global_vars())
            print(f"\n{tt.name!r} @ length {body['_c4']} (sheet {body['_sheet']!r}):")
            for it in res["items"]:
                if (it.get("material") or "").strip().upper() not in PU_NAMES:
                    continue
                sec = it.get("category")
                s = body.get(sec)
                if s is None:
                    continue
                want = round(s["expected_h"] * mult.get(sec, 1.0), 2)
                got = round(float(it.get("line_cost") or 0), 2)
                ok = abs(got - want) <= 0.02
                failures += 0 if ok else 1
                print(f"  {sec:<6} PU: line R{got:>10.2f}  expected R{want:>10.2f} "
                      f"(Burt H {s['expected_h']:.2f} x{mult.get(sec, 1.0):g})  "
                      f"{'OK' if ok else '*** MISMATCH ***'}")
    finally:
        db.close()
    print(f"\nverify: {'ALL OK' if failures == 0 else f'{failures} MISMATCHES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
