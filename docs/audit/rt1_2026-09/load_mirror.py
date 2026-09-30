"""RT1 1c — load the LOCAL scratch mirror icb_prodmirror from the 1b prod snapshots, with the committed CI loader.

    (DATABASE_URL = icb_prodmirror, freshly reset + `alembic upgrade head`; PYTHONPATH = backend/)
    python load_mirror.py <1b all.json> <1b meat_hangers.json>

load_snapshot() is ON CONFLICT DO NOTHING (it never overwrites), so the mirror must be empty first. The one row a
fresh database already holds under the same natural key is admin_settings `costings.pu_foam_4g_factor` (migration 0046
seeds 1.3631); it is set to the snapshot's value afterwards, as the v1.58 mirror did by hand. Refuses any database but
icb_prodmirror.
"""
import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.db_guard import resolve_db_name
from app.database import engine
from tools.costing_audit.mes_snapshot import load_snapshot

KEY = "costings.pu_foam_4g_factor"


def main(*paths):
    db = resolve_db_name(settings.DATABASE_URL)
    if db != "icb_prodmirror":
        raise SystemExit(f"REFUSED: {db!r} is not the scratch mirror icb_prodmirror")
    with engine.connect() as c:
        n = c.execute(text("select count(*) from bill_of_materials")).scalar()
        if n:
            raise SystemExit(f"REFUSED: the mirror already holds {n} BOM rows — reset it first (the loader never overwrites)")
    want = None
    for p in paths:
        print(f"== {Path(p).name}")
        load_snapshot(Path(p), allow_non_test_db=True)
        for r in json.loads(Path(p).read_text(encoding="utf-8"))["tables"].get("admin_settings", []):
            if r.get("key") == KEY:
                want = r.get("value")
    with engine.begin() as c:
        have = c.execute(text("select value from admin_settings where key = :k"), {"k": KEY}).scalar()
        if want is not None and have != want:
            c.execute(text("update admin_settings set value = :v where key = :k"), {"v": want, "k": KEY})
            print(f"== {KEY}: {have} (migration 0046 seed) -> {want} (the snapshot's, prod's)")
        print("== counts:", {t: c.execute(text(f"select count(*) from {t}")).scalar()
                             for t in ("trailer_types", "bill_of_materials", "materials", "bom_sections")})


if __name__ == "__main__":
    main(*sys.argv[1:])
