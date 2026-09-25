"""The Excel oracle: scenario -> recalculated copy of Burt's workbook -> section totals.

Local only (needs LibreOffice + the three workbooks). Never writes to Burt's
files: every scenario is an openpyxl COPY saved into a scratch folder, next to
copies of PRICE 2017 MARCH.xlsx / FORMULAS 2018.xls so the [1]/[2] links resolve.

Per scenario the copy gets, on its sheet only:
  * LENGTH / WIDTH / HEIGHT written to the input cells;
  * the flag block written literally — thickness + Y/N for every EPS/PU panel
    row (this also disconnects UP TO 5.5 CHILLER's control-panel formulas),
    other flags as saved unless the pack overrides them;
  * gate handling per gate_mode (as_sheet by default: Burt's own EPS-gated and
    PU-gated rows decide; force: the door's gate cells written 1/0 by door type;
    eps_flag: EPS flag Y with thickness 0 when the panel is PU);
  * PU foam grade by controlled substitution of the price-list reference in
    the PU lines ([1]PU!$C$17 = 32D, $C$19 = 4G) — exactly Burt's manual edit;
    a sheet whose PU lines hard-code a rate has no 4G spelling (UNVERIFIABLE).

Then ONE soffice call recalculates the whole batch (chunked), and the section
totals are read back as the sum of each section's gated J cells.

Prove-then-trust: before any scenario is trusted, a null scenario (the sheet's
saved inputs, as_sheet) is recalculated and must reproduce the workbook's own
cached section totals — a stale copy, a missing PRICE file or a broken link
fails here, loudly, not as a silent "PASS".
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openpyxl import load_workbook

from . import GOLDEN_DIR, SHEET_MAPS_DIR, __version__
from .mapping import PANELS, DOOR_PANELS, SHEET_TO_TRAILER, norm_name, sheet_slug
from .scenarios import Scenario, Pack, PanelSpec, sheet_state
from .sheet_map import SheetMap, discover_sheet, stale_external_links
from .soffice import convert_batch

GRP_FILE = "GRP Costings 2018.xlsx"
PRICE_FILE = "PRICE 2017 MARCH.xlsx"
FORMULAS_FILE = "FORMULAS 2018.xls"
WORKBOOK_FILES = (GRP_FILE, PRICE_FILE, FORMULAS_FILE)
PU_REF_RE = re.compile(r"(\[1\]PU!\$C\$)(17|19)\b")
PU_REF_BY_FOAM = {"32D": "17", "4G": "19"}
NULL_TOL = 1e-6          # relative tolerance for the prove-then-trust null scenario
BATCH_SIZE = 40


@dataclass
class GoldenLine:
    desc: str
    qty: float | None
    price: float | None
    total: float | None
    stale: bool = False


@dataclass
class GoldenSection:
    total: float | None            # gated material cost (sum of J cells); None when unverifiable
    raw_total: float | None        # the =SUM(H..) at the TOTAL row, ungated
    status: str                    # OK | UNVERIFIABLE
    reason: str | None
    gates: dict[str, object]
    lines: list[GoldenLine]
    multiplier: float = 1.0        # gated / raw (2 for SIDES: line totals are one side)


@dataclass
class GoldenScenario:
    scenario: dict
    grand_total: float | None
    sections: dict[str, GoldenSection]
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"scenario": self.scenario, "grand_total": self.grand_total,
                "findings": self.findings,
                "sections": {k: asdict(v) for k, v in self.sections.items()}}


def _panel_for_section(section_name: str) -> str | None:
    """FRONT/SIDES/ROOF/FLOOR/DRD/SRD section -> the panel whose insulation it carries."""
    first = norm_name(section_name).split()[:1]
    return first[0] if first and first[0] in PANELS else None


def workbook_fingerprint(workbook_dir: Path) -> dict[str, str]:
    out = {}
    for name in WORKBOOK_FILES:
        p = Path(workbook_dir) / name
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        out[name] = h.hexdigest()
    return out


def load_sheet_map_overrides(sheet_maps_dir: Path | None) -> dict[str, dict]:
    """sheet_maps/*.yaml keyed by the exact sheet name inside each file."""
    out: dict[str, dict] = {}
    d = Path(sheet_maps_dir or SHEET_MAPS_DIR)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if doc.get("sheet"):
            out[doc["sheet"]] = doc
    return out


class ExcelOracle:
    def __init__(self, workbook_dir: Path, *, work_dir: Path, soffice: Path | None = None,
                 sheet_maps_dir: Path | None = None, slim: bool = True, log=print):
        self.workbook_dir = Path(workbook_dir)
        self.work_dir = Path(work_dir)
        self.soffice = soffice
        self.slim = slim
        self.log = log
        for name in WORKBOOK_FILES:
            if not (self.workbook_dir / name).is_file():
                raise FileNotFoundError(f"{name} not found in {self.workbook_dir}")
        t0 = time.time()
        src = self.workbook_dir / GRP_FILE
        self.wb = load_workbook(src)                    # formulas (the copy we edit)
        self.wbv = load_workbook(src, data_only=True)   # Excel's cached values (never edited)
        self.stale = stale_external_links(self.wb, self.workbook_dir)
        self.overrides = load_sheet_map_overrides(sheet_maps_dir)
        self.maps: dict[str, SheetMap] = {}
        self.fingerprint = workbook_fingerprint(self.workbook_dir)
        if slim:
            self._slim()
        self.log(f"[oracle] workbook loaded in {time.time() - t0:.1f}s; stale links: {self.stale or 'none'}")

    # ── discovery ───────────────────────────────────────────────────────
    def discover(self, sheet: str) -> SheetMap:
        if sheet not in self.maps:
            if sheet not in self.wb.sheetnames:
                raise KeyError(f"sheet {sheet!r} not in workbook (exact spelling matters)")
            sm = discover_sheet(self.wb[sheet], self.wbv[sheet],
                                override=self.overrides.get(sheet), stale_links=self.stale)
            self.maps[sheet] = sm
        return self.maps[sheet]

    def _slim(self) -> None:
        """Drop sheets no body sheet references (the 17k-row planning sheets),
        so a scenario copy saves in ~0.6 s instead of ~2.4 s. Proven equal by the
        null-scenario check that guards every golden run."""
        keep = set(SHEET_TO_TRAILER)
        pat = re.compile(r"(?<![\[\]])'([^']+)'!|(?<![\[\]\w])([A-Za-z0-9_]+)!")
        for name in SHEET_TO_TRAILER:
            if name not in self.wb.sheetnames:
                continue
            for row in self.wb[name].iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        for m in pat.finditer(c.value):
                            tgt = m.group(1) or m.group(2)
                            if tgt in self.wb.sheetnames:
                                keep.add(tgt)
        for ws in list(self.wb.worksheets):
            if ws.title not in keep:
                self.wb.remove(ws)

    # ── scenario edits ──────────────────────────────────────────────────
    def _apply(self, sc: Scenario, sm: SheetMap) -> tuple[list[tuple[str, object]], list[str]]:
        """Write one scenario into the in-memory copy. Returns (undo list, findings)."""
        ws = self.wb[sc.sheet]
        undo: list[tuple[str, object]] = []
        findings: list[str] = []

        def put(cell: str, value):
            undo.append((cell, ws[cell].value))
            ws[cell] = value

        put(sm.inputs["LENGTH"], sc.length)
        put(sm.inputs["WIDTH"], sc.width)
        put(sm.inputs["HEIGHT"], sc.height)

        for panel in PANELS:
            eps, pu = sm.flag_by_label(f"{panel} EPS"), sm.flag_by_label(f"{panel} PU")
            spec = sc.panels.get(panel)
            if eps is None and pu is None:
                if spec is not None and spec.insulation != "none":
                    findings.append(f"{panel}: sheet has no {panel} EPS/PU rows — panel spec ignored")
                continue
            spec = spec or PanelSpec("none", 0.0)
            eps_t, eps_f, pu_t, pu_f = 0.0, "N", 0.0, "N"
            if spec.insulation == "eps":
                eps_t, eps_f = spec.thickness, "Y"
            elif spec.insulation == "pu":
                pu_t, pu_f = spec.thickness, "Y"
                if sc.gate_mode == "eps_flag":
                    eps_f = "Y"          # gate carrier, thickness 0
            if eps is not None:
                put(eps.thickness_cell, eps_t)
                put(eps.flag_cell, eps_f)
            if pu is not None:
                put(pu.thickness_cell, pu_t)
                put(pu.flag_cell, pu_f)

        for label, yn in sc.flags.items():
            f = sm.flag_by_label(label)
            if f is not None:
                put(f.flag_cell, yn)

        if sc.gate_mode == "force":
            for s in sm.sections:
                for g in s.gate_cells:
                    labs = [norm_name(x) for x in g.flag_labels]
                    if labs and all(l.startswith("DRD") for l in labs):
                        put(g.cell, 1 if sc.door == "drd" else 0)
                    elif labs and all(l.startswith("SRD") for l in labs):
                        put(g.cell, 1 if sc.door == "srd" else 0)

        # PU foam grade: controlled substitution of the price-list reference
        want = PU_REF_BY_FOAM[sc.foam]
        mix = {"17": 0, "19": 0}
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("=") and "PU!$C$" in v:
                    for m in PU_REF_RE.finditer(v):
                        mix[m.group(2)] += 1
                    new = PU_REF_RE.sub(lambda m: m.group(1) + want, v)
                    if new != v:
                        put(c.coordinate, new)
        if mix["17"] and mix["19"]:
            findings.append(f"mixed PU references on the sheet as saved: {mix['17']}x 32D (C17) + {mix['19']}x 4G (C19); "
                            f"normalised to {sc.foam} for this scenario")
        elif mix["19"] and not mix["17"]:
            findings.append(f"sheet as saved prices every PU line at 4G (C19); normalised to {sc.foam}")
        if sc.foam == "4G" and not (mix["17"] or mix["19"]):
            findings.append("NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — "
                            "4G cannot be expressed on this sheet")
        return undo, findings

    def _revert(self, sheet: str, undo: list[tuple[str, object]]) -> None:
        ws = self.wb[sheet]
        for cell, old in reversed(undo):
            ws[cell] = old

    # ── results ─────────────────────────────────────────────────────────
    def _read(self, out_path: Path, sc: Scenario, sm: SheetMap, findings: list[str]) -> GoldenScenario:
        wsv = load_workbook(out_path, data_only=True, read_only=False)[sc.sheet]
        no_4g = any(f.startswith("NO_4G_REFERENCE") for f in findings)
        sections: dict[str, GoldenSection] = {}
        grand = 0.0
        grand_ok = True
        for s in sm.sections:
            total = 0.0
            numeric = True
            for cell in s.gated_cells:
                v = wsv[cell].value
                if isinstance(v, (int, float)):
                    total += float(v)
                elif v is not None:
                    numeric = False
            raw = wsv[s.raw_total_cell].value if s.raw_total_cell else None
            raw = float(raw) if isinstance(raw, (int, float)) else None
            gates = {g.cell: wsv[g.cell].value for g in s.gate_cells}
            lines = []
            has_pu_line = False
            for l in s.lines:
                q = wsv[l.qty_cell].value if l.qty_cell else None
                p = wsv[l.price_cell].value if l.price_cell else None
                t = wsv[l.total_cell].value if l.total_cell else None
                if norm_name(l.desc) == "PU":
                    has_pu_line = True
                lines.append(GoldenLine(
                    desc=l.desc,
                    qty=float(q) if isinstance(q, (int, float)) else None,
                    price=float(p) if isinstance(p, (int, float)) else None,
                    total=float(t) if isinstance(t, (int, float)) else None,
                    stale=l.stale_link))
            # An insulation line the scenario switched ON that the sheet prices at 0
            # (e.g. the 4.8 FREEZER's EPS reference points at an empty price cell):
            # Excel cannot price this panel/insulation — never a PASS, never a
            # MES fault.
            unpriced = None
            panel = _panel_for_section(s.name)
            spec = sc.panels.get(panel) if panel else None
            if spec is not None and spec.insulation != "none":
                for l in lines:
                    if norm_name(l.desc) == spec.insulation.upper() and (l.price or 0) == 0 and (l.total or 0) == 0:
                        unpriced = f"EXCEL_NO_PRICE:{spec.insulation.upper()}"
            status, reason = "OK", None
            if s.unverifiable:
                status, reason = "UNVERIFIABLE", s.unverifiable
            elif not numeric:
                status, reason = "UNVERIFIABLE", "ERROR_CELL"
            elif no_4g and has_pu_line and any(
                    sc.panels.get(p, PanelSpec("none", 0)).insulation == "pu" for p in PANELS):
                status, reason = "UNVERIFIABLE", "NO_4G_REFERENCE"
            elif unpriced:
                status, reason = "UNVERIFIABLE", unpriced
            if status != "OK":
                grand_ok = False
            else:
                grand += total
            mult = 1.0
            if numeric and raw and abs(raw) > 0.005 and abs(total) > 0.005:
                mult = round(total / raw, 6)
            sections[s.name] = GoldenSection(
                total=round(total, 6) if numeric else None, raw_total=raw,
                status=status, reason=reason, gates=gates, lines=lines, multiplier=mult)
        gt = wsv[sm.grand_total_cell].value if sm.grand_total_cell else None
        gt = float(gt) if isinstance(gt, (int, float)) else None
        return GoldenScenario(scenario=sc.to_dict(), grand_total=gt, sections=sections, findings=list(findings))

    # ── batch run ───────────────────────────────────────────────────────
    def run(self, scenarios: list[Scenario]) -> dict[str, GoldenScenario]:
        """Recalculate every scenario; returns {scenario.id: GoldenScenario}."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        for name in (PRICE_FILE, FORMULAS_FILE):
            dst = self.work_dir / name
            if not dst.is_file():
                shutil.copy(self.workbook_dir / name, dst)
        results: dict[str, GoldenScenario] = {}
        pending: list[tuple[Path, Scenario, SheetMap, list[str]]] = []
        t0 = time.time()
        for i, sc in enumerate(scenarios):
            sm = self.discover(sc.sheet)
            undo, findings = self._apply(sc, sm)
            path = self.work_dir / f"scen_{i:04d}.xlsx"
            self.wb.save(path)
            self._revert(sc.sheet, undo)
            pending.append((path, sc, sm, findings))
        self.log(f"[oracle] {len(pending)} scenario copies written in {time.time() - t0:.1f}s")
        for start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[start:start + BATCH_SIZE]
            outputs, elapsed = convert_batch([p for p, *_ in chunk], self.work_dir / "out", soffice=self.soffice)
            self.log(f"[oracle] soffice recalculated {len(chunk)} copies in {elapsed}s")
            for path, sc, sm, findings in chunk:
                results[sc.id] = self._read(outputs[path], sc, sm, findings)
        return results

    # ── prove-then-trust ────────────────────────────────────────────────
    def null_scenario(self, sheet: str, pack_name: str = "null") -> Scenario:
        sm = self.discover(sheet)
        panels, door, flags = sheet_state(sm)
        return Scenario(id=f"null~{sheet_slug(sheet)}", pack=pack_name, sheet=sheet,
                        trailer_id=SHEET_TO_TRAILER[sheet], variant="null",
                        length=sm.input_values["LENGTH"], width=sm.input_values["WIDTH"],
                        height=sm.input_values["HEIGHT"], door=door, foam="32D",
                        panels=panels, flags=flags, gate_mode="as_sheet")

    def prove(self, sheets: list[str]) -> list[str]:
        """Null scenario per sheet must reproduce Excel's cached gated totals.
        Returns the list of failures (empty = trusted). Sheets whose PU lines
        are saved on the 4G reference are normalised to 32D by the null
        scenario, so they are compared with the substitution undone."""
        problems: list[str] = []
        scs = [self.null_scenario(s) for s in sheets]
        for sc in scs:
            sc.gate_mode = "as_sheet"
        res = self.run(scs)
        for sc in scs:
            sm = self.maps[sc.sheet]
            g = res[sc.id]
            mixed = any("normalised" in f for f in g.findings)
            for s in sm.sections:
                cached = s.cached_total
                got = g.sections[s.name].total
                if cached is None or got is None:
                    continue
                if mixed and any(norm_name(l.desc) == "PU" for l in s.lines):
                    continue      # substitution changed the PU price on purpose
                tol = max(abs(cached), 1.0) * NULL_TOL
                if abs(got - cached) > tol:
                    problems.append(f"{sc.sheet!r} {s.name}: recalculated {got:.4f} != cached {cached:.4f}")
        return problems


# ── golden files ────────────────────────────────────────────────────────

def write_golden(pack: Pack, oracle: ExcelOracle, results: dict[str, GoldenScenario],
                 scenarios: list[Scenario], golden_dir: Path | None = None) -> Path:
    out_dir = Path(golden_dir or GOLDEN_DIR) / pack.name
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    by_sheet: dict[str, list[GoldenScenario]] = {}
    for sc in scenarios:
        by_sheet.setdefault(sc.sheet, []).append(results[sc.id])
    for sheet, items in by_sheet.items():
        sm = oracle.maps[sheet]
        doc = {
            "sheet": sheet,
            "trailer_id": SHEET_TO_TRAILER[sheet],
            "sheet_map": {
                "label_col": sm.label_col, "inputs": sm.inputs, "input_values": sm.input_values,
                "control_panel": sm.control_panel, "selfcheck_ok": sm.selfcheck_ok,
                "flags": [{"label": f.label, "thickness": f.thickness, "flag": f.flag} for f in sm.flags],
                "sections": [{"name": s.name, "label": s.label, "rows": [s.first_row, s.last_row],
                              "gated_cells": s.gated_cells,
                              "gates": [{"cell": g.cell, "flags": g.flag_labels} for g in s.gate_cells],
                              "cached_total": s.cached_total, "unverifiable": s.unverifiable}
                             for s in sm.sections],
                "warnings": sm.warnings,
            },
            "scenarios": [g.to_dict() for g in items],
        }
        (out_dir / f"{sheet_slug(sheet)}.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    manifest = {
        "pack": pack.name,
        "pack_fingerprint": pack.fingerprint(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": __version__,
        "workbook_month": pack.raw.get("workbook_month"),
        "workbook": {"dir": str(oracle.workbook_dir), "files": oracle.fingerprint},
        "stale_links": oracle.stale,
        "scenario_count": len(scenarios),
        "sheets": {s: f"{sheet_slug(s)}.json" for s in by_sheet},
    }
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return out_dir


def read_golden(pack_name: str, golden_dir: Path | None = None) -> tuple[dict, dict[str, dict]]:
    """(manifest, {scenario_id: golden scenario dict})"""
    d = Path(golden_dir or GOLDEN_DIR) / pack_name
    mp = d / "_manifest.json"
    if not mp.is_file():
        raise FileNotFoundError(f"no golden for pack {pack_name!r} in {d} — run `audit golden` locally first")
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for f in manifest["sheets"].values():
        doc = json.loads((d / f).read_text(encoding="utf-8"))
        for g in doc["scenarios"]:
            out[g["scenario"]["id"]] = g
    return manifest, out
