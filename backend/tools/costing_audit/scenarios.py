"""Packs -> scenarios.

A pack is a small YAML document the user edits (tests/costing_audit/packs/):

    name: chillers
    tolerance_pct: 1.0
    gate_mode: as_sheet         # as_sheet | force | eps_flag   (see excel_oracle)
    bodies:
      - sheet: "UP TO 5.5 CHILLER AND 2.3 WIDE"      # exact sheet spelling
        lengths: [4.2, 5.5, 5.8]                     # sweep values (metres)
        widths:  [2.3]                               # optional; default = sheet value
        heights: [2.3]                               # optional; default = sheet value
        variants: [as_sheet, all_eps, all_pu, srd, drd, foam_4g]
        custom_variants:                             # optional, per-panel spelling
          thin_pu:
            door: drd
            foam: 32D
            panels: {FRONT: pu:0.05, DRD: pu:0.05, SIDES: pu:0.05, ROOF: pu:0.06, FLOOR: pu:0.06}
        flags: {"RICE GRAIN FLOOR": N}               # optional other-flag overrides (else as saved)
        section_map: {"EXCEL LABEL": "MES NAME"}     # optional
    thickness_defaults:                              # used when the sheet's own block reads 0
      eps: {FRONT: 0.06, DRD: 0.06, SRD: 0.06, SIDES: 0.06, ROOF: 0.076, FLOOR: 0.076}
      pu:  {FRONT: 0.06, DRD: 0.06, SRD: 0.06, SIDES: 0.06, ROOF: 0.076, FLOOR: 0.076}

Every (body x length x width x height x variant) is one Scenario. The six
named variants (ratified default 4):

    as_sheet  Burt's own flag/thickness block exactly as saved
    all_eps   every panel EPS at the sheet's EPS thickness (else defaults)
    all_pu    every panel PU  at the sheet's PU thickness  (else defaults)
    srd       as_sheet insulation, rear door = SRD
    drd       as_sheet insulation, rear door = DRD
    foam_4g   as_sheet, PU foam graded 4G
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

from .mapping import PANELS, DOOR_PANELS, SHEET_TO_TRAILER, norm_name
from .sheet_map import SheetMap

NAMED_VARIANTS = ("as_sheet", "all_eps", "all_pu", "srd", "drd", "foam_4g")
# as_sheet: Burt's own gate rows decide (every sheet has an EPS-gated and a
#           PU-gated row per door section, so honest flags price PU doors);
# force:    the door's gate cells are written 1/0 by door type (for sheets whose
#           gates read a flag the scenario cannot set honestly);
# eps_flag: the EPS flag is set Y with thickness 0 when the panel is PU.
GATE_MODES = ("as_sheet", "force", "eps_flag")

DEFAULT_THICKNESS = {
    "eps": {"FRONT": 0.06, "DRD": 0.06, "SRD": 0.06, "SIDES": 0.06, "ROOF": 0.076, "FLOOR": 0.076},
    "pu": {"FRONT": 0.06, "DRD": 0.06, "SRD": 0.06, "SIDES": 0.06, "ROOF": 0.076, "FLOOR": 0.076},
}


@dataclass
class PanelSpec:
    insulation: str            # eps | pu | none
    thickness: float           # metres; 0 when none


@dataclass
class Scenario:
    id: str
    pack: str
    sheet: str
    trailer_id: int
    variant: str
    length: float
    width: float
    height: float
    door: str                              # drd | srd | none
    foam: str                              # 32D | 4G
    panels: dict[str, PanelSpec]           # FRONT/DRD/SRD/SIDES/ROOF/FLOOR
    flags: dict[str, str]                  # other flag label -> Y/N (as sheet unless overridden)
    gate_mode: str = "as_sheet"
    section_map: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Pack:
    name: str
    path: Path
    tolerance_pct: float
    gate_mode: str
    bodies: list[dict]
    thickness_defaults: dict
    raw: dict

    @property
    def sheets(self) -> list[str]:
        return [b["sheet"] for b in self.bodies]

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.raw, sort_keys=True, default=str).encode()).hexdigest()[:12]


def load_pack(path: Path) -> Pack:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    name = raw.get("name") or path.stem
    gate_mode = str(raw.get("gate_mode", "as_sheet"))
    if gate_mode not in GATE_MODES:
        raise ValueError(f"{path.name}: gate_mode must be one of {GATE_MODES}")
    bodies = raw.get("bodies") or []
    if not bodies:
        raise ValueError(f"{path.name}: pack has no bodies")
    for b in bodies:
        if b.get("sheet") not in SHEET_TO_TRAILER:
            raise ValueError(f"{path.name}: unknown sheet {b.get('sheet')!r} (exact spelling, see mapping.py)")
        for v in b.get("variants") or []:
            if v not in NAMED_VARIANTS and v not in (b.get("custom_variants") or {}):
                raise ValueError(f"{path.name}: unknown variant {v!r} for {b['sheet']!r}")
    td = raw.get("thickness_defaults") or {}
    thickness_defaults = {
        "eps": {**DEFAULT_THICKNESS["eps"], **{k.upper(): float(v) for k, v in (td.get("eps") or {}).items()}},
        "pu": {**DEFAULT_THICKNESS["pu"], **{k.upper(): float(v) for k, v in (td.get("pu") or {}).items()}},
    }
    return Pack(name=name, path=path, tolerance_pct=float(raw.get("tolerance_pct", 1.0)),
                gate_mode=gate_mode, bodies=bodies, thickness_defaults=thickness_defaults, raw=raw)


# ── the sheet's own state ──────────────────────────────────────────────────

def sheet_state(sm: SheetMap) -> tuple[dict[str, PanelSpec], str, dict[str, str]]:
    """Read Burt's saved block: per-panel insulation + thickness, the door type
    the flags imply, and every other flag's Y/N."""
    panels: dict[str, PanelSpec] = {}
    others: dict[str, str] = {}
    eps_pu_cells = set()
    for p in PANELS:
        eps = sm.flag_by_label(f"{p} EPS")
        pu = sm.flag_by_label(f"{p} PU")
        if eps is None and pu is None:
            continue
        for f in (eps, pu):
            if f is not None:
                eps_pu_cells.add(f.flag_cell)
        eps_on = bool(eps and eps.flag == "Y")
        pu_on = bool(pu and pu.flag == "Y")
        if pu_on and not eps_on:
            panels[p] = PanelSpec("pu", float(pu.thickness or 0))
        elif eps_on and not pu_on:
            panels[p] = PanelSpec("eps", float(eps.thickness or 0))
        elif eps_on and pu_on:
            # Burt's "present but PU" spelling on thickness-scaled sheets: EPS flag Y
            # with thickness 0 carries the gate, PU carries the money.
            if (eps.thickness or 0) == 0 and (pu.thickness or 0) > 0:
                panels[p] = PanelSpec("pu", float(pu.thickness))
            else:
                panels[p] = PanelSpec("eps", float(eps.thickness or 0))
        else:
            panels[p] = PanelSpec("none", 0.0)
    for f in sm.flags:
        if f.flag_cell not in eps_pu_cells:
            others[f.label] = (f.flag or "N").upper()
    # door: whichever rear-door panel is present; DRD wins a tie (Burt's default)
    door = "none"
    for p in ("DRD", "SRD"):
        if p in panels and panels[p].insulation != "none":
            door = p.lower()
            break
    return panels, door, others


