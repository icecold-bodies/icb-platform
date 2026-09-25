"""LibreOffice headless: locate the binary and recalculate workbook copies.

The recipe (proven 25 Sep 2026 against the September workbook): openpyxl
writes the scenario inputs into a COPY, `soffice --headless --convert-to xlsx`
recalculates it with the PRICE + FORMULAS workbooks adjacent, and
`load_workbook(data_only=True)` reads the fresh cached values. Inputs
unchanged -> every formula cell on the three §3.0 sheets matched Excel's own
cached values to 5e-10.

Many files go into ONE soffice invocation (ratified default 11): the process
start-up dominates a single conversion, so 100 scenarios cost one start-up
plus ~1-2 s each, not 100 start-ups.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ENV_VAR = "COSTING_AUDIT_SOFFICE"

_CANDIDATES = {
    "win32": [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ],
    "darwin": ["/Applications/LibreOffice.app/Contents/MacOS/soffice"],
    "linux": ["/usr/bin/soffice", "/usr/bin/libreoffice", "/snap/bin/libreoffice"],
}


class SofficeNotFound(RuntimeError):
    pass


def find_soffice(explicit: str | None = None) -> Path:
    """Resolve the soffice binary: --soffice flag > $COSTING_AUDIT_SOFFICE > PATH >
    the platform's default install locations. Raises SofficeNotFound with the
    search order spelled out, so a missing install is a one-line fix."""
    tried: list[str] = []
    for cand in (explicit, os.environ.get(ENV_VAR)):
        if cand:
            p = Path(cand)
            if p.is_file():
                return p
            tried.append(str(p))
    on_path = shutil.which("soffice") or shutil.which("libreoffice")
    if on_path:
        return Path(on_path)
    tried.append("PATH")
    for cand in _CANDIDATES.get(sys.platform, []) + _CANDIDATES["linux"]:
        if Path(cand).is_file():
            return Path(cand)
        tried.append(cand)
    raise SofficeNotFound(
        "LibreOffice not found. Pass --soffice PATH or set %s. Tried: %s"
        % (ENV_VAR, ", ".join(tried)))


def convert_batch(files: list[Path], outdir: Path, soffice: Path | None = None,
                  timeout: float = 1800.0) -> tuple[dict[Path, Path], float]:
    """Recalculate every workbook in `files` (all in ONE soffice call) into
    `outdir`, returning ({input: output}, elapsed seconds). Every input must sit
    next to the workbooks its external links name (PRICE 2017 MARCH.xlsx,
    FORMULAS 2018.xls) — that adjacency is what resolves the cross-workbook
    price lookups."""
    if not files:
        return {}, 0.0
    exe = find_soffice(str(soffice) if soffice else None)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    names = [f.name for f in files]
    if len(set(names)) != len(names):
        raise ValueError("convert_batch needs distinct basenames (outputs land in one folder)")
    cmd = [str(exe), "--headless", "--norestore", "--nologo",
           "--convert-to", "xlsx", "--outdir", str(outdir)] + [str(f) for f in files]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("soffice failed rc=%s\n%s\n%s" % (proc.returncode, proc.stdout, proc.stderr))
    out: dict[Path, Path] = {}
    missing = []
    for f in files:
        o = outdir / (f.stem + ".xlsx")
        if o.is_file():
            out[f] = o
        else:
            missing.append(f.name)
    if missing:
        raise RuntimeError("soffice produced no output for: %s\n%s" % (", ".join(missing), proc.stdout))
    return out, round(time.time() - t0, 1)
