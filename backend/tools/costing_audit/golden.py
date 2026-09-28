"""Reading committed golden json — the run path's half of the golden files.

Kept apart from excel_oracle (which writes them) so the run path never imports
openpyxl or LibreOffice: the server-side audit (Admin -> Costing audit, v1.59)
runs where neither is installed (BA ruling: workbooks and LibreOffice stay off
the server)."""
from __future__ import annotations

import json
from pathlib import Path

from . import GOLDEN_DIR


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
