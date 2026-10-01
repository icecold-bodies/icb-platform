"""RT1 — READ ONLY: Manifest M's 11 MEAT HANGER PU lines through the engine against the database AS IT IS, compared
with Burt's MEAT BODY / SMALL MEAT BODY UP TO 5,2 rows evaluated by hand (formula text read 30 Sep).

Both MEAT HANGERs at three lengths (LARGE 5.3 / 6.7 default / 8.4; SMALL-MEDIUM 2.7 / 5.2 / 5.8 default), default width
and height; DRD and SRD; EPS and PU; the quote's foam toggle at 32D and at 4G. PU thicknesses are the Body Template's
(LARGE: FRONT / SIDES / DRD 0.062, ROOF / FLOOR 0.1) or, where the template is on EPS (SMALL-MEDIUM), the EPS thickness
the calculator carries onto PU on the switch (FRONT / SIDES / DRD 0.06, ROOF / FLOOR 0.076); SRD takes the DRD one.

Burt, per panel (T = thickness, P = PU!C19 4G on FRONT / DRD / SIDES / ROOF / FLOOR, PU!C17 32D on SRD; N = sheets):
  FRONT / DRD / SRD:  (1.22*2.44*T*P/2.98)*(1.22*2.44)*2        (MEAT BODY FRONT divides by 2.99 — shown apart)
  SIDES (x2 sides):  2 * (1.22*2.44*T*P/2.98)*(1.22*2.44)*((L+0.05)/1.22)
  ROOF / FLOOR:      (1.22*2.44*T*P/2.98)*(1.22*2.44)*((L+0.05)/1.22)

Checks (the ruling's proof):
  * SRD (Burt's only 32D line) = MES at 32D to the cent, with P = R4 095;
  * each 4G panel: Burt with P = R4 095 x the STORED 4G factor = MES at 32D x that factor = MES at 4G, to the cent
    (the volume is term for term; MEAT BODY FRONT's /2.99 is the one sheet quirk, shown as its own ratio);
  * Burt's LATEST 4G price (R5 581) against the stored factor: reported (a price-update job owns the setting);
  * EPS quotes: no PU line is costed (the rear door carries no PU).
The 4G structural difference is shown: MES's 4G toggle also moves the SRD door's PU to 4G; Burt keeps SRD at 32D.

    (DATABASE_URL + SESSION_SECRET; PYTHONPATH = backend/)  python verify_manifest_m.py
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
from app.services import insulation_foam as pu_foam

P32 = 4095.0              # Burt's 21 Sep PU!C17 (32D) = the shared PU material
P4G_LATEST = 5581.0       # Burt's 21 Sep PU!C19 (4G)
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
        print("database:", db.execute(text("select current_database()")).scalar(),
              f"| stored 4G factor {factor!r} | Burt's latest 4G / 32D = {P4G_LATEST}/{P32} = {P4G_LATEST / P32!r}")
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
                        for foam in (("32D", "4G") if ins_kind == "PU" else ("32D",)):
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
                            tot_mes = tot_burt = tot_latest = 0.0
                            for bid, sec in by_id.items():
                                if sec in ("DRD", "SRD") and sec != door:
                                    continue
                                if cfg["lines"].get(sec) is None:
                                    continue
                                mes = costed.get(bid, 0.0)
                                T = cfg["T"][sec]
                                div = cfg["front_div"] if sec == "FRONT" else 2.98
                                if sec == "SRD":
                                    want = round(burt(sec, T, L, P32), 2) if foam == "32D" else round(burt(sec, T, L, P32) * factor, 2)
                                    latest = round(burt(sec, T, L, P32), 2)                      # Burt keeps SRD at 32D
                                else:
                                    base = burt(sec, T, L, P32 * (factor if foam == "4G" else 1.0), 2.98)
                                    want = round(base, 2)
                                    latest = round(burt(sec, T, L, P4G_LATEST, div), 2)           # the sheet as written
                                good = abs(mes - want) <= 0.01
                                ok_all &= good
                                tot_mes += mes; tot_burt += want; tot_latest += latest
                                quirk = f" (sheet /{div}: {latest:,.2f})" if div != 2.98 else ""
                                print(f"{label:<44} {sec:<6} bom {bid:>5} T={T:<6} MES {mes:>11,.2f}  expected {want:>11,.2f}  "
                                      f"{'OK' if good else '!! DIFFERS'}  | Burt's sheet at his latest prices {latest:>11,.2f}{quirk}")
                            print(f"{'':<44} TOTAL  MES {tot_mes:>11,.2f}  expected {tot_burt:>11,.2f}  | Burt's sheet {tot_latest:>11,.2f}"
                                  f"  ({(tot_mes / tot_latest - 1) * 100:+.2f} % vs the sheet)")
                            if tid == 36:   # 6229, SMALL-MEDIUM FLOOR PU — own R446.02, OUT of M: reported against Burt's row 148
                                i = next((i for i in res["items"] if int(i.get("bom_id") or 0) == 6229 and not i.get("excluded")), None)
                                mes6229 = round(float(i.get("line_cost") or 0), 2) if i else None
                                T = cfg["T"]["FLOOR"]
                                print(f"{'':<44} FLOOR  bom  6229 (own R446.02, OUT of M) T={T:<6} MES {mes6229}  | Burt row 148 at "
                                      f"32D {burt('FLOOR', T, L, P32):,.2f} · at his 4G {burt('FLOOR', T, L, P4G_LATEST):,.2f}")
    finally:
        db.rollback(); db.close(); conn.close()
    print("ALL OK" if ok_all else "!! SOMETHING DIFFERS")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
