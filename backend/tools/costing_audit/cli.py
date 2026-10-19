"""`python -m tools.costing_audit <command>` — see the package docstring."""
from __future__ import annotations

import argparse
import json
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

def _golden(pack_arg: str, workbook_dir: str, *, golden_dir, work_dir, soffice, sheet_maps, prove: bool,
            provenance: str | None = None) -> Path:
    from .excel_oracle import ExcelOracle, write_golden
    from .scenarios import load_pack, expand_pack
    prov = None
    if provenance:
        # RT2 — a CORRECTED workbook set (Burt-authorised corrections made on a copy) carries its
        # provenance into the manifest: the source, each correction, its authority, and the proof
        # that replaces prove-then-trust (Burt's cached results predate the corrections).
        prov = json.loads(Path(provenance).read_text(encoding="utf-8"))
        files = {k.split()[0]: v for k, v in (prov.get("files", {}).get("corrected") or {}).items()}
        if not files:
            raise SystemExit(f"{provenance}: no 'files.corrected' block — not a build_corrected_set.py provenance")
    pack = load_pack(_pack_path(pack_arg))
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix=f"costing_audit_{pack.name}_"))
    o = ExcelOracle(Path(workbook_dir), work_dir=work, soffice=soffice, sheet_maps_dir=sheet_maps, log=_log)
    if prov is not None:
        want = {k.split()[0]: v for k, v in prov["files"]["corrected"].items()}
        have = {k.split()[0]: v for k, v in o.fingerprint.items()}
        if want != have:
            raise SystemExit(f"--provenance names files {want}, but {workbook_dir} holds {have}")
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
    out = write_golden(pack, o, results, scenarios, golden_dir=golden_dir, provenance=prov,
                       prove="ran" if prove else ("replaced by the corrections proof" if prov else "skipped"))
    _log(f"[golden] wrote {out}")
    return out


def cmd_golden(a) -> int:
    _golden(a.pack, a.workbook_dir, golden_dir=a.golden_dir, work_dir=a.work_dir, soffice=a.soffice,
            sheet_maps=a.sheet_maps, prove=not a.no_prove, provenance=a.provenance)
    return 0


# ── run ─────────────────────────────────────────────────────────────────

def cmd_run(a) -> int:
    from .accepted import load_accepted
    from .mes_probe import MesProbe
    from .report import write_all
    from .runner import golden_for, cost_and_compare
    from .scenarios import load_pack
    pack = load_pack(_pack_path(a.pack))
    if a.live_excel:
        if not a.workbook_dir:
            raise SystemExit("--live-excel needs --workbook-dir")
        _golden(a.pack, a.workbook_dir, golden_dir=a.golden_dir, work_dir=a.work_dir, soffice=a.soffice,
                sheet_maps=a.sheet_maps, prove=not a.no_prove)
    manifest, goldens, warnings = golden_for(pack, a.golden_dir)
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
    # every golden scenario of this pack runs (runner.cost_and_compare — the admin page's path too)
    try:
        rep = cost_and_compare(pack.name, manifest, goldens, probe=probe, accepted=accepted,
                               tolerance_pct=tolerance, mes_source=mes_source, warnings=warnings)
    finally:
        probe.close()
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


# ── pin (RT7) ────────────────────────────────────────────────────────────

PIN_HEADER = """\
# Known, explained Excel <-> MES differences — the PROD baseline (RT7, v1.61.1). WRITTEN BY `audit pin`.
# Used by `audit run --env prod` (CI over mes_snapshot/all.json; the admin page on prod) and `audit reaccept --env prod`.
#
# Every entry PINS ITS AMOUNTS (RT7_RULING_1): `amounts` lists, per cell it accepts, the difference MES - Excel it
# accepted ("<scenario id> | <section>": rand). A covered cell whose difference moves by more than R0.01, or a cell
# newly in scope, is a FLAG: ACCEPTED_AMOUNT_CHANGED. `cause:` matches triage LINES; `mechanism:` says what the
# difference is; `refs:` says what clears it; `review_by` fails the run loudly when it passes.
# `pair:` records the CI snapshot the pins were taken against: test_rt7_pins.py asserts its digest equals
# mes_snapshot/all.json, so snapshot and list move together or not at all (H2/H3).
# To change a pin: re-run the reference run, `audit pin --report ... --env prod --write`, and commit WITH the snapshot.
"""


