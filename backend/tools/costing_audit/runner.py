"""The run path shared by `audit run` (the CLI) and Admin -> Costing audit (v1.59).

golden json -> MES probe per scenario -> compare -> RunReport. One code path, so
the page and the CLI can never disagree about what a run found ("reuse, don't
fork"). Imports nothing from the oracle side: no openpyxl, no LibreOffice.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from .accepted import Accepted
from .compare import RunReport, build_report
from .golden import read_golden
from .scenarios import Pack, PanelSpec, Scenario


def golden_for(pack: Pack, golden_dir: Path | None = None) -> tuple[dict, dict[str, dict], list[str]]:
    """(manifest, goldens, warnings) — the warnings say when the golden is stale for the pack."""
    manifest, goldens = read_golden(pack.name, golden_dir)
    warnings: list[str] = []
    if manifest.get("pack_fingerprint") != pack.fingerprint():
        warnings.append("the pack file changed since this golden was generated — scenarios may be missing "
                        "(NO_GOLDEN) or stale; re-run `audit golden`")
    pm, gm = pack.raw.get("workbook_month"), manifest.get("workbook_month")
    if pm and gm and str(pm) > str(gm):
        warnings.append(f"pack names workbook month {pm} but the golden was generated from {gm} — regenerate golden")
    return manifest, goldens, warnings


def scenario_from_golden(g: dict) -> Scenario:
    """The Scenario a golden entry was generated for (scenario order + ids come from the
    golden: the pack expansion needs the sheet maps, which live only on the oracle side)."""
    panels = {k: PanelSpec(v["insulation"], float(v["thickness"])) for k, v in g["panels"].items()}
    return Scenario(**{**g, "panels": panels})


def cost_and_compare(pack_name: str, manifest: dict, goldens: dict[str, dict], *, probe,
                     accepted: list[Accepted], tolerance_pct: float, mes_source: str,
                     warnings: list[str], today: date | None = None,
                     on_progress: Callable[[int, int], None] | None = None,
                     check: Callable[[], None] | None = None) -> RunReport:
    """Cost every golden scenario of the pack through `probe`, then compare.

    `check()` runs before each scenario and may raise to stop the run (the admin
    page's timeout); `on_progress(done, total)` runs after each one."""
    ids = list(goldens.keys())
    results = {}
    for i, sid in enumerate(ids):
        if check is not None:
            check()
        results[sid] = probe.cost(scenario_from_golden(goldens[sid]["scenario"]))
        if on_progress is not None:
            on_progress(i + 1, len(ids))
    return build_report(pack_name=pack_name, tolerance_pct=tolerance_pct, manifest=manifest,
                        mes_source=mes_source, goldens=goldens, results=results, scenario_ids=ids,
                        accepted=accepted, warnings=warnings, today=today)


def merge_reports(reports: list[RunReport], pack_name: str = "all") -> RunReport:
    """Several packs' reports as one (the page's "All"). Cells and scenarios are kept as
    each pack produced them — every pack was compared at its own tolerance; the
    manifest keeps each pack's golden date and fingerprint."""
    if not reports:
        raise ValueError("nothing to merge")
    manifests = [r.golden_manifest or {} for r in reports]
    files = [(m.get("workbook") or {}).get("files") or {} for m in manifests]
    months = {m.get("workbook_month") for m in manifests}
    tols = {r.tolerance_pct for r in reports}
    warnings: list[str] = []
    for r in reports:
        for w in r.warnings:
            line = f"{r.pack}: {w}"
            if line not in warnings:
                warnings.append(line)
    if any(f != files[0] for f in files):
        warnings.append("the packs' golden files come from DIFFERENT workbooks — see each pack's fingerprint")
    if len(tols) > 1:
        warnings.append("packs use different tolerances: "
                        + ", ".join(f"{r.pack} {r.tolerance_pct} %" for r in reports))
    stale: dict = {}
    for m in manifests:
        stale.update(m.get("stale_links") or {})
    manifest = {
        "pack": pack_name,
        "packs": {r.pack: {"generated_at": m.get("generated_at"), "pack_fingerprint": m.get("pack_fingerprint"),
                           "scenario_count": m.get("scenario_count"), "tool_version": m.get("tool_version"),
                           "workbook_files": (m.get("workbook") or {}).get("files") or {}}
                  for r, m in zip(reports, manifests)},
        "generated_at": max((str(m.get("generated_at") or "") for m in manifests), default=""),
        "workbook_month": months.pop() if len(months) == 1 else "mixed",
        "workbook": {"files": files[0]} if all(f == files[0] for f in files) else {"files": {}},
        "stale_links": stale,
        "scenario_count": sum(int(m.get("scenario_count") or 0) for m in manifests),
    }
    return RunReport(pack=pack_name, tolerance_pct=reports[0].tolerance_pct,
                     generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     golden_manifest=manifest, mes_source=reports[0].mes_source, warnings=warnings,
                     cells=[c for r in reports for c in r.cells],
                     scenarios=[s for r in reports for s in r.scenarios])
