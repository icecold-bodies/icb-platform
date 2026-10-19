"""RT7_RULING_1B F6 — the negative control: load with the loader as it was at 1814b0c (ON CONFLICT DO NOTHING), then
run the NEW fidelity check. Expect it to fail on admin_settings (the 4G factor). Scratch mirror only."""
import importlib.util
import sys
from pathlib import Path

from app.config import settings
from app.db_guard import resolve_db_name

if resolve_db_name(settings.DATABASE_URL) != "icb_prodmirror":
    raise SystemExit("REFUSED: scratch mirror only")
spec = importlib.util.spec_from_file_location("old_loader", sys.argv[1])
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
from tools.costing_audit.mes_snapshot import check_fidelity, snapshot_path  # noqa: E402

snap = snapshot_path("all")
old.load_snapshot(snap, allow_non_test_db=True)
problems = check_fidelity(snap)
print(f"NC: {len(problems)} mismatch(es); exit {1 if problems else 0}")
sys.exit(1 if problems else 0)
