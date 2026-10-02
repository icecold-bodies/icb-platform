"""RT2 window click-through (runbook step 7) — the figures Michael should see, from the mirror after P + D.

    (DATABASE_URL = icb_prodmirror; PYTHONPATH = backend/)  python clickthrough_values.py

A NEW quote per body at its default size, every panel PU at the template thickness (EPS carried where the PU master
reads 0), the double rear door, and the foam the BODY opens on (not set by the script: after D the four R6 bodies must
open 4G by themselves). Prints the foam it opened on and every PU foam line, plus their sum. Read only.
"""
from __future__ import annotations

from app.config import settings
from app.db_guard import resolve_db_name
from app.services import insulation_foam as pu_foam
from tools.costing_audit.mes_probe import MesProbe
from tools.costing_audit.scenarios import PanelSpec, Scenario

BODIES = (12, 36, 24, 15, 34)
PANELS = ("FRONT", "DRD", "SRD", "SIDES", "ROOF", "FLOOR")


def main() -> int:
    assert resolve_db_name(settings.DATABASE_URL) == "icb_prodmirror", "mirror only"
    probe = MesProbe(log=lambda *_: None)
    try:
        for tid in BODIES:
            tt, bom = probe._load(tid)
            m = {(r.material.name or "").strip().upper(): r for r in bom if r.is_body_option and r.material}
            v = lambda n: float(m[n].variable_value or 0) if n in m else 0.0   # noqa: E731
            panels = {}
            for p in PANELS:
                if p == "SRD" or (f"{p} PU" not in m and f"{p} EPS" not in m):
                    continue
                panels[p] = PanelSpec("pu", v(f"{p} PU") or v(f"{p} EPS"))
            L, W, H = float(tt.default_length or 0), float(tt.default_width or 0), float(tt.default_height or 0)
            sc = Scenario(id=f"CT~{tid}", pack="clickthrough", sheet="", trailer_id=tid, variant="as_body", length=L,
                          width=W, height=H, door="drd", foam="32D", panels=panels, flags={}, foam_explicit=False)
            res = probe.cost(sc)
            rows = {r.id: r for r in bom}
            pu = [ln for ln in res.lines if ln.bom_id in rows and pu_foam.is_pu_foam_row(rows[ln.bom_id]) and not ln.excluded]
            opened = pu_foam.normalise(getattr(tt, "default_insulation_foam", None))
            print(f"{tt.name} ({tid}), {L} x {W} x {H}, double door, opens on {opened}: PU foam lines "
                  f"R{sum(ln.total for ln in pu):,.2f} — " + " · ".join(f"{ln.section} {ln.total:,.2f}" for ln in pu))
    finally:
        probe.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
