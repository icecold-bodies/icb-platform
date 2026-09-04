r"""
tools/icecream_floor_ply_raw_price.py  (v2 — target-state reconciler)
─────────────────────────────────────────────────────────────────────
FLOOR plywood on the icecream bodies (+ FREEZER MEDIUM, which shares the
material class): bring each line to Burt's September target —

  material named as the GRP sheet line, priced at the RAW PRICE-list value;
  the /2.98 nominal-sheet-area division carried in the line FORMULA;
  no unit-price override left on the line.

v1 assumed prod matched dev (same names, divided prices, no overrides) and
its guards refused prod's real state: the small body's line carries a manual
112.75 override (Michael's earlier hand-fix), and medium/large carry variant
material names — two of the deploy's 22 unmatched rows, still on pre-September
prices. v2 reconciles from ANY of those states and reports the cost effect per
line (for the small body the cost is identity-invariant; for stale lines this
COMPLETES the September price, moving the line to Burt's H).

Burt targets (September workbook, decoded):
  tid 16 ICECREAM SMALL  FLOOR '12MM PF PLYWOOD'  C8 =336  H=787.85
  tid 17 ICECREAM MEDIUM FLOOR '12MM PF PLYWOOD'  C14=665  H=2805.61
  tid 18 ICECREAM LARGE  FLOOR '18 MM PF PLYWOOD' C15=798  H=4790.01
  tid 20 FREEZER MEDIUM  FLOOR '12MM PF PLYWOOD'  C14=665  H=3215.10 (row 147)

Matching: the ONE non-option FLOOR line on the trailer whose material name
contains 'PLY' (any variant spelling). Zero or several candidates, or a
formula that is not the length x width area shape → refused + reported,
nothing guessed. Material updated IN PLACE only when every reference to it is
inside this spec set and it already carries the target name; otherwise the
line is REPOINTED to a found-or-created (target name, raw price) material —
prod's variant-named materials are left behind untouched (reported).

Modes: dry-run (default) / --apply (journaled) / --revert J.json / --verify.
Delta-driven and idempotent (dev, already at target, reports zero deltas).
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
AREA = 2.98

#: tid -> (target material name, raw September price, Burt H at sheet dims,
#:         verify Burt-H strictly?)
SPEC = {
    16: ("12MM PF PLYWOOD", 336.0, 787.852349, True),
    17: ("12MM PF PLYWOOD", 665.0, 2805.608221, True),
    18: ("18 MM PF PLYWOOD", 798.0, 4790.008389, True),
    # FREEZER MEDIUM: engine-verify is structural (unit + formula) — its MES
    # default dims are not asserted equal to the sheet's floor dims.
    20: ("12MM PF PLYWOOD", 665.0, 3215.096477, False),
}
VERIFY_DIMS = {16: (3.2, 2.1, 2.0), 17: (5.3, 2.3, 2.2), 18: (6.7, 2.6, 2.3),
               20: (5.3, 2.3, 2.2)}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").upper().strip())


def ensure_div(f: str) -> str:
    f = (f or "1").strip()
    if re.search(r"/\s*2\.98\s*$", f):
        return f
    return f"({f})/2.98"


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
            for ln in j["lines"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET material_id=:m, formula_expression=:f, "
                    "unit_price_override=:o, price_updated_at=:t WHERE id=:i"),
                    {"m": ln["before"]["material_id"], "f": ln["before"]["formula"],
                     "o": ln["before"]["override"],
                     "t": ln["before"]["price_updated_at"], "i": ln["bom_id"]})
            for m in j.get("materials_inplace", []):
                conn.execute(sa.text(
                    "UPDATE materials SET price_per_unit=:p, last_updated=:t WHERE id=:i"),
                    {"p": m["before"]["price"], "t": m["before"]["last_updated"], "i": m["id"]})
            for ph in j["price_history_ids"]:
                conn.execute(sa.text("DELETE FROM price_history WHERE id=:i"), {"i": ph})
            for oh in j["override_history_ids"]:
                conn.execute(sa.text("DELETE FROM bom_override_history WHERE id=:i"), {"i": oh})
            for mc in j["materials_created"]:
                n = conn.execute(sa.text(
                    "SELECT COUNT(*) FROM bill_of_materials WHERE material_id=:i"),
                    {"i": mc["id"]}).scalar()
                if n:
                    raise SystemExit(f"revert: created material {mc['id']} still referenced — abort")
                conn.execute(sa.text("DELETE FROM materials WHERE id=:i"), {"i": mc["id"]})
        print(f"reverted {args.revert}")
        return 0

    if args.verify:
        return verify(args.db)

    with eng.begin() as conn:
        mats = {r.id: dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT id, name, category_id, unit_of_measure, price_per_unit, supplier, "
            "material_code, sap_code, size, manufacture_sub_category, is_active, "
            "last_updated FROM materials"))}
        found, problems = {}, []
        for tid, (tname_target, raw, _h, _strict) in SPEC.items():
            rows = conn.execute(sa.text("""
                SELECT b.id AS bom_id, b.material_id, b.formula_expression,
                       b.unit_price_override, b.price_updated_at,
                       m.name AS mat, t.name AS tname
                FROM bill_of_materials b
                JOIN materials m ON m.id=b.material_id
                JOIN trailer_types t ON t.id=b.trailer_type_id
                WHERE b.trailer_type_id=:t AND b.bom_section='FLOOR'
                  AND NOT COALESCE(b.is_body_option, FALSE)
                  AND UPPER(m.name) LIKE '%PLY%'"""),
                {"t": tid}).mappings().all()
            if len(rows) != 1:
                problems.append(f"trailer {tid}: {len(rows)} FLOOR plywood candidates "
                                f"({[r['mat'] for r in rows]}) — refused")
                continue
            r = rows[0]
            f = (r["formula_expression"] or "").strip()
            at_target_f = bool(re.search(r"/\s*2\.98\s*$", f))
            base_ok = ("length" in f and "width" in f)
            if not (base_ok or at_target_f):
                problems.append(f"trailer {tid} bom={r['bom_id']}: formula {f!r} is not the "
                                f"length x width area shape — refused")
                continue
            found[tid] = r

        spec_boms = {r["bom_id"] for r in found.values()}
        deltas, journal_prep = [], []
        for tid, r in found.items():
            tname_target, raw, _h, _strict = SPEC[tid]
            mat = mats[r["material_id"]]
            cur_eff = r["unit_price_override"] if r["unit_price_override"] is not None \
                else mat["price_per_unit"]
            target_f = ensure_div(r["formula_expression"])
            name_ok = norm(mat["name"]) == norm(tname_target)
            price_ok = abs(mat["price_per_unit"] - raw) < 0.005
            f_ok = norm(target_f) == norm(r["formula_expression"] or "")
            ovr_ok = r["unit_price_override"] is None
            if name_ok and price_ok and f_ok and ovr_ok:
                continue
            refs = conn.execute(sa.text(
                "SELECT id FROM bill_of_materials WHERE material_id=:m"),
                {"m": r["material_id"]}).scalars().all()
            outside = [x for x in refs if x not in spec_boms]
            inplace = name_ok and not outside
            deltas.append({
                "tid": tid, "tname": r["tname"], "bom_id": r["bom_id"],
                "cur_mat_id": r["material_id"], "cur_mat_name": mat["name"],
                "cur_eff": cur_eff, "target_name": tname_target, "raw": raw,
                "target_eff": raw / AREA,
                "formula_before": r["formula_expression"], "formula_after": target_f,
                "override_before": r["unit_price_override"],
                "price_updated_at_before": (r["price_updated_at"].isoformat()
                                            if r["price_updated_at"] else None),
                "disposition": "IN_PLACE" if inplace else "REPOINT",
                "outside_refs": len(outside),
            })

        print(f"floor plywood reconcile: {len(deltas)} line deltas, {len(problems)} notes")
        for d in deltas:
            cost_note = ("cost unchanged" if abs(d["cur_eff"] - d["target_eff"]) < 0.01
                         else f"EFFECTIVE PRICE {round(d['cur_eff'],4)} -> "
                              f"{round(d['target_eff'],4)} (completes the September row)")
            print(f"  bom={d['bom_id']} {d['tname']!r}: {d['cur_mat_name']!r} -> "
                  f"{d['target_name']!r} @ R{d['raw']} [{d['disposition']}"
                  + (f", {d['outside_refs']} outside refs stay on the old material" if d["disposition"] == "REPOINT" and d["outside_refs"] else "")
                  + f"] — {cost_note}")
            if norm(d["formula_after"]) != norm(d["formula_before"] or ""):
                print(f"      formula {d['formula_before']!r} -> {d['formula_after']!r}")
            if d["override_before"] is not None:
                print(f"      override {d['override_before']} cleared (price lives on the material)")
        for p in problems:
            print(f"  NOTE: {p}")

        if not args.apply:
            print("(DRY RUN — nothing written. --apply to commit, then --verify.)")
            return 0
        if not deltas:
            print("nothing to apply.")
            return 0

        batch = datetime.now(timezone.utc)
        journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE, "lines": [],
                   "materials_inplace": [], "materials_created": [],
                   "price_history_ids": [], "override_history_ids": []}
        pool = {}
        for mid in sorted(mats):
            m = mats[mid]
            key = (norm(m["name"]), round(m["price_per_unit"], 4)
                   if m["price_per_unit"] is not None else None)
            if m["is_active"] and key not in pool:
                pool[key] = mid
        for d in deltas:
            if d["disposition"] == "IN_PLACE":
                mid = d["cur_mat_id"]
                m = mats[mid]
                journal["materials_inplace"].append({
                    "id": mid, "before": {"price": m["price_per_unit"],
                                          "last_updated": (m["last_updated"].isoformat()
                                                           if m["last_updated"] else None)}})
                conn.execute(sa.text(
                    "UPDATE materials SET price_per_unit=:p, last_updated=:now WHERE id=:i"),
                    {"p": d["raw"], "now": batch, "i": mid})
                phid = conn.execute(sa.text("""
                    INSERT INTO price_history (material_id, old_price, new_price,
                                               changed_date, changed_by)
                    VALUES (:m, :o, :n, :now, :who) RETURNING id"""),
                    {"m": mid, "o": m["price_per_unit"], "n": d["raw"],
                     "now": batch, "who": BATCH_NOTE}).scalar()
                journal["price_history_ids"].append(phid)
            else:
                key = (norm(d["target_name"]), round(d["raw"], 4))
                mid = pool.get(key)
                if mid is None:
                    tpl = mats[d["cur_mat_id"]]
                    mid = conn.execute(sa.text("""
                        INSERT INTO materials (name, category_id, unit_of_measure,
                                               price_per_unit, supplier, material_code,
                                               sap_code, size, manufacture_sub_category,
                                               is_active, last_updated,
                                               last_bulk_update_at, last_bulk_update_note)
                        VALUES (:n, :c, :u, :p, :s, :mc, :sc, :sz, :ms, TRUE, :now,
                                :now, :note) RETURNING id"""),
                        {"n": d["target_name"], "c": tpl["category_id"],
                         "u": tpl["unit_of_measure"], "p": d["raw"], "s": tpl["supplier"],
                         "mc": tpl["material_code"], "sc": tpl["sap_code"],
                         "sz": tpl["size"], "ms": tpl["manufacture_sub_category"],
                         "now": batch, "note": BATCH_NOTE}).scalar()
                    pool[key] = mid
                    journal["materials_created"].append({"id": mid, "name": d["target_name"],
                                                         "price": d["raw"]})
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET material_id=:m, formula_expression=:f, "
                "unit_price_override=NULL, price_updated_at=:now WHERE id=:i"),
                {"m": mid, "f": d["formula_after"], "now": batch, "i": d["bom_id"]})
            if d["override_before"] is not None or \
                    abs(d["cur_eff"] - d["target_eff"]) >= 0.01:
                ohid = conn.execute(sa.text("""
                    INSERT INTO bom_override_history
                        (bom_id, material_id, trailer_type_id, trailer_type_name,
                         material_name, old_price, new_price, changed_at, batch_at)
                    VALUES (:b, :m, :t, :tn, :mn, :o, NULL, :now, :now) RETURNING id"""),
                    {"b": d["bom_id"], "m": mid, "t": d["tid"], "tn": d["tname"],
                     "mn": d["target_name"], "o": d["override_before"],
                     "now": batch}).scalar()
                journal["override_history_ids"].append(ohid)
            journal["lines"].append({"bom_id": d["bom_id"],
                                     "before": {"material_id": d["cur_mat_id"],
                                                "formula": d["formula_before"],
                                                "override": d["override_before"],
                                                "price_updated_at": d["price_updated_at_before"]}})
        ts = batch.strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"floor_ply_raw_journal_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str))
        print(f"APPLIED. lines={len(journal['lines'])}, "
              f"in-place mats={len(journal['materials_inplace'])}, "
              f"created mats={len(journal['materials_created'])}, journal: {jpath}")
    return 0


def _bootstrap_app_path() -> None:
    """Make the `app` package importable no matter where this file runs from —
    the repo (backend/tools/…) or the VM staging copy in /tmp (the wrapper
    cd's to /opt/icb-platform/backend first)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.getcwd(), "/opt/icb-platform/backend", here):
        if os.path.isdir(os.path.join(cand, "app")):
            sys.path.insert(0, cand)
            return
    raise SystemExit("cannot locate the app package — run from backend/ "
                     "(or via the VM wrapper, which cd's there)")


def verify(db_url: str) -> int:
    _bootstrap_app_path()
    os.environ["DATABASE_URL"] = db_url
    from app.database import SessionLocal, TrailerType, BillOfMaterial
    from app.routers.calculator import (_build_bom_items, _build_body_variables,
                                        _bom_load_options, get_formula_lib, get_global_vars)
    from app.formula_engine import calculate_bom

    db = SessionLocal()
    failures = 0
    try:
        for tid, (mname, raw, h, strict) in SPEC.items():
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=tid)
                    .options(*_bom_load_options()).all())
            L, W, H_ = VERIFY_DIMS[tid]
            dims = {"length": L, "width": float(tt.default_width or W),
                    "height": float(tt.default_height or H_), "floor_thickness": 0.06,
                    "panel_thickness": 0.042, "insulation_thickness": 0.06,
                    "num_axles": 2, "num_doors": 2}
            sel = {str(r.id): bool(r.body_option_default) for r in rows if r.is_body_option}
            items = _build_bom_items(rows, dims, {}, sel, db, trailer=tt,
                                     insulation_foam="32D")
            res = calculate_bom(items, dims, _build_body_variables(rows),
                                get_formula_lib(), get_global_vars())
            got = unit = None
            for it in res["items"]:
                if it.get("category") == "FLOOR" and \
                        norm(it.get("material")) == norm(mname):
                    got = round(float(it.get("line_cost") or 0), 2)
                    unit = it.get("unit_price")
            unit_ok = unit is not None and abs(unit - raw) < 0.005
            if strict:
                ok = unit_ok and got is not None and abs(got - round(h, 2)) <= 0.02
                exp = f"expected R{round(h, 2)} @ R{raw}"
            else:
                ok = unit_ok
                exp = f"expected unit R{raw} (structural; sheet H {round(h, 2)} at sheet dims)"
            failures += 0 if ok else 1
            print(f"  {tt.name!r} FLOOR {mname!r}: line R{got} @ unit R{unit}  {exp}  "
                  f"{'OK' if ok else '*** MISMATCH ***'}")
    finally:
        db.close()
    print(f"verify: {'ALL OK' if failures == 0 else f'{failures} MISMATCHES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
