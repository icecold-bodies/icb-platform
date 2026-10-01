"""READ ONLY on the mirror (= prod's 1b data + Manifest A): every PU panel line of the two MEAT HANGERs, priced through
the engine at the body's default size with that side's PU master selected (thickness 0.06 m, the carry default),
against the same quantity at the pre-29 Sep per-sheet material prices (the 28 Sep snapshot)."""
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import app.database as _db
from app.database import BillOfMaterial, TrailerType
from app.formula_engine import calculate_bom
from app.routers.calculator import _apply_body_variable_overrides, _bom_load_options, _build_body_variables, _build_bom_items
from app.services import get_formula_lib, get_global_vars, get_section_snapshot

OLD = {r["id"]: r["price_per_unit"] for r in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["tables"]["materials"]}
eng = create_engine(_db.engine.url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})
event.listen(eng, "connect", _db._set_search_path)
conn = eng.connect()
db = Session(bind=conn, autoflush=False)
db.execute(text("SET TRANSACTION READ ONLY"))
order = get_section_snapshot().order
for tid in (12, 36):
    tt = db.query(TrailerType).filter_by(id=tid).first()
    rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
    rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(), r.material.name.lower() if r.material else ""))
    m = {r.material.name: r.id for r in rows if r.is_body_option and r.material}
    dims = {"length": tt.default_length or 4.0, "width": tt.default_width or 2.4, "height": tt.default_height or 2.2}
    print(f"\n{tt.name} at {dims}")
    total_now = total_then = 0.0
    for side in ("FRONT", "SIDES", "ROOF", "FLOOR", "DRD", "SRD"):
        pu, eps = f"{side} PU", f"{side} EPS"
        if pu not in m:
            continue
        sel = {str(v): False for k, v in m.items() if k.endswith(" EPS") or k.endswith(" PU")}
        sel[str(m[pu])] = True
        flags = {k: (k == pu) for k in m if k.endswith(" EPS") or k.endswith(" PU")}
        excl = ["DRD", "DRD DOOR FITTINGS"] if side == "SRD" else ["SRD", "SRD DOOR FITTINGS"]
        items = _build_bom_items(rows, dims, {}, sel, db, excl, trailer=tt, flag_overrides=flags, include_all_items=False,
                                 user_excluded_bom_ids=[], optional_sections_enabled=[], formula_overrides=None, insulation_foam="32D")
        bv = _build_body_variables(rows)
        _apply_body_variable_overrides(bv, {pu: 0.06})
        res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
        for it in res["items"]:
            r = next((x for x in rows if x.id == int(it.get("bom_id") or 0)), None)
            if not r or r.is_body_option or not r.material or r.material.name != "PU" or r.bom_section != side or it.get("excluded"):
                continue
            q, u, c = float(it.get("quantity") or 0), float(it.get("unit_price") or 0), float(it.get("line_cost") or 0)
            then = q * (r.unit_price_override if r.unit_price_override is not None else (OLD.get(r.material_id) or 0))
            total_now += c; total_then += then
            print(f"   {side:<6} bom {r.id:>5}  qty {q:8.4f}  unit R{u:>8.2f}  now R{c:>10,.2f}  |  at 28 Sep prices R{then:>9,.2f}  "
                  f"({'own' if r.unit_price_override is not None else 'material'} {r.formula_expression})")
    print(f"   all six PU panels: now R{total_now:,.2f}  vs  R{total_then:,.2f} at the 28 Sep per-sheet prices")
db.rollback(); db.close(); conn.close()