def _panel_thickness(kind: str, panel: str, sm: SheetMap, defaults: dict) -> float:
    """The sheet's own thickness for that panel/kind where non-zero, else the
    pack's defaults table (ratified default 4)."""
    f = sm.flag_by_label(f"{panel} {kind.upper()}")
    if f is not None and f.thickness:
        return float(f.thickness)
    return float(defaults[kind].get(panel, 0.0))


def _parse_panel_spec(text) -> PanelSpec:
    """'pu:0.06' | 'eps:0.076' | 'none'"""
    s = str(text).strip().lower()
    if s in ("none", "", "0"):
        return PanelSpec("none", 0.0)
    kind, _, t = s.partition(":")
    if kind not in ("eps", "pu"):
        raise ValueError(f"panel spec must be eps:<m> | pu:<m> | none, got {text!r}")
    return PanelSpec(kind, float(t or 0))


def expand_pack(pack: Pack, maps: dict[str, SheetMap]) -> list[Scenario]:
    """All scenarios of a pack, in pack order. `maps` = discovered SheetMap per sheet."""
    out: list[Scenario] = []
    for body in pack.bodies:
        sheet = body["sheet"]
        sm = maps[sheet]
        base_panels, base_door, base_flags = sheet_state(sm)
        flag_over = {str(k): str(v).upper() for k, v in (body.get("flags") or {}).items()}
        flags = dict(base_flags)
        for k, v in flag_over.items():
            match = next((lab for lab in flags if norm_name(lab) == norm_name(k)), k)
            flags[match] = v
        section_map = dict(body.get("section_map") or {})
        gate_mode = str(body.get("gate_mode") or pack.gate_mode)
        lengths = [float(x) for x in (body.get("lengths") or [sm_input_value(sm, "LENGTH")])]
        widths = [float(x) for x in (body.get("widths") or [sm_input_value(sm, "WIDTH")])]
        heights = [float(x) for x in (body.get("heights") or [sm_input_value(sm, "HEIGHT")])]
        variants = list(body.get("variants") or ["as_sheet"])
        custom = body.get("custom_variants") or {}
        for L in lengths:
            for W in widths:
                for H in heights:
                    for var in variants:
                        panels = {p: PanelSpec(s.insulation, s.thickness) for p, s in base_panels.items()}
                        door, foam = base_door, "32D"
                        if var == "all_eps" or var == "all_pu":
                            kind = "eps" if var == "all_eps" else "pu"
                            for p in panels:
                                if p in DOOR_PANELS and p.lower() != door:
                                    panels[p] = PanelSpec("none", 0.0)
                                else:
                                    panels[p] = PanelSpec(kind, _panel_thickness(kind, p, sm, pack.thickness_defaults))
                        elif var in ("srd", "drd"):
                            door = var
                            other = "SRD" if var == "drd" else "DRD"
                            if var.upper() in panels:
                                cur = panels[var.upper()]
                                if cur.insulation == "none":
                                    # take the other door's insulation kind at this door's thickness
                                    src = panels.get(other) or PanelSpec("eps", 0.0)
                                    kind = src.insulation if src.insulation != "none" else "eps"
                                    panels[var.upper()] = PanelSpec(kind, _panel_thickness(kind, var.upper(), sm, pack.thickness_defaults))
                            if other in panels:
                                panels[other] = PanelSpec("none", 0.0)
                        elif var == "foam_4g":
                            foam = "4G"
                        elif var == "as_sheet":
                            pass
                        else:
                            spec = custom[var]
                            door = str(spec.get("door") or door).lower()
                            foam = str(spec.get("foam") or "32D").upper()
                            for p, txt in (spec.get("panels") or {}).items():
                                panels[p.upper()] = _parse_panel_spec(txt)
                            for p in DOOR_PANELS:
                                if p in panels and p.lower() != door:
                                    panels[p] = PanelSpec("none", 0.0)
                        sid = f"{norm_name(sheet).replace(' ', '_')[:24]}~L{L:g}~W{W:g}~H{H:g}~{var}"
                        out.append(Scenario(
                            id=sid, pack=pack.name, sheet=sheet, trailer_id=SHEET_TO_TRAILER[sheet],
                            variant=var, length=L, width=W, height=H, door=door, foam=foam,
                            panels=panels, flags=flags, gate_mode=gate_mode, section_map=section_map))
    return out


def sm_input_value(sm: SheetMap, which: str) -> float:
    """The sheet's saved LENGTH/WIDTH/HEIGHT (the pack's sweep default)."""
    v = sm.input_values.get(which)
    if v is None:
        raise ValueError(f"{sm.sheet!r}: no saved {which} value on the sheet")
    return float(v)
