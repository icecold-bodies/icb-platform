"""RT1 — READ ONLY: price Manifest B's five single-rear-door PU lines through the engine against the database
AS IT IS, and compare each with Burt's row by hand.

For each body, a single-rear-door quote with SRD PU on at thickness T (the master's own thickness is 0 on
prod, so T rides as a body-variable override, as the calculator sends it), DRD sections excluded; and a
double-door quote (the SRD PU line must be excluded — its own rule is `SRD PU = Y`).

Burt (both MEAT HANGER sheets, row 46; and the F1 lines #197 proved): H = (1.22*2.44*T*C17/2.98)*(1.22*2.44)*2
with C17 = PU!C17 = 4100 (September PRICE list). Expected after Manifest B: the engine = Burt to the cent.

    (DATABASE_URL + SESSION_SECRET set; PYTHONPATH = backend/)  python verify_manifest_b.py [T ...]   (default 0.06 0.08)
"""
import sys

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import app.database as _db
from app.database import BillOfMaterial, TrailerType
from app.formula_engine import calculate_bom
from app.routers.calculator import (_apply_body_variable_overrides, _bom_load_options, _build_body_variables,
                                    _build_bom_items)
from app.services import get_formula_lib, get_global_vars, get_section_snapshot

LINES = {5851: 12, 6159: 36, 5585: 17, 2415: 20, 3576: 19}      # bom id -> body id
C17 = 4100.0


def burt(t):
    return round((1.22 * 2.44 * t * C17 / 2.98) * (1.22 * 2.44) * 2, 2)


def main(ts):
    eng = create_engine(_db.engine.url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    db = Session(bind=conn, autoflush=False)
    ok_all = True
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        print("database:", db.execute(text("select current_database()")).scalar(),
              "| read only:", db.execute(text("show transaction_read_only")).scalar())
        order = get_section_snapshot().order
        print(f"{'line':>5} {'body':<26} {'door':<4} {'T':>5} {'qty':>8} {'unit':>8} {'MES':>10} {'Burt':>10}  verdict")
        for bid, tid in LINES.items():
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
            rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                                     r.material.name.lower() if r.material else ""))
            m = {r.material.name: r.id for r in rows if r.is_body_option and r.material}
            dims = {"length": tt.default_length or 4.0, "width": tt.default_width or 2.4, "height": tt.default_height or 2.2}
            cases = [("DRD", ts[0])] + [("SRD", t) for t in ts]
            for door, t in cases:
                if door == "SRD":
                    sel = {str(m["DRD EPS"]): False, str(m["DRD PU"]): False, str(m["SRD EPS"]): False, str(m["SRD PU"]): True}
                    flags = {"DRD EPS": False, "DRD PU": False, "SRD EPS": False, "SRD PU": True}
                    excl, var = ["DRD", "DRD DOOR FITTINGS"], {"SRD PU": t}
                else:
                    sel = {str(m["DRD EPS"]): True, str(m["DRD PU"]): False, str(m["SRD EPS"]): False, str(m["SRD PU"]): False}
                    flags = {"DRD EPS": True, "DRD PU": False, "SRD EPS": False, "SRD PU": False}
                    excl, var = ["SRD", "SRD DOOR FITTINGS"], {"DRD EPS": t}
                items = _build_bom_items(rows, dims, {}, sel, db, excl, trailer=tt, flag_overrides=flags,
                                         include_all_items=False, user_excluded_bom_ids=[], optional_sections_enabled=[],
                                         formula_overrides=None, insulation_foam="32D")
                bv = _build_body_variables(rows)
                _apply_body_variable_overrides(bv, var)
                res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
                it = next((i for i in res["items"] if int(i.get("bom_id") or 0) == bid), None)
                cost = round(float(it.get("line_cost") or 0), 2) if it else None
                if door == "SRD":
                    want = burt(t)
                    good = it is not None and not it.get("excluded") and cost == want
                    qty = f"{float(it.get('quantity') or 0):8.4f}" if it else "-"
                    unit = f"{float(it.get('unit_price') or 0):8.2f}" if it else "-"
                    print(f"{bid:>5} {tt.name:<26} SRD  {t:>5} {qty} {unit} {cost if cost is not None else '-':>10} {want:>10.2f}  "
                          f"{'OK' if good else '!! DIFFERS'}")
                else:
                    good = it is None or it.get("excluded") or cost == 0
                    print(f"{bid:>5} {tt.name:<26} DRD  {'-':>5} {'':>8} {'':>8} {cost if cost is not None else 'absent':>10} {'0':>10}  "
                          f"{'OK (not costed)' if good else '!! COSTED ON DRD'}")
                ok_all &= bool(good)
    finally:
        db.rollback()
        db.close()
        conn.close()
    print("ALL OK" if ok_all else "!! SOMETHING DIFFERS")
    return 0 if ok_all else 1


if __name__ == "__main__":
    # --c17=<price>: Burt's PU!C17 to compare with (default 4100, the September list). The formula-only
    # variant leaves every line on the material's price (R4 095 since 29 Sep = Burt's 21 Sep list): --c17=4095.
    args = []
    for a in sys.argv[1:]:
        if a.startswith("--c17="):
            C17 = float(a.split("=", 1)[1])
        else:
            args.append(float(a))
    print(f"Burt's PU!C17 = {C17:g}")
    sys.exit(main(args or [0.06, 0.08]))
