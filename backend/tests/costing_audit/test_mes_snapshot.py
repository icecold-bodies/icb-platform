"""The committed MES snapshot loads into the isolated test database — inside
a transaction that is rolled back, so the shared icb_test is left exactly as
found. This is the loader CI relies on (the CI database has no ICB BOM data);
it caught the 65 535-bind-parameter limit the smoke-only snapshot hid."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit import MES_SNAPSHOT_DIR                       # noqa: E402
from tools.costing_audit.mapping import SHEET_TO_TRAILER               # noqa: E402
from tools.costing_audit.mes_snapshot import load_snapshot, FORBIDDEN  # noqa: E402
from tools.costing_audit.scenarios import load_pack                    # noqa: E402
from tools.costing_audit import PACKS_DIR                              # noqa: E402

SNAPSHOT = MES_SNAPSHOT_DIR / "all.json"


def test_snapshot_carries_every_pack_body_and_no_personal_tables():
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert not (set(doc["tables"]) & FORBIDDEN)
    have = {r["id"] for r in doc["tables"]["trailer_types"]}
    for p in PACKS_DIR.glob("*.yaml"):
        for sheet in load_pack(p).sheets:
            assert SHEET_TO_TRAILER[sheet] in have, f"{p.name}: {sheet!r} (trailer {SHEET_TO_TRAILER[sheet]}) not in the snapshot"
    assert any(r["key"] == "costings.pu_foam_4g_factor" for r in doc["tables"]["admin_settings"])


def test_snapshot_loads_into_the_test_database_and_rolls_back():
    from app.config import settings
    from app.db_guard import resolve_db_name
    if not resolve_db_name(settings.DATABASE_URL).endswith("_test"):
        pytest.skip("needs the isolated _test database")
    from sqlalchemy import text
    from app.database import engine
    with engine.connect() as c:
        before = c.execute(text("select (select count(*) from bill_of_materials), (select count(*) from trailer_types)")).fetchone()
    counts = load_snapshot(SNAPSHOT, rollback=True, log=lambda *_: None)
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert set(counts) == set(doc["tables"])          # every table went through the loader
    assert counts["bill_of_materials"] <= len(doc["tables"]["bill_of_materials"])
    with engine.connect() as c:
        after = c.execute(text("select (select count(*) from bill_of_materials), (select count(*) from trailer_types)")).fetchone()
    assert after == before                             # rolled back: the shared test DB is untouched
