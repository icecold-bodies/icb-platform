"""MES BOM snapshot — the calculator's master data for a pack's bodies, as JSON.

CI has no ICB database: `seed_from_mockup` seeds MES floor mock data, not the
trailer_types / bill_of_materials / materials the calculator prices from. So
the CI gate compares golden against a COMMITTED snapshot of exactly the rows
the calc path reads, loaded into the (isolated, `_test`) CI database and then
costed through the real `_build_bom_items -> calculate_bom` path. That makes
CI an ENGINE-drift gate; DATA drift (a price edited in admin) is what the
local `audit run` against the live dev database catches.

    audit snapshot --pack P            export from DATABASE_URL -> mes_snapshot/<pack>.json
    audit run --pack P --mes-snapshot  load the snapshot first (test DB only), then run

The export walks the FK graph from the pack's trailers so every referenced
row (materials, categories, sections, skin formulas + items + ingredients +
SAP item codes, taping blocks, floor plates, mounting cleats, masters that
own global sections) comes along; users/customers/costings are refused.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, date, timezone
from pathlib import Path

from . import MES_SNAPSHOT_DIR

ROOT_TABLES_ALL = ("bom_sections", "formulas", "global_variables")
SETTING_KEYS = ("costings.pu_foam_4g_factor",)
FORBIDDEN = {"users", "user_sessions", "customers", "customer_contacts", "customer_end_users",
             "calculations", "calculations_sales_rep_audit", "validated_references", "help_request_log",
             "price_history", "bom_override_history", "quote_counter"}


def _ensure_backend_on_path() -> None:
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def export_snapshot(trailer_ids: list[int], out_path: Path, *, log=print) -> dict:
    """Export the calc-path rows for `trailer_ids` from DATABASE_URL."""
    _ensure_backend_on_path()
    from sqlalchemy import select, text
    from app.database import Base, engine
    md = Base.metadata
    tables = md.tables
    rows: dict[str, dict[tuple, dict]] = {}          # table -> {pk: row}
    queue: list[tuple[str, tuple]] = []

    def add(table: str, row: dict):
        pk = tuple(row[c.name] for c in tables[table].primary_key.columns)
        if pk in rows.setdefault(table, {}):
            return
        rows[table][pk] = row
        queue.append((table, pk))

    with engine.connect() as conn:
        def fetch_where(table: str, col: str, values):
            t = tables[table]
            vals = [v for v in values if v is not None]
            if not vals:
                return []
            res = conn.execute(select(t).where(t.c[col].in_(vals)))
            return [dict(r._mapping) for r in res]

        for r in fetch_where("trailer_types", "id", trailer_ids):
            add("trailer_types", r)
        for r in fetch_where("bill_of_materials", "trailer_type_id", trailer_ids):
            add("bill_of_materials", r)
        for name in ROOT_TABLES_ALL:
            for r in conn.execute(select(tables[name])):
                add(name, dict(r._mapping))
        for r in fetch_where("admin_settings", "key", list(SETTING_KEYS)):
            add("admin_settings", r)
        # one-to-many children of the recipe tables come along with their parent
        children = {"skin_formulas": [("skin_formula_items", "formula_id")],
                    "taping_blocks": [("taping_block_items", "block_id")],
                    "floor_plates": [("floor_plate_items", "plate_id")],
                    "mounting_cleats": [("mounting_cleat_items", "cleat_id")]}
        # FK closure
        while queue:
            table, pk = queue.pop()
            row = rows[table][pk]
            for fk in tables[table].foreign_keys:
                target = fk.column.table.name
                val = row.get(fk.parent.name)
                if val is None:
                    continue
                if target in FORBIDDEN:
                    raise RuntimeError(f"{table}.{fk.parent.name} points into {target} — refusing to snapshot personal data")
                tpk = tuple(val for _ in fk.column.table.primary_key.columns)
                if tpk in rows.get(target, {}):
                    continue
                for r in fetch_where(target, fk.column.name, [val]):
                    add(target, r)
            for child, col in children.get(table, []):
                for r in fetch_where(child, col, [pk[0]]):
                    add(child, r)

    # sorted_tables warns about FK cycles (bom_sections <-> bill_of_materials);
    # the loader defers those columns, so the order only needs to be sane.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        order = [t.name for t in md.sorted_tables if t.name in rows]
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "trailer_ids": sorted(trailer_ids),
           "tables": {name: [{k: _jsonable(v) for k, v in r.items()} for r in rows[name].values()] for name in order}}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=0, default=str), encoding="utf-8")
    log(f"[snapshot] {out_path.name}: " + ", ".join(f"{n} {len(rows[n])}" for n in order))
    return doc


INSERT_CHUNK = 200      # rows per INSERT — Postgres allows 65 535 bind parameters


def load_snapshot(path: Path, *, allow_non_test_db: bool = False, rollback: bool = False,
                  log=print) -> dict[str, int]:
    """Insert the snapshot rows (ON CONFLICT DO NOTHING, ids preserved) into
    DATABASE_URL. Refuses a non-`_test` database unless explicitly allowed: this
    writes master data and belongs in CI / a scratch DB, never in dev or prod.
    `rollback=True` does everything inside a transaction that is rolled back —
    the loader's own test, leaving the shared test database exactly as found."""
    _ensure_backend_on_path()
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import Base, engine
    from app.config import settings
    from app.db_guard import resolve_db_name
    dbname = resolve_db_name(settings.DATABASE_URL)
    if not dbname.endswith("_test") and not allow_non_test_db:
        raise RuntimeError(f"refusing to load a snapshot into {dbname!r} (not a _test database)")
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    md = Base.metadata
    tables = md.tables
    counts: dict[str, int] = {}
    deferred: list[tuple[str, dict, dict]] = []      # (table, pk-values, {col: value}) for cyclic FKs
    inserted_tables: list[str] = []
    # Every (table, pk) the snapshot carries. The dev database is missing some
    # FK constraints (a deleted trailer's masters survive and still own global
    # sections); a fresh CI database has them all, so an FK whose target row is
    # not in the snapshot is written NULL — and logged — rather than refused.
    present = {name: {tuple(r[c.name] for c in tables[name].primary_key.columns) for r in items}
               for name, items in doc["tables"].items()}
    dangling: list[str] = []

    def _resolvable(t, col: str, val) -> bool:
        fk = next((f for f in t.foreign_keys if f.parent.name == col), None)
        if fk is None or val is None:
            return True
        return (val,) in present.get(fk.column.table.name, set())

    conn = engine.connect()
    txn = conn.begin()
    try:
        for name, items in doc["tables"].items():
            t = tables[name]
            fk_cols = {fk.parent.name for fk in t.foreign_keys}
            # FKs into tables not inserted yet (or into this table itself) are
            # written NULL now and set by UPDATE once every row exists.
            later = {fk.parent.name for fk in t.foreign_keys
                     if fk.column.table.name == name or fk.column.table.name not in inserted_tables}
            batch = []
            for r in items:
                row = dict(r)
                for col in fk_cols:
                    if row.get(col) is not None and not _resolvable(t, col, row[col]):
                        dangling.append(f"{name}.{col}={row[col]} (row {[row[c.name] for c in t.primary_key.columns]})")
                        row[col] = None
                for col in later:
                    if row.get(col) is not None:
                        pkv = {c.name: row[c.name] for c in t.primary_key.columns}
                        deferred.append((name, pkv, {col: row[col]}))
                        row[col] = None
                batch.append(row)
            skipped = 0
            for start in range(0, len(batch), INSERT_CHUNK):
                chunk = batch[start:start + INSERT_CHUNK]
                res = conn.execute(pg_insert(t).values(chunk).on_conflict_do_nothing())
                if res.rowcount is not None and res.rowcount >= 0:
                    skipped += len(chunk) - res.rowcount
            counts[name] = len(batch) - skipped
            if skipped:
                # Rows that already existed keep their current values — the
                # target is not a snapshot mirror, and nothing here overwrites.
                log(f"[snapshot] {name}: {skipped} row(s) already present, left untouched")
            inserted_tables.append(name)
        for name, pkv, vals in deferred:
            t = tables[name]
            cond = " AND ".join(f"{k} = :pk_{k}" for k in pkv)
            sets = ", ".join(f"{k} = :v_{k}" for k in vals)
            conn.execute(text(f"UPDATE {t.fullname} SET {sets} WHERE {cond}"),
                         {**{f"pk_{k}": v for k, v in pkv.items()}, **{f"v_{k}": v for k, v in vals.items()}})
        # sequences: bump past the preserved ids
        for name in doc["tables"]:
            t = tables[name]
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement is not False:
                seq = conn.execute(text(f"SELECT pg_get_serial_sequence('{t.fullname}', '{pk[0].name}')")).scalar()
                if seq:
                    conn.execute(text(
                        f"SELECT setval('{seq}', COALESCE((SELECT MAX({pk[0].name}) FROM {t.fullname}), 1))"))
        if rollback:
            txn.rollback()
        else:
            txn.commit()
    except Exception:
        txn.rollback()
        raise
    finally:
        conn.close()
    log("[snapshot] " + ("dry-run (rolled back): " if rollback else "loaded: ")
        + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if dangling:
        log(f"[snapshot] {len(dangling)} dangling FK(s) written NULL (orphans in the source database): "
            + "; ".join(dangling[:8]) + (" ..." if len(dangling) > 8 else ""))
    return counts


def snapshot_path(pack_name: str) -> Path:
    return MES_SNAPSHOT_DIR / f"{pack_name}.json"
