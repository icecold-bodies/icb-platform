"""Golden (Excel) vs MES: section cells, then line-level triage on every FLAG.

Per scenario x section (ratified defaults 3, 7):

    PASS          both sides priced, |mes-excel| / |excel| <= tolerance
    FLAG          both sides priced, variance over tolerance
    PRESENCE      one side is zero/absent, the other is not (never a division)
    SKIP          both sides zero (the rear door that is not fitted, etc.)
    UNVERIFIABLE  the oracle could not price the section (STALE_LINK,
                  ERROR_CELL, NO_4G_REFERENCE) — never PASS
    UNMAPPED      the Excel section has no MES section of that name
    ACCEPTED      a FLAG/PRESENCE/UNMAPPED covered by accepted_differences.yaml
    EXPIRED       ... covered by an entry past its review_by (fails)
    NO_GOLDEN     the pack has a scenario the golden does not (re-run golden)

Line triage matches lines by normalised description (duplicates such as the
three GLUE LINE rows pair up in order) and classifies each as MISSING_IN_MES,
EXTRA_IN_MES, PRICE_DIFF, QTY_DIFF, BOTH or OK; the largest rand contributor
is the "likely cause".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone

from .accepted import Accepted
from .mapping import SectionMapper, norm_name, norm_key
from .mes_probe import MesResult

FAILING = {"FLAG", "PRESENCE", "UNMAPPED", "EXPIRED", "NO_GOLDEN"}
LINE_TOL_PCT = 0.5          # a line's price/qty is "different" beyond this
_ZERO_FORMULA_RE = re.compile(r"\*\s*0(?:\.0+)?(?![\d.])")


def _hint(m) -> str | None:
    f = getattr(m, "formula", None) or ""
    if _ZERO_FORMULA_RE.search(f) and _near_zero(getattr(m, "total", 0.0)):
        return "ZERO_FORMULA"
    return None


@dataclass
class LineTriage:
    desc: str
    excel_qty: float | None
    excel_price: float | None
    excel_total: float | None
    mes_qty: float | None
    mes_price: float | None
    mes_total: float | None
    delta: float               # mes_total - excel_total (rand)
    cls: str                   # MISSING_IN_MES | EXTRA_IN_MES | PRICE_DIFF | QTY_DIFF | BOTH | OK | STALE_LINK | GROUP_DIFF
    mes_formula: str | None = None
    hint: str | None = None    # e.g. ZERO_FORMULA: the MES quantity formula carries a literal x0


@dataclass
class Cell:
    scenario_id: str
    sheet: str
    trailer_id: int
    trailer_name: str
    variant: str
    length: float
    width: float
    height: float
    section_excel: str | None
    section_mes: str | None
    excel_total: float | None
    mes_total: float | None
    variance_pct: float | None
    status: str
    reason: str | None = None
    accepted: dict | None = None
    likely_cause: str | None = None
    triage: list[LineTriage] = field(default_factory=list)
    base_status: str | None = None     # the status before any acceptance (FLAG/PRESENCE/UNMAPPED)

    @property
    def failing(self) -> bool:
        return self.status in FAILING

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScenarioRow:
    scenario: dict
    excel_grand: float | None
    mes_grand: float | None
    findings: list[str]
    unmatched_flags: list[str]
    notes: list[str]
    payload: dict


@dataclass
class RunReport:
    pack: str
    tolerance_pct: float
    generated_at: str
    golden_manifest: dict
    mes_source: str
    warnings: list[str]
    cells: list[Cell]
    scenarios: list[ScenarioRow]

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cells:
            out[c.status] = out.get(c.status, 0) + 1
        return dict(sorted(out.items()))

    @property
    def failing(self) -> list[Cell]:
        return [c for c in self.cells if c.failing]

    @property
    def exit_code(self) -> int:
        return 1 if self.failing else 0

    def to_dict(self) -> dict:
        return {"pack": self.pack, "tolerance_pct": self.tolerance_pct, "generated_at": self.generated_at,
                "golden_manifest": self.golden_manifest, "mes_source": self.mes_source,
                "warnings": self.warnings, "counts": self.counts, "exit_code": self.exit_code,
                "cells": [c.to_dict() for c in self.cells],
                "scenarios": [asdict(s) for s in self.scenarios]}


def _pct(mes: float, excel: float) -> float:
    return abs(mes - excel) / abs(excel) * 100.0


def _near_zero(v: float | None) -> bool:
    return v is None or abs(v) < 0.005


def _scaled(e: dict, mult: float) -> dict:
    """Excel line totals are one side of a multiplied section (SIDES x2); MES
    line totals already carry the section multiplier. Scale Excel to match."""
    if mult == 1.0:
        return e
    out = dict(e)
    for k in ("qty", "total"):
        if out.get(k) is not None:
            out[k] = out[k] * mult
    return out


def triage_lines(excel_lines: list[dict], mes_lines: list[MesLine_like],
                 multiplier: float = 1.0) -> tuple[list[LineTriage], str | None]:
    """Pair Excel and MES lines by normalised description (duplicates pair in
    order); leftovers pair by prefix (Excel '130*62MM TAPPING BLOCKS' against
    MES '..._200MM' + '..._250MM' become one grouped row)."""
    pool: dict[str, list] = {}
    for m in mes_lines:
        if m.excluded:
            continue
        pool.setdefault(norm_name(m.desc), []).append(m)
    out: list[LineTriage] = []
    unmatched_excel: list[dict] = []
    for e0 in excel_lines:
        e = _scaled(e0, multiplier)
        key = norm_name(e["desc"])
        m = pool[key].pop(0) if pool.get(key) else None
        et = e.get("total")
        if m is None:
            if e.get("stale"):
                out.append(LineTriage(e["desc"], e.get("qty"), e.get("price"), et, None, None, None,
                                      -(et or 0.0), "STALE_LINK"))
            elif _near_zero(et):
                continue            # a zero Excel line with no MES twin is not a difference
            else:
                unmatched_excel.append(e)
            continue
        delta = (m.total or 0.0) - (et or 0.0)
        # Money first: a line whose rand total agrees is OK even when the two
        # sides spell qty x price differently (Excel "1 plate at R190" vs MES
        # "2 x R95"). Only a real rand difference gets classified.
        if abs(delta) <= max(abs(et or 0.0), 1.0) * LINE_TOL_PCT / 100.0:
            cls = "OK"
        else:
            price_diff = qty_diff = False
            if e.get("price") is not None and not _near_zero(e["price"]):
                price_diff = _pct(m.price, e["price"]) > LINE_TOL_PCT
            if e.get("qty") is not None and not _near_zero(e["qty"]):
                qty_diff = _pct(m.qty, e["qty"]) > LINE_TOL_PCT
            if price_diff and qty_diff:
                cls = "BOTH"
            elif price_diff:
                cls = "PRICE_DIFF"
            elif qty_diff:
                cls = "QTY_DIFF"
            else:
                cls = "BOTH"        # e.g. Excel carries no price/qty cell for the line
        out.append(LineTriage(e["desc"], e.get("qty"), e.get("price"), et, m.qty, m.price, m.total,
                              round(delta, 2), cls, mes_formula=getattr(m, "formula", None), hint=_hint(m)))
    # second pass: prefix grouping of the leftovers
    leftovers = [m for rest in pool.values() for m in rest if not _near_zero(m.total)]
    for e in unmatched_excel:
        key = norm_name(e["desc"])
        grp = [m for m in leftovers if norm_name(m.desc).startswith(key) or key.startswith(norm_name(m.desc))]
        if not grp:
            out.append(LineTriage(e["desc"], e.get("qty"), e.get("price"), e.get("total"), None, None, None,
                                  -(e.get("total") or 0.0), "MISSING_IN_MES"))
            continue
        for m in grp:
            leftovers.remove(m)
        mt = sum(m.total for m in grp)
        mq = sum(m.qty for m in grp)
        delta = mt - (e.get("total") or 0.0)
        cls = "OK" if abs(delta) <= max(abs(e.get("total") or 0.0), 1.0) * LINE_TOL_PCT / 100.0 else "GROUP_DIFF"
        out.append(LineTriage(f"{e['desc']} ~ {len(grp)} MES line(s)", e.get("qty"), e.get("price"), e.get("total"),
                              mq, None, mt, round(delta, 2), cls))
    for m in leftovers:
        out.append(LineTriage(m.desc, None, None, None, m.qty, m.price, m.total, round(m.total, 2), "EXTRA_IN_MES",
                              mes_formula=getattr(m, "formula", None)))
    out = regroup_renames(out)
    return out, likely_cause(out)


def _word_sig(desc: str) -> frozenset:
    """A line name without its size/number tokens: '130*62MM TAPPING BLOCKS' and
    'TAPPING BLOCKS_200MM' both -> {TAPPING, BLOCKS}; '1MM GALV PLATE' and
    '1.2MM GALV PLATE' -> {GALV, PLATE}."""
    return frozenset(t for t in norm_name(desc).replace("_", " ").split() if not any(ch.isdigit() for ch in t))


def regroup_renames(tri: list[LineTriage]) -> list[LineTriage]:
    """Pair a MISSING_IN_MES line with the EXTRA_IN_MES line(s) that carry the same
    words (a rename or a size variant), so a rename shows as one GROUP_DIFF row
    with its real net difference instead of a big missing + a big extra."""
    missing = [t for t in tri if t.cls == "MISSING_IN_MES"]
    extra = [t for t in tri if t.cls == "EXTRA_IN_MES"]
    if not missing or not extra:
        return tri
    used: set[int] = set()
    merged: dict[int, LineTriage] = {}
    for t in missing:
        sig = _word_sig(t.desc)
        if not sig:
            continue
        grp = [x for x in extra if id(x) not in used and _word_sig(x.desc) == sig]
        if not grp:
            continue
        used.update(id(x) for x in grp)
        et = t.excel_total or 0.0
        mt = sum(x.mes_total or 0.0 for x in grp)
        delta = mt - et
        cls = "OK" if abs(delta) <= max(abs(et), 1.0) * LINE_TOL_PCT / 100.0 else "GROUP_DIFF"
        merged[id(t)] = LineTriage(f"{t.desc} ~ {' + '.join(x.desc for x in grp)}", t.excel_qty, t.excel_price,
                                   t.excel_total, sum(x.mes_qty or 0.0 for x in grp),
                                   grp[0].mes_price if len(grp) == 1 else None, mt, round(delta, 2), cls,
                                   mes_formula=grp[0].mes_formula if len(grp) == 1 else None)
    return [merged.get(id(t), t) for t in tri if id(t) not in used]


def likely_cause(tri: list[LineTriage]) -> str | None:
    diffs = [t for t in tri if t.cls != "OK"]
    if not diffs:
        return None
    top = max(diffs, key=lambda t: abs(t.delta))
    return f"{top.cls} {top.desc} ({top.delta:+.2f})" + (f" [{top.hint}]" if top.hint else "")


class MesLine_like:      # structural type for triage (MesLine or a test double)
    desc: str
    qty: float
    price: float
    total: float
    excluded: bool


def _mark(cell: Cell, primary: Accepted, others: list[Accepted], today: date | None) -> Cell:
    cell.accepted = primary.to_dict()
    if others:
        cell.accepted["also"] = [o.to_dict() for o in others]
        if any(o.kind == "known_defect" for o in others):
            cell.accepted["kind"] = "known_defect"
    expired = [a for a in [primary, *others] if a.expired(today)]
    cell.status = "EXPIRED" if expired else "ACCEPTED"
    if expired:
        cell.reason = f"accepted entry {expired[0].index} review_by {expired[0].review_by} has passed"
    return cell


def apply_accepted(cell: Cell, accepted: list[Accepted], today: date | None = None,
                   tolerance_pct: float = 1.0) -> Cell:
    """Grey a FLAG / PRESENCE / UNMAPPED cell when accepted entries cover it.

    PRESENCE / UNMAPPED (a whole section on one side only): an in-scope entry
    whose cause names the cell's reason or likely cause covers it.
    FLAG (both sides priced): the lines named by the in-scope entries' causes
    must account for the section's net difference to within the tolerance —
    otherwise the cell stays a FLAG, and its reason says what is unexplained."""
    if cell.status not in ("FLAG", "PRESENCE", "UNMAPPED"):
        return cell
    cell.base_status = cell.status
    names = [cell.section_excel, cell.section_mes]
    scope = [a for a in accepted if a.in_scope(sheet=cell.sheet, trailer_id=cell.trailer_id,
                                                section_names=names, variant=cell.variant)]
    if not scope:
        return cell
    blanket = [a for a in scope if not a.cause_tokens()]
    if blanket:                                    # an entry without a cause covers the whole cell
        return _mark(cell, blanket[0], [], today)
    text = f"{cell.reason or ''} {cell.likely_cause or ''}"
    if cell.status != "FLAG" or not cell.triage:
        hits = [a for a in scope if a.names_cause(text)]
        return _mark(cell, hits[0], hits[1:], today) if hits else cell
    covered: dict[int, Accepted] = {}
    for a in scope:
        toks = a.cause_tokens()
        for t in cell.triage:
            if t.cls != "OK" and id(t) not in covered and any(k in norm_name(f"{t.cls} {t.desc}") for k in toks):
                covered[id(t)] = a
    if not covered:
        return cell
    net = (cell.mes_total or 0.0) - (cell.excel_total or 0.0)
    explained = sum(t.delta for t in cell.triage if id(t) in covered)
    rest = net - explained
    base = abs(cell.excel_total or 0.0)
    if (abs(rest) / base * 100.0 if base > 0.005 else abs(rest)) > (tolerance_pct if base > 0.005 else 1.0):
        cell.reason = (f"accepted cause(s) explain {explained:+,.2f} of {net:+,.2f}; "
                       f"unexplained {rest:+,.2f}").replace(",", " ")
        return cell
    weight: dict[int, float] = {}
    by_index: dict[int, Accepted] = {}
    for t in cell.triage:
        a = covered.get(id(t))
        if a is not None:
            weight[a.index] = weight.get(a.index, 0.0) + abs(t.delta)
            by_index[a.index] = a
    order = sorted(by_index.values(), key=lambda a: -weight[a.index])
    return _mark(cell, order[0], order[1:], today)


def _underlying_status(c: dict) -> str:
    """The pre-acceptance status of a saved cell (older reports carry no base_status)."""
    if c.get("base_status"):
        return c["base_status"]
    if c.get("status") not in ("ACCEPTED", "EXPIRED"):
        return c["status"]
    r = c.get("reason") or ""
    if r.startswith(("EXTRA_IN_MES", "MISSING_IN_MES", "EXTRA_SECTION_IN_MES")):
        return "PRESENCE"
    if "no MES section" in r:
        return "UNMAPPED"
    return "FLAG"


def reapply_accepted(report: dict, accepted: list[Accepted], *, today: date | None = None,
                     note: str | None = None) -> RunReport:
    """Rebuild a RunReport from a saved report JSON with a (different) accepted
    list applied — re-evaluates a run, e.g. the prod run, without re-running MES."""
    cells: list[Cell] = []
    for c in report["cells"]:
        d = dict(c)
        tri = regroup_renames([LineTriage(**t) for t in d.pop("triage", [])])
        d.pop("accepted", None)
        base = _underlying_status(d)
        d["status"] = base
        d["base_status"] = None
        if str(d.get("reason") or "").startswith(("accepted entry", "accepted cause")):
            d["reason"] = None
        if tri:
            d["likely_cause"] = likely_cause(tri)
        cell = Cell(**d, triage=tri)
        cells.append(apply_accepted(cell, accepted, today, report["tolerance_pct"]))
    rows = [ScenarioRow(**s) for s in report.get("scenarios", [])]
    warnings = list(report.get("warnings") or [])
    if note:
        warnings.append(note)
    return RunReport(pack=report["pack"], tolerance_pct=report["tolerance_pct"],
                     generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     golden_manifest=report.get("golden_manifest") or {},
                     mes_source=str(report.get("mes_source", "?")) + " (re-evaluated from the run of "
                                + str(report.get("generated_at", "?")) + ")",
                     warnings=warnings, cells=cells, scenarios=rows)


def compare_scenario(golden: dict, mes: MesResult, *, tolerance_pct: float,
                     accepted: list[Accepted], today: date | None = None) -> list[Cell]:
    sc = golden["scenario"]
    mapper = SectionMapper(list(mes.sections.keys()), sc.get("section_map"))
    cells: list[Cell] = []
    used_mes: set[str] = set()
    base = dict(scenario_id=sc["id"], sheet=sc["sheet"], trailer_id=sc["trailer_id"], trailer_name=mes.trailer_name,
                variant=sc["variant"], length=sc["length"], width=sc["width"], height=sc["height"])

    def finish(cell: Cell) -> Cell:
        return apply_accepted(cell, accepted, today, tolerance_pct)

    for ex_name, gs in golden["sections"].items():
        mes_name = mapper.to_mes(ex_name)
        ex_total = gs.get("total")
        if gs.get("status") != "OK":
            cells.append(finish(Cell(**base, section_excel=ex_name, section_mes=mes_name, excel_total=ex_total,
                                     mes_total=mes.sections.get(mes_name) if mes_name else None,
                                     variance_pct=None, status="UNVERIFIABLE", reason=gs.get("reason"))))
            if mes_name:
                used_mes.add(mes_name)
            continue
        if mes_name is None:
            status = "SKIP" if _near_zero(ex_total) else "UNMAPPED"
            cells.append(finish(Cell(**base, section_excel=ex_name, section_mes=None, excel_total=ex_total,
                                     mes_total=None, variance_pct=None, status=status,
                                     reason=None if status == "SKIP" else "no MES section of that name")))
            continue
        used_mes.add(mes_name)
        mes_total = mes.sections.get(mes_name, 0.0)
        ex_zero, mes_zero = _near_zero(ex_total), _near_zero(mes_total)
        if ex_zero and mes_zero:
            cells.append(Cell(**base, section_excel=ex_name, section_mes=mes_name, excel_total=ex_total,
                              mes_total=mes_total, variance_pct=None, status="SKIP"))
            continue
        mes_lines = [l for l in mes.lines if l.section == mes_name]
        if ex_zero or mes_zero:
            tri, cause = triage_lines(gs.get("lines", []), mes_lines, gs.get("multiplier") or 1.0)
            cells.append(finish(Cell(**base, section_excel=ex_name, section_mes=mes_name, excel_total=ex_total,
                                     mes_total=mes_total, variance_pct=None, status="PRESENCE",
                                     reason="EXTRA_IN_MES" if ex_zero else "MISSING_IN_MES",
                                     likely_cause=cause, triage=tri)))
            continue
        pct = _pct(mes_total, ex_total)
        if pct <= tolerance_pct:
            cells.append(Cell(**base, section_excel=ex_name, section_mes=mes_name, excel_total=ex_total,
                              mes_total=mes_total, variance_pct=round(pct, 3), status="PASS"))
        else:
            tri, cause = triage_lines(gs.get("lines", []), mes_lines, gs.get("multiplier") or 1.0)
            cells.append(finish(Cell(**base, section_excel=ex_name, section_mes=mes_name, excel_total=ex_total,
                                     mes_total=mes_total, variance_pct=round(pct, 3), status="FLAG",
                                     likely_cause=cause, triage=tri)))
    for mes_name, total in mes.sections.items():
        if mes_name in used_mes or _near_zero(total):
            continue
        mes_lines = [l for l in mes.lines if l.section == mes_name]
        tri, cause = triage_lines([], mes_lines)
        cells.append(finish(Cell(**base, section_excel=None, section_mes=mes_name, excel_total=None,
                                 mes_total=total, variance_pct=None, status="PRESENCE",
                                 reason="EXTRA_SECTION_IN_MES", likely_cause=cause, triage=tri)))
    return cells


def build_report(*, pack_name: str, tolerance_pct: float, manifest: dict, mes_source: str,
                 goldens: dict[str, dict], results: dict[str, MesResult], scenario_ids: list[str],
                 accepted: list[Accepted], warnings: list[str], today: date | None = None) -> RunReport:
    cells: list[Cell] = []
    rows: list[ScenarioRow] = []
    for sid in scenario_ids:
        g = goldens.get(sid)
        if g is None:
            cells.append(Cell(scenario_id=sid, sheet="?", trailer_id=0, trailer_name="", variant="?",
                              length=0, width=0, height=0, section_excel=None, section_mes=None,
                              excel_total=None, mes_total=None, variance_pct=None, status="NO_GOLDEN",
                              reason="scenario not in golden — re-run `audit golden`"))
            continue
        m = results[sid]
        cells.extend(compare_scenario(g, m, tolerance_pct=tolerance_pct, accepted=accepted, today=today))
        rows.append(ScenarioRow(scenario=g["scenario"], excel_grand=g.get("grand_total"), mes_grand=m.grand_total,
                                findings=list(g.get("findings") or []), unmatched_flags=m.unmatched_flags,
                                notes=m.notes, payload=m.payload))
    return RunReport(pack=pack_name, tolerance_pct=tolerance_pct,
                     generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     golden_manifest=manifest, mes_source=mes_source, warnings=warnings,
                     cells=cells, scenarios=rows)
