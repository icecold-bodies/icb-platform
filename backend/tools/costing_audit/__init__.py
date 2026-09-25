"""Costing audit — Excel ↔ MES parity packs (v1.57).

Proves, per body / per section / per scenario, that the MES calculator agrees
with Burt's GRP Costings workbook. Two halves that never need each other at
the same time:

  * the Excel ORACLE (local only) — recalculates scenario copies of the
    workbook with LibreOffice headless and writes GOLDEN json;
  * the MES PROBE + COMPARATOR (local or CI) — costs the same scenarios through
    the real /api/calculate code path and diffs them against the golden.

    python -m tools.costing_audit discover --workbook-dir DIR [--sheet NAME]
    python -m tools.costing_audit golden   --pack P --workbook-dir DIR
    python -m tools.costing_audit run      --pack P [--golden-dir D] [--tolerance X]

The workbooks themselves never enter git; only the golden json does.
"""
from pathlib import Path

__version__ = "1.57.0"

# Repo-relative anchors. backend/tools/costing_audit/ -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
TESTS_DIR = BACKEND_DIR / "tests" / "costing_audit"
PACKS_DIR = TESTS_DIR / "packs"
GOLDEN_DIR = TESTS_DIR / "golden"
SHEET_MAPS_DIR = TESTS_DIR / "sheet_maps"
ACCEPTED_FILE = TESTS_DIR / "accepted_differences.yaml"
MES_SNAPSHOT_DIR = TESTS_DIR / "mes_snapshot"