def cmd_pin(a) -> int:
    """Pin every entry's `amounts` from saved reports: every cell the list accepts, under every entry covering it.
    Dry-run unless --write. Refuses to write while the reports still hold unaccepted cells."""
    import json
    from datetime import datetime, timezone
    import yaml
    from .accepted import load_accepted_doc
    from .compare import FAILING, cell_net, pin_key, reapply_accepted
    from .mes_snapshot import snapshot_digest
    path = _accepted_path(a.accepted, a.env)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    items = raw.get("accepted") or [] if isinstance(raw, dict) else raw
    header = {k: v for k, v in raw.items() if k != "accepted"} if isinstance(raw, dict) else {}
    _, entries = load_accepted_doc(path, ignore_pins=True)
    pins: dict[int, dict[str, float]] = {i: {} for i in range(len(items))}
    failing: list[str] = []
    for rp in a.report:
        doc = json.loads(Path(rp).read_text(encoding="utf-8"))
        rep = reapply_accepted(doc, entries)
        for c in rep.cells:
            if c.status in ("ACCEPTED", "EXPIRED"):
                key, net = pin_key(c), cell_net(c)
                for d in [c.accepted, *(c.accepted.get("also") or [])]:
                    have = pins[d["index"]].get(key)
                    if have is not None and abs(have - net) > 0.005:
                        raise SystemExit(f"REFUSED: {key} differs between reports ({have:+.2f} vs {net:+.2f}) — "
                                         "pin from ONE reference run")
                    pins[d["index"]][key] = net
            elif c.status in FAILING:
                failing.append(f"{rep.pack}: {c.status} {pin_key(c)} {c.reason or c.likely_cause or ''}".strip())
    for i, e in enumerate(items):
        n = len(pins[i])
        vals = list(pins[i].values())
        rng = f"{min(vals):+.2f} .. {max(vals):+.2f}" if vals else "(none)"
        _log(f"  entry {i:>2} {e.get('mechanism') or '?':<28} {str(e.get('body'))[:34]:<34} "
             f"{str(e.get('section'))[:22]:<22} {n:>3} cells  {rng}" + ("   <- pins nothing: prune it (H4)" if not n else ""))
    _log(f"  {sum(len(v) for v in pins.values())} pins over {len(items)} entries; {len(failing)} unaccepted cell(s)")
    for f in failing[:30]:
        _log(f"    {f}")
    if not a.write:
        _log("dry run — nothing written (--write to write)")
        return 1 if failing else 0
    if failing:
        raise SystemExit(f"REFUSED: {len(failing)} unaccepted cell(s) in the reports — accept them first")
    for i, e in enumerate(items):
        e["amounts"] = dict(sorted(pins[i].items()))
    if a.snapshot:
        header["pair"] = {"snapshot": "mes_snapshot/all.json", "snapshot_sha256": snapshot_digest(Path(a.snapshot)),
                          "exported_at": a.exported_at, "prod_code": a.prod_code, "alembic": a.alembic,
                          "pinned_from": [Path(r).name for r in a.report],
                          "pinned_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    body = yaml.safe_dump({**header, "accepted": items}, sort_keys=False, allow_unicode=True, width=120)
    path.write_text(PIN_HEADER + body, encoding="utf-8")
    _log(f"wrote {path}")
    return 0


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
    ids = sorted({SHEET_TO_TRAILER[s] for p in packs for s in p.sheets}
                 | {int(t) for t in (a.trailers or "").split(",") if t.strip()})
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
    g.add_argument("--provenance", default=None,
                   help="corrections.json of a corrected workbook set (build_corrected_set.py): recorded in the "
                        "manifest; the workbook dir must hold exactly its 'corrected' files")
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
    s.add_argument("--trailers", default=None,
                   help="extra trailer ids beyond the packs' bodies, comma-separated (RT2's 15-body CI snapshot adds "
                        "12,15,36: the two MEAT HANGERs and RHINORANGE, which test_g1 reads)")
    s.set_defaults(fn=cmd_snapshot)

    pn = sub.add_parser("pin", help="RT7: write each accepted entry's amounts from saved reports (dry-run unless --write)")
    pn.add_argument("--report", required=True, action="append", help="report JSON of ONE reference run (repeatable)")
    pn.add_argument("--accepted", default=None)
    pn.add_argument("--env", default=None)
    pn.add_argument("--write", action="store_true", help="write the amounts (refused while any cell is unaccepted)")
    pn.add_argument("--snapshot", default=None, help="the CI snapshot the reports were run against: records the pair")
    pn.add_argument("--exported-at", default=None, help="when the snapshot was exported on prod (ISO)")
    pn.add_argument("--prod-code", default=None, help="prod's code at the export (sha)")
    pn.add_argument("--alembic", default=None, help="prod's alembic head at the export")
    pn.set_defaults(fn=cmd_pin)
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
