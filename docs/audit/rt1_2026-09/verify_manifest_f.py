"""RT1 Manifest F — READ ONLY: after F (the stored 4G factor = Burt's 21 Sep 5 581 / 4 095), both MEAT HANGERs'
PU panels through the engine against Burt's MEAT BODY / SMALL MEAT BODY UP TO 5,2 rows at his 21 Sep prices, as his
sheet is written (RT1 ruling 2 §2a).

Same cases as verify_manifest_m.py: both MEAT HANGERs at three lengths (LARGE 5.3 / 6.7 default / 8.4; SMALL-MEDIUM
2.7 / 5.2 / 5.8 default), default width and height; DRD and SRD; EPS and PU; the quote's foam toggle at 32D and 4G;
the Body Template's PU thicknesses (SMALL-MEDIUM: the EPS thicknesses the calculator carries onto PU).

Burt, per panel (T = thickness, P = PU!C17 32D R4 095 or PU!C19 4G R5 581):
  FRONT / DRD / SRD:  (1.22*2.44*T*P/2.98)*(1.22*2.44)*2        (MEAT BODY FRONT divides by 2.99)
  SIDES (x2 sides):  2 * (1.22*2.44*T*P/2.98)*(1.22*2.44)*((L+0.05)/1.22)
  ROOF / FLOOR:      (1.22*2.44*T*P/2.98)*(1.22*2.44)*((L+0.05)/1.22)
His sheets price every MEAT panel at 4G except the single rear door (32D).

Checks:
  * the stored factor is exactly 5 581 / 4 095;
  * PU at 32D: every panel = Burt's row at R4 095, to the cent (F does not touch 32D);
  * PU at 4G: FRONT / DRD / SIDES / ROOF / FLOOR = Burt's row at R5 581, to the cent — as his sheet is written, except
    MEAT BODY FRONT's /2.99 (the ruling fixes /2.98): that one is shown with its ratio;
  * PU at 4G, SRD: the MES rule (the 32D price x the factor = R5 581) to the cent; Burt keeps SRD at 32D — the
    difference is the known structural one (RT1 ruling 2 §2b), shown in rand;
  * EPS quotes: no PU line is costed.

    (DATABASE_URL + SESSION_SECRET; PYTHONPATH = backend/)  [RT1_P32=4100] python verify_manifest_f.py
    RT1_P32 = the PU material's 32D price the check expects (default 4095, Manifest F; 4100 for F2).
"""
import os
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
from app.services import insulation_foam as pu_foam

P32 = float(os.environ.get("RT1_P32", "4095"))   # the shared PU material: 4095 under F, 4100 (Burt's corrected 32D) under F2
P4G = 5581.0              # Burt's 21 Sep PU!C19 (4G)
AREA = 1.22 * 2.44
BODIES = {
    12: dict(lengths=(5.3, 6.7, 8.4), T={"FRONT": 0.062, "SIDES": 0.062, "ROOF": 0.1, "FLOOR": 0.1, "DRD": 0.062, "SRD": 0.062},
             front_div=2.99, lines={"FRONT": 5842, "DRD": 5877, "SRD": 5851, "SIDES": 5899, "ROOF": 5910, "FLOOR": 5921}),
    36: dict(lengths=(2.7, 5.2, 5.8), T={"FRONT": 0.06, "SIDES": 0.06, "ROOF": 0.076, "FLOOR": 0.076, "DRD": 0.06, "SRD": 0.06},
             front_div=2.98, lines={"FRONT": 6150, "DRD": 6185, "SRD": 6159, "SIDES": 6207, "ROOF": 6218}),
}


def burt(section, T, L, price, div=2.98):
    g = AREA * T * price / div
    if section in ("FRONT", "DRD", "SRD"):
        return g * AREA * 2
    n = (L + 0.05) / 1.22
    return g * AREA * n * (2 if section == "SIDES" else 1)


