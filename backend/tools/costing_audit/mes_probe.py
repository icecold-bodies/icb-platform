"""The MES probe: cost a scenario through the SAME path /api/calculate uses.

In-process by default — `_build_bom_items` -> `calculate_bom` from
app.routers.calculator, exactly as `september_impact_report.py` does — so CI
needs no HTTP server. `--base-url` posts the identical payload to a running
side-port server instead (never :8000).

The scenario is spelled the way the calculator UI spells it (read off a real
saved costing's input_state, v1.56):

    body_option_selections   {master-row-id: bool} for every is_body_option row
                             (the FRONT/DRD/SRD/SIDES/ROOF/FLOOR EPS-PU pairs,
                             DOOR TYPE masters where the body has them, and the
                             other flags — RICE GRAIN FLOOR etc. — matched by
                             name to the sheet's own flag block)
    body_variable_overrides  {master material name: thickness m} — the
                             scenario's insulation thicknesses
    excluded_categories      the OTHER rear door's sections by name (how the UI
                             gates DRD/SRD on v2 bodies without door masters)
    flag_overrides           {flag name: bool} aliases, as the UI sends them
    optional_sections_enabled []  — OPTIONAL EXTRAS off (Excel has none)
    insulation_foam          32D | 4G
    dimensions               length/width/height + the UI's zero defaults
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .mapping import PANELS, DOOR_PANELS, norm_name
from .scenarios import Scenario, PanelSpec

# The calculator page's dimension defaults (calculator.js:1958).
UI_DIM_DEFAULTS = {"floor_thickness": 0, "panel_thickness": 0, "insulation_thickness": 0,
                   "num_doors": 1, "num_axles": 2}


@dataclass
class MesLine:
    section: str
    desc: str
    qty: float
    price: float
    total: float
    excluded: bool = False
    bom_id: int | None = None
    formula: str | None = None


@dataclass
class MesResult:
    trailer_id: int
    trailer_name: str
    sections: dict[str, float]           # category_totals (SIDES x2 already applied)
    grand_total: float
    lines: list[MesLine]
    payload: dict
    unmatched_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _ensure_backend_on_path() -> None:
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


class MesProbe:
    """One probe per run; caches BOM rows per trailer (read-only)."""

    def __init__(self, base_url: str | None = None, log=print):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.log = log
        self._rows: dict[int, list] = {}
        self._trailers: dict[int, object] = {}
        self._db = None
        if not self.base_url:
            _ensure_backend_on_path()
            from app.database import SessionLocal
            self._db = SessionLocal()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    # ── BOM masters ─────────────────────────────────────────────────────
    def _load(self, trailer_id: int):
        if trailer_id in self._rows:
            return self._trailers[trailer_id], self._rows[trailer_id]
        from app.database import TrailerType, BillOfMaterial
        from app.routers.calculator import _bom_load_options, get_section_snapshot
        tt = self._db.query(TrailerType).filter_by(id=trailer_id).first()
        if tt is None:
            raise KeyError(f"trailer_types.id={trailer_id} not in this database")
        rows = (self._db.query(BillOfMaterial).filter_by(trailer_type_id=trailer_id)
                .options(*_bom_load_options()).all())
        order = get_section_snapshot().order
        rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                                 r.material.name.lower() if r.material else ""))
        self._trailers[trailer_id], self._rows[trailer_id] = tt, rows
        return tt, rows

    def masters(self, trailer_id: int) -> list[dict]:
        """Plain view of the body-option master rows (for reports/tests)."""
        _, rows = self._load(trailer_id)
        return [{"id": r.id, "name": r.material.name, "group": r.body_option_group,
                 "subgroup": r.body_option_subgroup, "variable_value": r.variable_value,
                 "default": bool(r.body_option_default)}
                for r in rows if r.is_body_option and r.material]

    def sections(self, trailer_id: int) -> list[str]:
        _, rows = self._load(trailer_id)
        seen: list[str] = []
        for r in rows:
            if r.is_body_option:
                continue
            name = r.bom_section or (r.material.category.name if r.material and r.material.category else "Uncategorised")
            if name not in seen:
                seen.append(name)
        return seen

    # ── payload ─────────────────────────────────────────────────────────
    def build_payload(self, sc: Scenario) -> tuple[dict, list[str], list[str]]:
        """Returns (payload, unmatched sheet flags, notes)."""
        _, rows = self._load(sc.trailer_id)
        masters = [r for r in rows if r.is_body_option and r.material]
        sel: dict[str, bool] = {}
        var_over: dict[str, float] = {}
        flag_over: dict[str, bool] = {}
        notes: list[str] = []
        handled: set[int] = set()

        # insulation pairs
        for panel in PANELS:
            eps = next((r for r in masters if norm_name(r.material.name) == f"{panel} EPS"), None)
            pu = next((r for r in masters if norm_name(r.material.name) == f"{panel} PU"), None)
            spec = sc.panels.get(panel, PanelSpec("none", 0.0))
            if eps is None and pu is None:
                if spec.insulation != "none":
                    notes.append(f"{panel}: body has no {panel} EPS/PU masters")
                continue
            for r, kind in ((eps, "eps"), (pu, "pu")):
                if r is None:
                    continue
                on = spec.insulation == kind
                sel[str(r.id)] = on
                flag_over[r.material.name] = on
                var_over[r.material.name] = float(spec.thickness) if on else 0.0
                handled.add(r.id)

        # DOOR TYPE masters (bodies that have them, e.g. CHILLER LARGE)
        for r in masters:
            if norm_name(r.body_option_group) == "DOOR TYPE" or norm_name(r.material.name) in DOOR_PANELS and r.body_option_subgroup and norm_name(r.body_option_subgroup) == "DOOR TYPE":
                on = norm_name(r.material.name) == sc.door.upper()
                sel[str(r.id)] = on
                flag_over[r.material.name] = on
                handled.add(r.id)

        # other flags: match the sheet's flag block by name, else the body default
        sheet_flags = {norm_name(k): v for k, v in sc.flags.items()}
        matched: set[str] = set()
        for r in masters:
            if r.id in handled:
                continue
            key = norm_name(r.material.name)
            if key in sheet_flags:
                on = sheet_flags[key] == "Y"
                matched.add(key)
            else:
                on = bool(r.body_option_default)
            sel[str(r.id)] = on
            flag_over[r.material.name] = on
        unmatched = [k for k in sc.flags if norm_name(k) not in matched]
        for r in masters:
            if r.id in handled or norm_name(r.material.name) in sheet_flags:
                continue
            notes.append(f"MES master {r.material.name!r} has no flag on the sheet — left at body default "
                         f"{'ON' if r.body_option_default else 'OFF'}")

        other_door = "SRD" if sc.door == "drd" else ("DRD" if sc.door == "srd" else None)
        excluded = []
        if other_door:
            for name in self.sections(sc.trailer_id):
                toks = norm_name(name).split()
                if toks and (toks[0] == other_door or (other_door in toks and "DOOR" in toks)):
                    excluded.append(name)
        if sc.door == "none":
            for name in self.sections(sc.trailer_id):
                toks = norm_name(name).split()
                if toks and toks[0] in DOOR_PANELS:
                    excluded.append(name)

        payload = {
            "trailer_type_id": sc.trailer_id,
            "dimensions": {"length": sc.length, "width": sc.width, "height": sc.height, **UI_DIM_DEFAULTS},
            "overrides": {},
            "body_option_selections": sel,
            "body_variable_overrides": var_over,
            "excluded_categories": excluded,
            "flag_overrides": flag_over,
            "user_excluded_bom_ids": [],
            "optional_sections_enabled": [],
            "insulation_foam": sc.foam,
            "profit_margin": 0,
            "chassis": {"enabled": False},
        }
        return payload, unmatched, notes

    # ── cost ────────────────────────────────────────────────────────────
    def cost(self, sc: Scenario) -> MesResult:
        payload, unmatched, notes = self.build_payload(sc)
        if self.base_url:
            result = self._post(payload)
            tname = result.get("trailer_name", "")
        else:
            result = self._in_process(payload)
            tname = self._trailers[sc.trailer_id].name
        lines = [MesLine(section=it.get("category", ""), desc=it.get("material", ""),
                         qty=float(it.get("quantity") or 0), price=float(it.get("unit_price") or 0),
                         total=float(it.get("line_cost") or 0), excluded=bool(it.get("excluded")),
                         bom_id=it.get("bom_id"), formula=it.get("formula"))
                 for it in result.get("items", [])]
        return MesResult(trailer_id=sc.trailer_id, trailer_name=tname,
                         sections={k: float(v) for k, v in (result.get("category_totals") or {}).items()},
                         grand_total=float(result.get("grand_total") or 0), lines=lines,
                         payload=payload, unmatched_flags=unmatched, notes=notes)

    def _in_process(self, body: dict) -> dict:
        from app.routers.calculator import (_build_bom_items, _build_body_variables,
                                            _apply_body_variable_overrides, get_formula_lib,
                                            get_global_vars)
        from app.formula_engine import calculate_bom
        from app.services import insulation_foam as pu_foam
        tt, rows = self._load(body["trailer_type_id"])
        body_opt_sel = {str(k): bool(v) for k, v in body["body_option_selections"].items()}
        flag_overrides = {str(k): bool(v) for k, v in body["flag_overrides"].items()}
        items = _build_bom_items(rows, body["dimensions"], {}, body_opt_sel, self._db,
                                 body["excluded_categories"], trailer=tt, flag_overrides=flag_overrides,
                                 include_all_items=False, user_excluded_bom_ids=[],
                                 optional_sections_enabled=body["optional_sections_enabled"],
                                 formula_overrides=None,
                                 insulation_foam=pu_foam.normalise(body["insulation_foam"]))
        body_vars = _build_body_variables(rows)
        _apply_body_variable_overrides(body_vars, body["body_variable_overrides"])
        return calculate_bom(items, body["dimensions"], body_vars, get_formula_lib(), get_global_vars())

    def _post(self, body: dict) -> dict:
        import httpx
        if not hasattr(self, "_client"):
            self._client = httpx.Client(base_url=self.base_url, timeout=120.0, verify=False)
            origin = self.base_url
            r = self._client.post("/api/mes/autologin", headers={"Origin": origin}, json={})
            if r.status_code != 200:
                raise RuntimeError(f"autologin on {self.base_url} failed: {r.status_code} {r.text[:200]} "
                                   "(the side-port server needs MES_DEMO_AUTOLOGIN_USER and its origin in ALLOWED_ORIGINS)")
            import re
            page = self._client.get("/calculator").text
            m = re.search(r'<meta name="csrf-token" content="([^"]*)"', page)
            self._client.headers["X-CSRF-Token"] = m.group(1) if m else ""
        r = self._client.post("/api/calculate", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"/api/calculate {r.status_code}: {r.text[:300]}")
        return r.json()
