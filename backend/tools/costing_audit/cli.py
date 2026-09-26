"""`python -m tools.costing_audit <command>` — see the package docstring."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import PACKS_DIR, GOLDEN_DIR, ACCEPTED_FILE, SHEET_MAPS_DIR, __version__
from .mapping import SHEET_TO_TRAILER


def _pack_path(arg: str) -> Path:
    p = Path(arg)
    if p.is_file():
        return p
    cand = PACKS_DIR / f"{arg}.yaml"
    if cand.is_file():
        return cand
    raise SystemExit(f"pack {arg!r} not found (looked for {cand})")


def _log(msg: str) -> None:
    print(msg, flush=True)


# ── discover ────────────────────────────────────────────────────────────

def cmd_discover(a) -> int:
    from .excel_oracle import ExcelOracle
    from .sheet_map import render_text
    work = Path(a.work_dir) if a.work_dir else Path(tempfile.mkdtemp(prefix="costing_audit_"))
    o = ExcelOracle(Path(a.workbook_dir), work_dir=work, soffice=a.soffice, sheet_maps_dir=a.sheet_maps, log=_log)
    sheets = a.sheet or list(SHEET_TO_TRAILER)
    chunks = []
    for s in sheets:
        try:
            sm = o.discover(s)
            chunks.append(render_text(sm))
        except Exception as exc:          # a non-standard sheet is a finding, not a crash
            chunks.append(f"=== {s!r}\n  NOT DISCOVERABLE: {exc}")
    text = "\n\n".join(chunks) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        _log(f"wrote {a.out}")
    else:
        sys.stdout.write(text)
    return 0


# ── golden ──────────────────────────────────────────────────────────────

def _golden(pack_arg: str, workbook_dir: str, *, golden_dir, work_dir, soffice, sheet_maps, prove: bool) -> Path:
    from .excel_oracle import ExcelOracle, write_golden
    from .scenarios import load_pack, expand_pack
    pack = load_pack(_pack_path(pack_arg))
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix=f"costing_audit_{pack.name}_"))
    o = ExcelOracle(Path(workbook_dir), work_dir=work, soffice=soffice, sheet_maps_dir=sheet_maps, log=_log)
    for s in pack.sheets:
        sm = o.discover(s)
        if not sm.selfcheck_ok:
            raise SystemExit(f"{s!r}: sheet-map self-check failed ({sm.warnings}) — fix the sheet_map before golden")
    if prove:
        problems = o.prove(pack.sheets)
        if problems:
            raise SystemExit("prove-then-trust FAILED — the recalculated null scenario does not reproduce "
                             "the workbook's cached totals:\n  " + "\n  ".join(problems))
        _log(f"[golden] prove-then-trust OK on {len(pack.sheets)} sheets")
    scenarios = expand_pack(pack, o.maps)
    _log(f"[golden] {len(scenarios)} scenarios in pack {pack.name}")
    results = o.run(scenarios)
    out = write_golden(pack, o, results, scenarios, golden_dir=golden_dir)
    _log(f"[golden] wrote {out}")
    return out


def cmd_golden(a) -> int:
    _golden(a.pack, a.workbook_dir, golden_dir=a.golden_dir, work_dir=a.work_dir, soffice=a.soffice,
            sheet_maps=a.sheet_maps, prove=not a.no_prove)
    return 0


# ── run ─────────────────────────────────────────────────────────────────

def cmd_run(a) -> int:
    from .accepted import load_accepted
    from .compare import build_report
    from .excel_oracle import read_golden
    from .mes_probe import MesProbe
    from .report import write_all
    from .scenarios import load_pack, expand_pack, Scenario
    pack = load_pack(_pack_path(a.pack))
    warnings: list[str] = []
    if a.live_excel:
        if not a.workbook_dir:
            raise SystemExit("--live-excel needs --workbook-dir")
        _golden(a.pack, a.workbook_dir, golden_dir=a.golden_dir, work_dir=a.work_dir, soffice=a.soffice,
                sheet_maps=a.sheet_maps, prove=not a.no_prove)
    manifest, goldens = read_golden(pack.name, a.golden_dir)
    if manifest.get("pack_fingerprint") != pack.fingerprint():
        warnings.append("the pack file changed since this golden was generated — scenarios may be missing "
                        "(NO_GOLDEN) or stale; re-run `audit golden`")
    pm, gm = pack.raw.get("workbook_month"), manifest.get("workbook_month")
    if pm and gm and str(pm) > str(gm):
        warnings.append(f"pack names workbook month {pm} but the golden was generated from {gm} — regenerate golden")
    if a.mes_snapshot is not None:
        from .mes_snapshot import load_snapshot, snapshot_path
        snap = Path(a.mes_snapshot) if a.mes_snapshot else snapshot_path(pack.name)
        if not snap.is_file() and not a.mes_snapshot:
            snap = snapshot_path("all")          # one snapshot covering every pack's bodies
        load_snapshot(snap, allow_non_test_db=a.allow_non_test_db, log=_log)
    tolerance = float(a.tolerance) if a.tolerance is not None else pack.tolerance_pct
    accepted_path = _accepted_path(a.accepted, a.env)
    accepted = load_accepted(accepted_path)
    if a.env:
        warnings.append(f"accepted list: {accepted_path.name} (--env {a.env})")
    probe = MesProbe(base_url=a.base_url, log=_log)
    mes_source = a.base_url or _db_label()
    # scenario order + ids come from the golden (the pack expansion needs the sheet maps,
    # which live only on the oracle side); every golden scenario of this pack runs.
    ids = list(goldens.keys())
    results = {}
    try:
        for sid in ids:
            g = goldens[sid]["scenario"]
            sc = Scenario(**{**g, "panels": {k: _panel(v) for k, v in g["panels"].items()}})
            results[sid] = probe.cost(sc)
    finally:
        probe.close()
    rep = build_report(pack_name=pack.name, tolerance_pct=tolerance, manifest=manifest, mes_source=mes_source,
                       goldens=goldens, results=results, scenario_ids=ids, accepted=accepted, warnings=warnings)
    out_dir = Path(a.out) if a.out else Path("costing_audit_reports")
    paths = write_all(rep, out_dir, stem=a.stem)
    _log(Path(paths["md"]).read_text(encoding="utf-8"))
    _log("reports: " + ", ".join(str(p) for p in paths.values()))
    return rep.exit_code


def _accepted_path(explicit: str | None, env: str | None) -> Path:
    """--accepted PATH wins; --env NAME picks tests/costing_audit/accepted_differences.<NAME>.yaml
    (each environment's data drifts on its own — dev and prod need their own baselines)."""
    if explicit:
        return Path(explicit)
    if env:
        p = ACCEPTED_FILE.with_name(f"accepted_differences.{env}.yaml")
        if not p.is_file():
            raise SystemExit(f"no accepted list for --env {env!r}: {p}")
        return p
    return ACCEPTED_FILE


def cmd_reaccept(a) -> int:
    """Re-evaluate a saved report JSON against an accepted list — no MES, no DB."""
    import json
    from .accepted import load_accepted
    from .compare import reapply_accepted
    from .report import write_all
    accepted_path = _accepted_path(a.accepted, a.env)
    accepted = load_accepted(accepted_path)
    rc = 0
    for rp in a.report:
        doc = json.loads(Path(rp).read_text(encoding="utf-8"))
        rep = reapply_accepted(doc, accepted, note=f"accepted list: {accepted_path.name}")
        out_dir = Path(a.out) if a.out else Path(rp).parent
        stem = a.stem or Path(rp).stem
        paths = write_all(rep, out_dir, stem=stem)
        _log(Path(paths["md"]).read_text(encoding="utf-8"))
        rc = max(rc, rep.exit_code)
    return rc


def _panel(d: dict):
    from .scenarios import PanelSpec
    return PanelSpec(d["insulation"], float(d["thickness"]))


def _db_label() -> str:
    try:
        from app.config import settings
        from app.db_guard import resolve_db_name, resolve_host
        return f"in-process {resolve_host(settings.DATABASE_URL)}/{resolve_db_name(settings.DATABASE_URL)}"
    except Exception:
        return "in-process"


# ── snapshot ────────────────────────────────────────────────────────────

def cmd_snapshot(a) -> int:
    from .mes_snapshot import export_snapshot, snapshot_path
    from .scenarios import load_pack
    packs = [load_pack(_pack_path(x)) for x in a.pack]
    ids = sorted({SHEET_TO_TRAILER[s] for p in packs for s in p.sheets})
    out = Path(a.out) if a.out else snapshot_path(packs[0].name if len(packs) == 1 else "all")
    export_snapshot(ids, out, log=_log)
    return 0


# ── parser ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.costing_audit",
                                description=f"Costing audit v{__version__}: Excel <-> MES parity packs")
    sub = p.add_subparsers(dest="cmd", required=True)

    def excel_args(sp):
        sp.add_argument("--workbook-dir", required=False, help="folder holding GRP Costings 2018.xlsx + PRICE + FORMULAS")
        sp.add_argument("--soffice", help="LibreOffice soffice binary (else $COSTING_AUDIT_SOFFICE / PATH / default install)")
        sp.add_argument("--sheet-maps", default=None, help=f"sheet_maps folder (default {SHEET_MAPS_DIR})")
        sp.add_argument("--work-dir", help="scratch folder for scenario copies (default: a temp dir)")

    d = sub.add_parser("discover", help="print the auto-detected cell map per sheet for review")
    excel_args(d)
    d.add_argument("--sheet", action="append", help="exact sheet name (repeatable; default: all mapped sheets)")
    d.add_argument("--out", help="write the text here instead of stdout")
    d.set_defaults(fn=cmd_discover)

    g = sub.add_parser("golden", help="run the Excel oracle locally and write golden json")
    excel_args(g)
    g.add_argument("--pack", required=True, help="pack name (tests/costing_audit/packs/<name>.yaml) or path")
    g.add_argument("--golden-dir", default=None, help=f"default {GOLDEN_DIR}")
    g.add_argument("--no-prove", action="store_true", help="skip the null-scenario prove-then-trust check")
    g.set_defaults(fn=cmd_golden)

    r = sub.add_parser("run", help="MES probe + compare vs golden -> HTML/CSV/JSON/MD; exit 1 on unaccepted FLAG")
    excel_args(r)
    r.add_argument("--pack", required=True)
    r.add_argument("--golden-dir", default=None)
    r.add_argument("--tolerance", type=float, default=None, help="percent; overrides the pack")
    r.add_argument("--base-url", default=None, help="hit a running side-port server instead of in-process")
    r.add_argument("--mes-snapshot", nargs="?", const="", default=None,
                   help="load tests/costing_audit/mes_snapshot/<pack>.json (or PATH) into the _test DB first")
    r.add_argument("--allow-non-test-db", action="store_true", help=argparse.SUPPRESS)
    r.add_argument("--accepted", default=None, help=f"default {ACCEPTED_FILE}")
    r.add_argument("--env", default=None, help="use tests/costing_audit/accepted_differences.<env>.yaml (e.g. prod)")
    r.add_argument("--live-excel", action="store_true", help="golden + run in one go (local only)")
    r.add_argument("--no-prove", action="store_true")
    r.add_argument("--out", default=None, help="report folder (default ./costing_audit_reports)")
    r.add_argument("--stem", default=None, help="report file stem (default costing_audit_<pack>)")
    r.set_defaults(fn=cmd_run)

    ra = sub.add_parser("reaccept", help="re-apply an accepted list to a saved report JSON (no MES needed)")
    ra.add_argument("--report", required=True, action="append", help="report JSON (repeatable)")
    ra.add_argument("--accepted", default=None)
    ra.add_argument("--env", default=None)
    ra.add_argument("--out", default=None, help="folder for the rewritten reports (default: beside the JSON)")
    ra.add_argument("--stem", default=None, help="only with one --report")
    ra.set_defaults(fn=cmd_reaccept)

    s = sub.add_parser("snapshot", help="export the MES master data the packs' bodies need (for CI)")
    s.add_argument("--pack", required=True, action="append", help="repeatable; several packs -> mes_snapshot/all.json")
    s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_snapshot)
    return p


def main(argv: list[str] | None = None) -> int:
    # The summaries carry non-cp1252 characters; a redirected Windows stdout
    # must never turn a finished run into a UnicodeEncodeError exit 1.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    a = build_parser().parse_args(argv)
    return int(a.fn(a) or 0)
