"""
tools/september_impact_report.py
────────────────────────────────
Cost every September-affected MES body through the REAL calculation engine
(the same _build_bom_items -> calculate_bom path /api/calculate runs, with the
trailer's default dimensions and default body-option selections) and snapshot
the totals. Run once before the apply and once after, then join:

    DATABASE_URL=... python tools/september_impact_report.py --snapshot before.json
    ... apply ...
    DATABASE_URL=... python tools/september_impact_report.py --snapshot after.json
    python tools/september_impact_report.py --join before.json after.json \
        --out docs/audit/september_price_update/impact_report.csv

Each body is costed twice per snapshot: on 32D PU foam (the default every
costing opens on) and on 4G FOAM — the 4G columns show the ratio-change
effect (ratified default 7) that the 32D view cannot see.

Totals are the engine's grand_total: the summed included line costs at
default selections — no chassis, margin or ratio applied, so the deltas are
pure material-price effects. The BA formats the user-facing version.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The §3.2 import script owns the mapping; reuse it so the two can never drift.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "september_price_import",
    Path(__file__).resolve().parent / "september_price_import.py")
_imp = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_imp)
AFFECTED_TRAILER_IDS = sorted(set(_imp.SHEET_TO_TRAILER.values()))

_FALLBACK_DIMS = {
    "floor_thickness": 0.060,
    "panel_thickness": 0.042,
    "insulation_thickness": 0.060,
    "num_axles": 2,
    "num_doors": 2,
}


def snapshot(path: str):
    from app.database import SessionLocal, TrailerType, BillOfMaterial
    from app.routers.calculator import (_build_bom_items, _build_body_variables,
                                        _bom_load_options, get_formula_lib,
                                        get_global_vars, get_section_snapshot)
    from app.formula_engine import calculate_bom

    db = SessionLocal()
    out = {}
    try:
        formula_lib = get_formula_lib()
        global_vars = get_global_vars()
        section_order = get_section_snapshot().order
        for tid in AFFECTED_TRAILER_IDS:
            tt = db.query(TrailerType).filter_by(id=tid).first()
            if tt is None:
                continue
            bom_rows = (db.query(BillOfMaterial)
                        .filter_by(trailer_type_id=tid)
                        .options(*_bom_load_options()).all())

            def _sec_key(r):
                name = r.bom_section or (r.material.category.name
                                         if r.material and r.material.category else "")
                return (section_order.get(name, 99998), name.lower(),
                        r.material.name.lower() if r.material else "")
            bom_rows.sort(key=_sec_key)

            dims = {
                "length": float(tt.default_length or 7.5),
                "width": float(tt.default_width or 2.6),
                "height": float(tt.default_height or 2.6),
                **_FALLBACK_DIMS,
            }
            body_opt_sel = {str(r.id): bool(r.body_option_default)
                            for r in bom_rows if r.is_body_option}
            body_vars = _build_body_variables(bom_rows)

            totals = {}
            for foam in ("32D", "4G"):
                items = _build_bom_items(bom_rows, dims, {}, body_opt_sel, db,
                                         trailer=tt, insulation_foam=foam)
                result = calculate_bom(items, dims, body_vars, formula_lib, global_vars)
                totals[foam] = round(float(result.get("grand_total") or 0.0), 2)
            out[str(tid)] = {"name": tt.name, "active": bool(tt.is_active), **totals}
            print(f"  {tt.name:<40} 32D={totals['32D']:>12.2f}  4G={totals['4G']:>12.2f}")
    finally:
        db.close()
    Path(path).write_text(json.dumps(out, indent=2))
    print(f"snapshot -> {path} ({len(out)} bodies)")


def join(before_path: str, after_path: str, out_csv: str):
    before = json.loads(Path(before_path).read_text())
    after = json.loads(Path(after_path).read_text())
    rows = []
    for tid, b in sorted(before.items(), key=lambda kv: kv[1]["name"]):
        a = after.get(tid)
        if a is None:
            continue
        r = {"body": b["name"], "active": b["active"],
             "old_total": b["32D"], "new_total": a["32D"],
             "delta_r": round(a["32D"] - b["32D"], 2),
             "delta_pct": round((a["32D"] / b["32D"] - 1) * 100, 2) if b["32D"] else "",
             "old_total_4g": b["4G"], "new_total_4g": a["4G"],
             "delta_r_4g": round(a["4G"] - b["4G"], 2),
             "delta_pct_4g": round((a["4G"] / b["4G"] - 1) * 100, 2) if b["4G"] else ""}
        rows.append(r)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"impact report -> {out_csv} ({len(rows)} bodies)")
    for r in rows:
        print(f"  {r['body']:<40} {r['old_total']:>12.2f} -> {r['new_total']:>12.2f} "
              f"({r['delta_r']:>+11.2f}, {r['delta_pct']:>+6.2f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", metavar="OUT_JSON")
    ap.add_argument("--join", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--out", default="impact_report.csv")
    args = ap.parse_args()
    if args.snapshot:
        snapshot(args.snapshot)
    elif args.join:
        join(args.join[0], args.join[1], args.out)
    else:
        ap.error("--snapshot or --join required")


if __name__ == "__main__":
    main()
