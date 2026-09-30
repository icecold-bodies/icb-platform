"""RT1 Manifest F — the proof on the mirror, line by line and cell by cell (RT1 ruling 2 §2a).

    (DATABASE_URL = icb_prodmirror + SESSION_SECRET; PYTHONPATH = backend/)
    python f_linecheck.py capture <out.json> <report.json>...     READ ONLY: every scenario of the given audit reports,
                                                                   re-costed in-process from the exact payload the
                                                                   audit sent, with every line and section total
    python f_linecheck.py compare <before.json> <after.json>       the engine checks, from two captures
    python f_linecheck.py audit <before-report.json> <after-report.json> [...pairs]
                                                                   the audit's own cells, pack by pack

The engine checks (compare):
  * a 32D scenario: every line and every section total identical, field for field — F touches 4G quotes only;
  * a 4G scenario: every costed PU foam line (material PU / PU FOAM, insulation_foam.is_pu_foam_row) has its unit
    price x exactly new/old, and its line cost x the same ratio to the cent; every other line identical;
  * a 4G cell (scenario x section) moves by (ratio - 1) x its PU foam part, to the cent: a cell that is all PU foam
    moves by the ratio itself, a cell with no PU foam line does not move.
The audit check (audit): 32D cells identical (status, both totals); 4G cells: which moved, and every status change.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PU_NAMES = {"PU", "PU FOAM"}          # app/services/insulation_foam.py PU_FOAM_MATERIAL_NAMES


def _session():
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool
    import app.database as _db
    eng = create_engine(_db.engine.url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    db = Session(bind=conn, autoflush=False)
    db.execute(text("SET TRANSACTION READ ONLY"))
    name = db.execute(text("select current_database()")).scalar()
    if name != "icb_prodmirror":
        raise SystemExit(f"REFUSED: {name!r} is not the scratch mirror icb_prodmirror")
    return db, conn


def capture(out: Path, reports: list[Path]) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
    from app.services import insulation_foam as pu_foam
    from tools.costing_audit.mes_probe import MesProbe
    db, conn = _session()
    try:
        factor = pu_foam.get_4g_factor(db)
        probe = MesProbe(session=db, log=lambda *_: None)
        doc = {"factor": factor, "database": "icb_prodmirror", "scenarios": []}
        for rp in reports:
            rep = json.loads(rp.read_text(encoding="utf-8"))
            for s in rep["scenarios"]:
                sc, payload = s["scenario"], s["payload"]
                res = probe._in_process(payload)
                doc["scenarios"].append({
                    "pack": rep["pack"], "id": sc["id"], "foam": sc["foam"], "trailer_id": sc["trailer_id"],
                    "totals": res.get("category_totals") or {}, "grand_total": res.get("grand_total"),
                    "items": [{k: it.get(k) for k in ("bom_id", "category", "material", "quantity", "unit_price",
                                                      "line_cost", "excluded", "section_multiplier", "formula")}
                              for it in res.get("items", [])]})
        out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        n4 = sum(1 for s in doc["scenarios"] if s["foam"] == "4G")
        print(f"captured {len(doc['scenarios'])} scenarios ({n4} graded 4G) from {len(reports)} report(s) at factor {factor!r} -> {out}")
    finally:
        db.rollback(); db.close(); conn.close()
    return 0


def _is_pu(it) -> bool:
    return str(it.get("material") or "").strip().upper() in PU_NAMES


def compare(before: Path, after: Path) -> int:
    b, a = (json.loads(p.read_text(encoding="utf-8")) for p in (before, after))
    ratio = a["factor"] / b["factor"]
    print(f"factor {b['factor']!r} -> {a['factor']!r}; ratio {ratio!r}")
    bad: list[str] = []
    if [s["id"] for s in b["scenarios"]] != [s["id"] for s in a["scenarios"]]:
        print("!! the two captures do not hold the same scenarios"); return 1
    c = Counter()
    per_pack = defaultdict(Counter)
    max_line_dev = max_cell_dev = 0.0
    all_pu_cells = []
    for sb, sa in zip(b["scenarios"], a["scenarios"]):
        sid, pack = f"{sb['pack']}:{sb['id']}", sb["pack"]
        if [i["bom_id"] for i in sb["items"]] != [i["bom_id"] for i in sa["items"]]:
            bad.append(f"{sid}: the line list differs"); continue
        if sb["foam"] != "4G":
            c["scen_32d"] += 1
            if sb["items"] != sa["items"] or sb["totals"] != sa["totals"] or sb["grand_total"] != sa["grand_total"]:
                bad.append(f"{sid} (32D): something moved")
            c["cells_32d"] += len(sb["totals"]); per_pack[pack]["cells_32d"] += len(sb["totals"])
            continue
        c["scen_4g"] += 1
        pu_part = defaultdict(float)             # section -> PU foam line costs before
        pu_delta = defaultdict(float)            # section -> sum of the PU foam lines' moves
        for ib, ia in zip(sb["items"], sa["items"]):
            same_shape = all(ib[k] == ia[k] for k in ("category", "material", "quantity", "excluded", "section_multiplier", "formula"))
            if not same_shape:
                bad.append(f"{sid} bom {ib['bom_id']}: the line's shape changed"); continue
            if _is_pu(ib):
                up_b, up_a = float(ib["unit_price"] or 0), float(ia["unit_price"] or 0)
                if abs(up_a - up_b * ratio) > 1e-9 * max(1.0, abs(up_b)):
                    bad.append(f"{sid} bom {ib['bom_id']}: unit price {up_b!r} -> {up_a!r}, not x {ratio!r}")
                lc_b, lc_a = float(ib["line_cost"] or 0), float(ia["line_cost"] or 0)
                if ib["excluded"] or lc_b == 0:
                    # a PU foam line the scenario does not cost (its panel is EPS, the other rear door, a x0
                    # formula): the price it carries scales, the cost stays R0
                    c["pu_lines_4g_uncosted"] += 1
                    if lc_a != 0:
                        bad.append(f"{sid} bom {ib['bom_id']}: an uncosted PU foam line now costs {lc_a}")
                    continue
                c["pu_lines_4g"] += 1
                dev = abs(lc_a - lc_b * ratio)
                max_line_dev = max(max_line_dev, dev)
                if dev > 0.011:          # both sides are rounded to the cent by the engine
                    bad.append(f"{sid} bom {ib['bom_id']}: line cost {lc_b} -> {lc_a}, x ratio = {lc_b * ratio:.4f}")
                pu_part[ib["category"]] += lc_b
                pu_delta[ib["category"]] += lc_a - lc_b
            elif ib != ia:
                bad.append(f"{sid} bom {ib['bom_id']} ({ib['material']}): a non-foam line moved")
        for sec in sorted(set(sb["totals"]) | set(sa["totals"])):
            tb, ta = float(sb["totals"].get(sec, 0.0)), float(sa["totals"].get(sec, 0.0))
            c["cells_4g"] += 1; per_pack[pack]["cells_4g"] += 1
            if pu_part[sec] == 0:
                if tb != ta:
                    bad.append(f"{sid} {sec}: no PU foam line, yet {tb} -> {ta}")
                c["cells_4g_still"] += 1; per_pack[pack]["cells_4g_still"] += 1
                continue
            want = tb + (ratio - 1) * pu_part[sec]
            dev = abs(ta - want)
            max_cell_dev = max(max_cell_dev, dev)
            if dev > 0.015:
                bad.append(f"{sid} {sec}: {tb} -> {ta}; expected {want:.4f} (PU foam part {pu_part[sec]:.2f})")
            c["cells_4g_moved"] += 1; per_pack[pack]["cells_4g_moved"] += 1
            if abs(pu_part[sec] - tb) <= 0.01 * max(1, len(sb["items"])):
                all_pu_cells.append((sid, sec, tb, ta, ta / tb if tb else None))
    print(f"scenarios: {c['scen_32d']} at 32D, {c['scen_4g']} at 4G; PU foam lines at 4G: {c['pu_lines_4g']} costed "
          f"(price and cost x the ratio) + {c['pu_lines_4g_uncosted']} not costed in their scenario (price x the ratio, cost R0 before and after)")
    print(f"cells at 32D: {c['cells_32d']}, every one unchanged (every line identical)")
    print(f"cells at 4G: {c['cells_4g']} = {c['cells_4g_moved']} moved by (ratio - 1) x their PU foam part"
          f" + {c['cells_4g_still']} with no PU foam line, unchanged")
    for pack, pc in sorted(per_pack.items()):
        print(f"   {pack:<10} 32D cells {pc['cells_32d']:>5} unchanged | 4G cells {pc['cells_4g']:>4}: moved {pc['cells_4g_moved']:>4}, "
              f"no PU foam {pc['cells_4g_still']:>4}")
    print(f"largest deviation: a PU foam line {max_line_dev:.4f}, a cell {max_cell_dev:.4f} (engine rounding to the cent)")
    if all_pu_cells:
        print(f"cells that are all PU foam (move by the ratio itself): {len(all_pu_cells)}, e.g. "
              + "; ".join(f"{s.split(':', 1)[1]} {sec} {tb:,.2f} -> {ta:,.2f} (x {r:.9f})" for s, sec, tb, ta, r in all_pu_cells[:3]))
    if bad:
        print(f"!! {len(bad)} problem(s):"); [print("   ", x) for x in bad[:40]]
        return 1
    print("ALL OK")
    return 0


def audit(pairs: list[tuple[Path, Path]]) -> int:
    ok = True
    tot = Counter()
    for pb, pa in pairs:
        rb, ra = (json.loads(p.read_text(encoding="utf-8")) for p in (pb, pa))
        foam = {s["scenario"]["id"]: s["scenario"]["foam"] for s in rb["scenarios"]}
        key = lambda cl: (cl["scenario_id"], cl["section_excel"], None if cl["section_excel"] else cl["section_mes"])
        cb, ca = {key(x): x for x in rb["cells"]}, {key(x): x for x in ra["cells"]}
        if set(cb) != set(ca):
            print(f"!! {rb['pack']}: the cell sets differ"); ok = False; continue
        n32 = n32_same = n4 = n4_moved = 0
        trans = Counter()
        flags = []
        for k, xb in cb.items():
            xa = ca[k]
            if foam[k[0]] != "4G":
                n32 += 1
                same = all(xb[f] == xa[f] for f in ("status", "mes_total", "excel_total", "section_mes", "reason"))
                n32_same += same
                if not same:
                    print(f"!! {rb['pack']} {k}: a 32D cell moved: {xb['status']} {xb['mes_total']} -> {xa['status']} {xa['mes_total']}")
                    ok = False
                continue
            n4 += 1
            n4_moved += xb["mes_total"] != xa["mes_total"]
            if xb["excel_total"] != xa["excel_total"]:
                print(f"!! {rb['pack']} {k}: the golden moved"); ok = False
            trans[(xb["status"], xa["status"])] += 1
            if xa["status"] != xb["status"]:
                flags.append(xa)
        tot["32"] += n32; tot["32s"] += n32_same; tot["4"] += n4; tot["4m"] += n4_moved
        print(f"{rb['pack']:<10} counts {rb['counts']} -> {ra['counts']}")
        print(f"{'':<10} 32D cells {n32}, unchanged {n32_same} | 4G cells {n4}, MES total moved on {n4_moved}")
        for (s0, s1), n in sorted(trans.items()):
            print(f"{'':<10}    4G {s0:>12} -> {s1:<12} {n}")
        for x in sorted(flags, key=lambda x: (x["sheet"], x["length"], x["section_excel"] or "")):
            print(f"{'':<10}    changed: {x['sheet']} L{x['length']:g} {x['section_excel'] or x['section_mes']}: Excel {x['excel_total']:,.2f} "
                  f"MES {x['mes_total']:,.2f} ({(x['variance_pct'] or 0):+.2f} %) {cb[key(x)]['status']} -> {x['status']}")
    print(f"ALL PACKS: 32D cells {tot['32']}, unchanged {tot['32s']} | 4G cells {tot['4']}, MES total moved on {tot['4m']}")
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "capture":
        sys.exit(capture(Path(sys.argv[2]), [Path(p) for p in sys.argv[3:]]))
    if cmd == "compare":
        sys.exit(compare(Path(sys.argv[2]), Path(sys.argv[3])))
    if cmd == "audit":
        ps = [Path(p) for p in sys.argv[2:]]
        sys.exit(audit(list(zip(ps[0::2], ps[1::2]))))
    print(__doc__); sys.exit(1)
