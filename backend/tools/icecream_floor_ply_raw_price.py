r"""
tools/icecream_floor_ply_raw_price.py
─────────────────────────────────────
FLOOR plywood on the icecream bodies: put the RAW September PRICE-list value
back on the MATERIAL and move Burt's /2.98 (nominal 1.22x2.44 sheet area) into
the line FORMULA (Michael, 4 Sep — follow-on to the PU R4100 re-anchor).

Burt's G-cells (September workbook, decoded):
  icecream small  FLOOR '12MM PF PLYWOOD'  = PLYWOODS+TIMBER!C8  /2.98  (C8  = 336, "9 MM PF")
  icecream medium FLOOR '12MM PF PLYWOOD'  = PLYWOODS+TIMBER!C14 /2.98  (C14 = 665, "9MM BIRCH PLYWOOD")
  icecream large  FLOOR '18 MM PF PLYWOOD' = PLYWOODS+TIMBER!C15 /2.98  (C15 = 798, "12MM BIRCH PLY")
(The GRP line names deliberately do not match the PRICE-list row names —
confirmed with Michael; not this tool's problem.)

Transformation per material: price_per_unit -> the raw C-value; every line
referencing that material gets "/2.98" appended to its quantity formula. The
line cost is IDENTITY-invariant: (raw price) x (area/2.98) == (raw/2.98) x
area. The tool refuses any material whose current price is not raw/2.98
within a cent (that would mean the state has drifted and the identity would
not hold), and refuses any referencing formula that already carries /2.98.

Sharing closure: material #1040-equivalent (medium's plywood) is also used by
FREEZER MEDIUM's FLOOR line — that line is included in the same run, or the
price restore would inflate it x2.98. Every referencing line found on ANY
body is either transformed or the whole material is refused; nothing is left
half-done.

Modes: dry-run (default) / --apply (journaled) / --revert J.json / --verify
(engine: the three icecream lines must equal Burt's cached H to the cent).
Delta-driven and idempotent.
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

BATCH_NOTE = "September 2026 — floor plywood raw sheet price, /2.98 in formula"

#: (trailer_id, material name on the FLOOR line) -> raw September PRICE-list value
SPEC = {
    16: ("12MM PF PLYWOOD", 336.0, 787.852349),    # Burt H132, sheet 'icecream up to 3,2'
    17: ("12MM PF PLYWOOD", 665.0, 2805.608221),   # Burt H140, sheet 'icecream up to 4.8'
    18: ("18 MM PF PLYWOOD", 798.0, 4790.008389),  # Burt H140, sheet ' icecream 4.9 up'
}
AREA = 2.98


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="JOURNAL_JSON")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if not args.db:
        raise SystemExit("no DATABASE_URL — refusing to guess a database.")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    eng = sa.create_engine(args.db)

    if args.revert:
        with eng.begin() as conn:
            j = json.loads(Path(args.revert).read_text())
            for m in j["materials"]:
                conn.execute(sa.text(
                    "UPDATE materials SET price_per_unit=:p, last_updated=:t WHERE id=:i"),
                    {"p": m["before"]["price"], "t": m["before"]["last_updated"], "i": m["id"]})
            for ln in j["lines"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET formula_expression=:f WHERE id=:i"),
                    {"f": ln["before"], "i": ln["bom_id"]})
            for ph in j["price_history_ids"]:
                conn.execute(sa.text("DELETE FROM price_history WHERE id=:i"), {"i": ph})
        print(f"reverted {args.revert}")
        return 0

    if args.verify:
        return verify(args.db)

    with eng.begin() as conn:
        mat_deltas, line_deltas, problems = [], [], []
        for tid, (mname, raw, _h) in SPEC.items():
            rows = conn.execute(sa.text("""
                SELECT b.id AS bom_id, m.id AS mid, m.name, m.price_per_unit,
                       m.last_updated, b.formula_expression, b.unit_price_override
                FROM bill_of_materials b JOIN materials m ON m.id=b.material_id
                WHERE b.trailer_type_id=:t AND b.bom_section='FLOOR'
                  AND NOT COALESCE(b.is_body_option, FALSE)
                  AND UPPER(BTRIM(m.name)) = :n"""),
                {"t": tid, "n": mname}).mappings().all()
            if len(rows) != 1:
                problems.append(f"trailer {tid}: {len(rows)} FLOOR lines named {mname!r} — skipped")
                continue
            r = rows[0]
            if r["unit_price_override"] is not None:
                problems.append(f"trailer {tid} bom={r['bom_id']}: carries a price override "
                                f"({r['unit_price_override']}) — refused, resolve first")
                continue
            already = abs(r["price_per_unit"] - raw) < 0.005
            divided_ok = abs(r["price_per_unit"] - raw / AREA) < 0.01
            if not (already or divided_ok):
                problems.append(f"trailer {tid} mat#{r['mid']} {mname!r}: current price "
                                f"{r['price_per_unit']} is neither {raw} nor {round(raw/AREA,4)} "
                                f"— drifted, refused (send to the CA)")
                continue
            # closure: every line referencing this material, on any body
            refs = conn.execute(sa.text("""
                SELECT b.id AS bom_id, b.trailer_type_id AS tid, t.name AS tname,
                       b.bom_section, b.formula_expression
                FROM bill_of_materials b LEFT JOIN trailer_types t ON t.id=b.trailer_type_id
                WHERE b.material_id=:m AND NOT COALESCE(b.is_body_option, FALSE)"""),
                {"m": r["mid"]}).mappings().all()
            ok = True
            for ref in refs:
                has_div = re.search(r"/\s*2\.98\s*$", (ref["formula_expression"] or "").strip())
                if already and not has_div:
                    problems.append(f"mat#{r['mid']} already raw but bom={ref['bom_id']} "
                                    f"({ref['tname']}/{ref['bom_section']}) lacks /2.98 — "
                                    f"inconsistent state, refused")
                    ok = False
                if (not already) and has_div:
                    problems.append(f"mat#{r['mid']} still divided but bom={ref['bom_id']} "
                                    f"already has /2.98 — inconsistent state, refused")
                    ok = False
            if not ok or already:
                continue
            mat_deltas.append({"id": r["mid"], "name": r["name"],
                               "before_price": r["price_per_unit"], "after_price": raw,
                               "before_last_updated": (r["last_updated"].isoformat()
                                                       if r["last_updated"] else None)})
            for ref in refs:
                f = (ref["formula_expression"] or "1").strip()
                line_deltas.append({"bom_id": ref["bom_id"], "tid": ref["tid"],
                                    "tname": ref["tname"], "sec": ref["bom_section"],
                                    "before": ref["formula_expression"],
                                    "after": f"({f})/2.98"})

        print(f"floor plywood raw-price: {len(mat_deltas)} material deltas, "
              f"{len(line_deltas)} line-formula deltas, {len(problems)} notes")
        for d in mat_deltas:
            print(f"  material #{d['id']} {d['name']!r}: {d['before_price']} -> {d['after_price']}")
        for d in line_deltas:
            print(f"  line bom={d['bom_id']} {d['tname']!r} {d['sec']}: "
                  f"{d['before']!r} -> {d['after']!r}")
        for p in problems:
            print(f"  NOTE: {p}")

        if not args.apply:
            print("(DRY RUN — nothing written. --apply to commit, then --verify.)")
            return 0
        if not (mat_deltas or line_deltas):
            print("nothing to apply.")
            return 0

        batch = datetime.now(timezone.utc)
        journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE,
                   "materials": [], "lines": [], "price_history_ids": []}
        for d in mat_deltas:
            conn.execute(sa.text(
                "UPDATE materials SET price_per_unit=:p, last_updated=:now WHERE id=:i"),
                {"p": d["after_price"], "now": batch, "i": d["id"]})
            phid = conn.execute(sa.text("""
                INSERT INTO price_history (material_id, old_price, new_price, changed_date, changed_by)
                VALUES (:m, :o, :n, :now, :who) RETURNING id"""),
                {"m": d["id"], "o": d["before_price"], "n": d["after_price"],
                 "now": batch, "who": BATCH_NOTE}).scalar()
            journal["price_history_ids"].append(phid)
            journal["materials"].append({"id": d["id"],
                                         "before": {"price": d["before_price"],
                                                    "last_updated": d["before_last_updated"]}})
        for d in line_deltas:
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET formula_expression=:f WHERE id=:i"),
                {"f": d["after"], "i": d["bom_id"]})
            journal["lines"].append({"bom_id": d["bom_id"], "before": d["before"]})
        ts = batch.strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"floor_ply_raw_journal_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str))
        print(f"APPLIED. materials={len(journal['materials'])}, lines={len(journal['lines'])}, "
              f"journal: {jpath}")
    return 0


def verify(db_url: str) -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ["DATABASE_URL"] = db_url
    from app.database import SessionLocal, TrailerType, BillOfMaterial
    from app.routers.calculator import (_build_bom_items, _build_body_variables,
                                        _bom_load_options, get_formula_lib, get_global_vars)
    from app.formula_engine import calculate_bom

    dims_by_tid = {16: (3.2, 2.1, 2.0), 17: (5.3, 2.3, 2.2), 18: (6.7, 2.6, 2.3)}
    db = SessionLocal()
    failures = 0
    try:
        for tid, (mname, raw, h) in SPEC.items():
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=tid)
                    .options(*_bom_load_options()).all())
            L, W, H_ = dims_by_tid[tid]
            dims = {"length": L, "width": float(tt.default_width or W),
                    "height": float(tt.default_height or H_), "floor_thickness": 0.06,
                    "panel_thickness": 0.042, "insulation_thickness": 0.06,
                    "num_axles": 2, "num_doors": 2}
            sel = {str(r.id): bool(r.body_option_default) for r in rows if r.is_body_option}
            items = _build_bom_items(rows, dims, {}, sel, db, trailer=tt,
                                     insulation_foam="32D")
            res = calculate_bom(items, dims, _build_body_variables(rows),
                                get_formula_lib(), get_global_vars())
            got = None
            for it in res["items"]:
                if it.get("category") == "FLOOR" and \
                        (it.get("material") or "").strip().upper() == mname:
                    got = round(float(it.get("line_cost") or 0), 2)
                    unit = it.get("unit_price")
            want = round(h, 2)
            ok = got is not None and abs(got - want) <= 0.02 and abs(unit - raw) < 0.005
            failures += 0 if ok else 1
            print(f"  {tt.name!r} FLOOR {mname!r}: line R{got} @ unit R{unit} "
                  f" expected R{want} @ R{raw}  {'OK' if ok else '*** MISMATCH ***'}")
    finally:
        db.close()
    print(f"verify: {'ALL OK' if failures == 0 else f'{failures} MISMATCHES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