def main():
    eng = create_engine(_db.engine.url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    db = Session(bind=conn, autoflush=False)
    ok_all = True
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        factor = pu_foam.get_4g_factor(db)
        good = factor == P4G / P32
        ok_all &= good
        print("database:", db.execute(text("select current_database()")).scalar(),
              f"| stored 4G factor {factor!r} | Burt's 21 Sep 4G / 32D = {P4G / P32!r}  {'OK' if good else '!! NOT F'}")
        order = get_section_snapshot().order
        for tid, cfg in BODIES.items():
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
            rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                                     r.material.name.lower() if r.material else ""))
            m = {r.material.name: r.id for r in rows if r.is_body_option and r.material}
            ins = [k for k in m if k.endswith(" EPS") or k.endswith(" PU")]
            by_id = {v: k for k, v in cfg["lines"].items()}
            for L in cfg["lengths"]:
                dims = {"length": L, "width": tt.default_width, "height": tt.default_height}
                for door in ("DRD", "SRD"):
                    for ins_kind in ("PU", "EPS"):
                        for foam in (("32D", "4G") if ins_kind == "PU" else ("4G",)):
                            sides = ["FRONT", "SIDES", "ROOF", "FLOOR", door]
                            on = {f"{s} {ins_kind}" for s in sides}
                            sel = {str(m[k]): (k in on) for k in ins}
                            flags = {k: (k in on) for k in ins}
                            var = {k: (cfg["T"][k.split()[0]] if k in on else 0.0) for k in ins if k.split()[0] in cfg["T"]}
                            excl = ["SRD", "SRD DOOR FITTINGS"] if door == "DRD" else ["DRD", "DRD DOOR FITTINGS"]
                            items = _build_bom_items(rows, dims, {}, sel, db, excl, trailer=tt, flag_overrides=flags,
                                                     include_all_items=False, user_excluded_bom_ids=[],
                                                     optional_sections_enabled=[], formula_overrides=None,
                                                     insulation_foam=foam)
                            bv = _build_body_variables(rows)
                            _apply_body_variable_overrides(bv, var)
                            res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
                            costed = {int(i.get("bom_id") or 0): round(float(i.get("line_cost") or 0), 2)
                                      for i in res["items"] if int(i.get("bom_id") or 0) in by_id and not i.get("excluded")}
                            label = f"{tt.name} L{L} {door} {ins_kind} {foam}"
                            if ins_kind == "EPS":
                                good = not any(costed.values())
                                ok_all &= good
                                print(f"{label:<44} PU lines costed: {costed or 'none'}  {'OK' if good else '!! PU COSTED ON AN EPS QUOTE'}")
                                continue
                            tot_mes = tot_sheet = 0.0
                            for bid, sec in by_id.items():
                                if sec in ("DRD", "SRD") and sec != door:
                                    continue
                                mes = costed.get(bid, 0.0)
                                T = cfg["T"][sec]
                                div = cfg["front_div"] if sec == "FRONT" else 2.98
                                if foam == "32D":
                                    want = round(burt(sec, T, L, P32), 2)
                                    sheet = want
                                    note = ""
                                elif sec == "SRD":
                                    want = round(burt(sec, T, L, P32) * factor, 2)          # the MES rule: SRD follows the toggle
                                    sheet = round(burt(sec, T, L, P32), 2)                  # Burt keeps SRD at 32D
                                    note = f"  | Burt's sheet keeps SRD at 32D: {sheet:,.2f} (MES {mes - sheet:+,.2f})"
                                else:
                                    want = round(burt(sec, T, L, P4G), 2)                    # Burt's row at R5 581, /2.98
                                    sheet = round(burt(sec, T, L, P4G, div), 2)              # as his sheet is written
                                    note = (f"  | Burt's sheet /{div}: {sheet:,.2f} (MES x {mes / sheet:.6f})" if div != 2.98
                                            else "  = Burt's sheet")
                                good = abs(mes - want) <= 0.01
                                ok_all &= good
                                tot_mes += mes; tot_sheet += sheet
                                print(f"{label:<44} {sec:<6} bom {bid:>5} T={T:<6} MES {mes:>11,.2f}  expected {want:>11,.2f}  "
                                      f"{'OK' if good else '!! DIFFERS'}{note}")
                            print(f"{'':<44} TOTAL  MES {tot_mes:>11,.2f}  | Burt's sheet {tot_sheet:>11,.2f}"
                                  f"  ({tot_mes - tot_sheet:+,.2f}, {(tot_mes / tot_sheet - 1) * 100:+.3f} %)")
    finally:
        db.rollback(); db.close(); conn.close()
    print("ALL OK" if ok_all else "!! SOMETHING DIFFERS")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
