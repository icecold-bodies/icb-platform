"""RT2 Manifest P — the per-line table at each body's DEFAULT size and DEFAULT foam (RT2_RULING_1, Part 3 ratified:
"the P table at default size must show, for every line, old -> new -> Burt at the body's default foam").

    (DATABASE_URL = icb_prodmirror; PYTHONPATH = backend/)  python p_table.py <label> <out.json> [<burt golden dir>]

With a golden dir, the line's own panel takes BURT's thickness from that golden (the scenario p_table_join.py reads):
the MES and Burt then compare like for like — same size, same foam, same thickness — which is what P changes.

For each of Manifest P's 39 lines it prices one NEW quote on the line's body through the audit probe (the
calculator's own in-process path, read-only) and reads that bom line's total:
  * size     the body's default length / width / height (Body Templates);
  * foam     the body's R6 default: 4G on MEAT HANGER LARGE, MEAT HANGER SMALL-MEDIUM, EXPLOSIVE 4.9 AND UP and
             RHINORANGE TRAILER; 32D everywhere else — set explicitly, so "old" (before P and D) is priced at the
             same grade as "new";
  * panels   every panel PU, at the PU master's thickness; where the PU master reads 0, the EPS master's thickness
             (the Part 1 calculator carries the thickness across when a quote switches a panel EPS -> PU);
  * door     the double rear door, or the single one for an SRD line.
Run it before P ("old") and after P + D ("new"); Burt's column comes from his sheets (p_table_join.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from app.config import settings
from app.db_guard import resolve_db_name
from tools.costing_audit.mes_probe import MesProbe
from tools.costing_audit.scenarios import PanelSpec, Scenario

MANIFEST = Path(__file__).resolve().parents[1] / "manifest_p" / "manifest_p.yaml"
DEFAULT_4G = {12, 36, 24, 15}                      # RT2_RULING_1 R6
PANELS = ("FRONT", "DRD", "SRD", "SIDES", "ROOF", "FLOOR")


def lines() -> list[tuple[int, int, str, str]]:
    """(bom id, body id, body, section) — each P line once."""
    seen, out = set(), []
    for e in yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["changes"]:
        if e["bom_id"] not in seen:
            seen.add(e["bom_id"])
            out.append((int(e["bom_id"]), int(e["body_id"]), e["body"][0] if isinstance(e["body"], list) else e["body"], e["section"]))
    return sorted(out, key=lambda x: (x[2], PANELS.index(x[3]) if x[3] in PANELS else 9, x[0]))


def burt_thickness(gdir: Path, tid: int, sec: str) -> float | None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from p_table_join import SHEET                              # the same sheet + scenario the join reads
    d = json.loads((gdir / f"{SHEET[tid]}.json").read_text(encoding="utf-8"))
    sc = next(s for s in d["scenarios"] if s["scenario"]["variant"] == ("srd" if sec == "SRD" else "all_pu"))
    return (sc["scenario"]["panels"].get(sec) or {}).get("thickness")


def main(label: str, out: str, burt_dir: str | None = None) -> int:
    db = resolve_db_name(settings.DATABASE_URL)
    if db != "icb_prodmirror":
        raise SystemExit(f"REFUSED: {db!r} is not the scratch mirror")
    probe = MesProbe(log=lambda *_: None)
    rows = []
    try:
        for bid, tid, body, sec in lines():
            tt, bom = probe._load(tid)
            masters = {(r.material.name or "").strip().upper(): r for r in bom if r.is_body_option and r.material}
            panels, carried_note = {}, {}
            val = lambda name: float(masters[name].variable_value or 0) if name in masters else 0.0   # noqa: E731
            for p in PANELS:
                if f"{p} PU" not in masters and f"{p} EPS" not in masters:
                    continue
                t = val(f"{p} PU")
                if t <= 0 and val(f"{p} EPS") > 0:           # EPS -> PU on the quote: the thickness comes along
                    t, carried_note[p] = val(f"{p} EPS"), "EPS carried"
                if t <= 0 and p == "SRD":                      # the single door switched on: _carryRearDoorThickness
                    t = val("DRD PU") or val("DRD EPS") or 0.06    # takes the double door's active cell, else 0.06
                    carried_note[p] = "from DRD"
                panels[p] = PanelSpec("pu", t)
            if burt_dir:                                       # like for like: the line's panel at Burt's thickness
                tb = burt_thickness(Path(burt_dir), tid, sec)
                if tb is not None:
                    panels[sec], carried_note[sec] = PanelSpec("pu", float(tb)), "Burt's"
            L, W, H = float(tt.default_length or 0), float(tt.default_width or 0), float(tt.default_height or 0)
            foam = "4G" if tid in DEFAULT_4G else "32D"
            door = "srd" if sec == "SRD" else "drd"
            sc = Scenario(id=f"P~{bid}", pack="p_table", sheet="", trailer_id=tid, variant="p_table", length=L,
                          width=W, height=H, door=door, foam=foam, panels=panels, flags={}, foam_explicit=True)
            res = probe.cost(sc)
            hit = [ln for ln in res.lines if ln.bom_id == bid]
            ln = hit[0] if hit else None
            rows.append({"bom_id": bid, "body_id": tid, "body": body, "section": sec, "size": [L, W, H], "foam": foam,
                         "door": door, "thickness": panels.get(sec).thickness if sec in panels else None,
                         "carried": carried_note.get(sec),
                         "total": None if ln is None else round(ln.total, 2), "qty": None if ln is None else ln.qty,
                         "unit_price": None if ln is None else ln.price, "excluded": None if ln is None else ln.excluded,
                         "formula": None if ln is None else ln.formula, "found": ln is not None})
            print(f"   {body:<26} {sec:<6} bom {bid:>5}  {L}x{W}x{H} {foam:<3} {door}  t={rows[-1]['thickness']}"
                  f"{' (' + rows[-1]['carried'] + ')' if rows[-1]['carried'] else ''}  ->  "
                  f"{'NOT PRICED' if ln is None else f'R{ln.total:,.2f}' + (' (excluded)' if ln.excluded else '')}")
    finally:
        probe.close()
    Path(out).write_text(json.dumps({"label": label, "database": db, "lines": rows}, indent=1), encoding="utf-8")
    print(f"== {label}: {len(rows)} lines -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
