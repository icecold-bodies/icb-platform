"""MES BOM snapshot — the calculator's master data for a pack's bodies, as JSON.

CI has no ICB database: `seed_from_mockup` seeds MES floor mock data, not the
trailer_types / bill_of_materials / materials the calculator prices from. So
the CI gate compares golden against a COMMITTED snapshot of exactly the rows
the calc path reads, loaded into the (isolated, `_test`) CI database and then
costed through the real `_build_bom_items -> calculate_bom` path. That makes
CI an ENGINE-drift gate; DATA drift (a price edited in admin) is what the
local `audit run` against the live dev database catches.

    audit snapshot --pack P            export from DATABASE_URL -> mes_snapshot/<pack>.json
    audit run --pack P --mes-snapshot  load the snapshot first (test DB only), check it, then run
    audit load-snapshot                load + the fidelity check alone (RT7: CI's step before the packs)

The export walks the FK graph from the pack's trailers so every referenced
row (materials, categories, sections, skin formulas + items + ingredients +
SAP item codes, taping blocks, floor plates, mounting cleats, masters that
own global sections) comes along; users/customers/costings are refused.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path

from . import MES_SNAPSHOT_DIR

ROOT_TABLES_ALL = ("bom_sections", "formulas", "global_variables")
SETTING_KEYS = ("costings.pu_foam_4g_factor",)
FORBIDDEN = {"users", "user_sessions", "customers", "customer_contacts", "customer_end_users",
             "calculations", "calculations_sales_rep_audit", "validated_references", "help_request_log",
             "price_history", "bom_override_history", "quote_counter"}
# v1.57.3 — the snapshot is exported from PROD and committed as CI's baseline, so
# the export is an ALLOW-list, not only the FK-walk refusal above: a table outside
# it, or a personal-looking column in one, refuses the whole export (nothing is
# written). tests/costing_audit/test_mes_snapshot_no_people.py re-checks the file.
ALLOWED_TABLES = {
    "admin_settings", "bill_of_materials", "body_option_groups", "body_option_subgroups",
    "bom_sections", "floor_plate_items", "floor_plates", "formulas", "global_variables",
    "material_categories", "materials", "mounting_cleat_items", "mounting_cleats",
    "report_templates", "sap_item_codes", "skin_formula_ingredients", "skin_formula_items",
    "skin_formulas", "taping_block_items", "taping_blocks", "trailer_groups", "trailer_types",
}
PERSONAL_COLUMN = re.compile(
    r"e_?mail|phone|telephone|mobile|whatsapp|fax|username|password|first_name|last_name|"
    r"full_name|contact_name|customer|end_user|address|id_number|vat_number", re.I)


def check_pricing_only(tables: dict[str, list[dict]]) -> None:
    """Raise unless every table is allow-listed and no column looks personal."""
    extra = sorted(set(tables) - ALLOWED_TABLES)
    if extra:
        raise RuntimeError(f"snapshot would carry non-pricing table(s) {extra} — refusing to export")
    cols = sorted({f"{t}.{c}" for t, rows in tables.items() for r in rows for c in r if PERSONAL_COLUMN.search(c)})
    if cols:
        raise RuntimeError(f"snapshot would carry personal-looking column(s) {cols} — refusing to export")


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
    check_pricing_only(doc["tables"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=0, default=str), encoding="utf-8")
    log(f"[snapshot] {out_path.name}: " + ", ".join(f"{n} {len(rows[n])}" for n in order))
    return doc


INSERT_CHUNK = 200      # rows per INSERT — Postgres allows 65 535 bind parameters
UNDO = "__undo__"       # inserted[UNDO]: the load's undo log, replayed backwards by unload_snapshot()
# RT7 (RT7_RULING_1B §1): the rows a snapshot parent OWNS — a body's BOM rows, a recipe's items. The export carries
# every one of them, so a row under a snapshot parent that the snapshot does not carry (deleted on prod since, or put
# there by a seed or an earlier load) is stale: the load removes it and the fidelity check refuses it.
OWNED_BY = {"bill_of_materials": "trailer_type_id", "skin_formula_items": "formula_id",
            "taping_block_items": "block_id", "floor_plate_items": "plate_id", "mounting_cleat_items": "cleat_id"}
# RT7_RULING_2 Q2: the dangling foreign keys check_fidelity allows — EXACTLY these, by (table, primary key, column), with
# the value the snapshot carries. Their targets are not in the snapshot, so the loader writes them NULL. They are rows of
# a trailer 51 that prod no longer has (a queued clean-up item); any other dangling FK, or one more, fails the check.
# test_rt7_pins.py holds this list equal to the committed snapshot's dangling FKs: it shrinks when the clean-up lands.
DANGLING_REF = "body 51 orphans"
DANGLING_ALLOWED = {
    ("bill_of_materials", 7238, "trailer_type_id"): 51,
    ("bill_of_materials", 7238, "body_option_group_id"): 21,
    ("bill_of_materials", 7239, "trailer_type_id"): 51,
    ("bill_of_materials", 7239, "body_option_group_id"): 21,
    ("bill_of_materials", 7362, "trailer_type_id"): 51,
    ("bill_of_materials", 7418, "trailer_type_id"): 51,
    ("bill_of_materials", 7418, "body_option_subgroup_id"): 59,
}


def _guard_test_db(allow_non_test_db: bool, what: str) -> None:
    from app.config import settings
    from app.db_guard import resolve_db_name
    dbname = resolve_db_name(settings.DATABASE_URL)
    if not dbname.endswith("_test") and not allow_non_test_db:
        raise RuntimeError(f"refusing to {what} {dbname!r} (not a _test database)")


def _pk_of(t, row) -> tuple:
    return tuple(row[c.name] for c in t.primary_key.columns)


def _pk_where(t, pks):
    from sqlalchemy import tuple_
    cols = list(t.primary_key.columns)
    if len(cols) == 1:
        return cols[0].in_([p[0] for p in pks])
    return tuple_(*cols).in_(pks)


def _fetch(conn, t, pks) -> dict[tuple, dict]:
    """The database rows of `t` with these primary keys, as {pk: full row}."""
    from sqlalchemy import select
    pks, out = list(pks), {}
    for s in range(0, len(pks), 1000):
        for r in conn.execute(select(t).where(_pk_where(t, pks[s:s + 1000]))):
            d = dict(r._mapping)
            out[_pk_of(t, d)] = d
    return out


def _unique_keys(t) -> list[tuple[str, ...]]:
    """The table's natural keys: every unique constraint or unique index other than the primary key."""
    from sqlalchemy import UniqueConstraint
    pk = tuple(c.name for c in t.primary_key.columns)
    keys = [tuple(c.name for c in uc.columns) for uc in t.constraints if isinstance(uc, UniqueConstraint)]
    keys += [tuple(c.name for c in ix.columns) for ix in t.indexes if ix.unique]
    return [k for k in dict.fromkeys(keys) if k and k != pk]


def _set_row(conn, t, row: dict, vals: dict) -> None:
    """UPDATE one row. Core fires a column's Python-side `onupdate` when the UPDATE does not set it, so those columns
    are pinned to the row's own values — the undo log must be able to put the row back exactly."""
    vals = {**{c.name: row[c.name] for c in t.columns if c.onupdate is not None and c.name not in vals}, **vals}
    conn.execute(t.update().where(_pk_where(t, [_pk_of(t, row)])).values(vals))


def _restore_rows(conn, t, rows: list[dict]) -> None:
    """Set every column of each row back to the given values, by primary key (executemany)."""
    from sqlalchemy import and_, bindparam
    pkc = list(t.primary_key.columns)
    rest = [c for c in t.columns if not c.primary_key]
    if not rows or not rest:
        return
    stmt = (t.update().where(and_(*[c == bindparam(f"pk_{c.name}") for c in pkc]))
            .values({c.name: bindparam(f"v_{c.name}") for c in rest}))
    conn.execute(stmt, [{**{f"pk_{c.name}": r[c.name] for c in pkc}, **{f"v_{c.name}": r[c.name] for c in rest}}
                        for r in rows])


def _referrers(t):
    """(table, column) of every foreign key in the model that points at `t`."""
    from app.database import Base
    return [(rt, fk.parent.name) for rt in Base.metadata.tables.values() for fk in rt.foreign_keys
            if fk.column.table is t]


def _delete_rows(conn, t, rows: list[dict], undo: list) -> None:
    """Delete these rows (ordered DELETE, never CASCADE: a row something still references fails the load loudly).
    The rows that point at them are logged first, so an `ON DELETE SET NULL` the database applies is undone too."""
    from sqlalchemy import select
    if not rows:
        return
    pks = [_pk_of(t, r) for r in rows]
    if len(list(t.primary_key.columns)) == 1:
        ids = [p[0] for p in pks]
        for rt, col in _referrers(t):
            refs = []
            for s in range(0, len(ids), 1000):
                refs += [dict(r._mapping) for r in conn.execute(select(rt).where(rt.c[col].in_(ids[s:s + 1000])))]
            if refs:
                undo.append(("restore", rt.name, refs))
    for s in range(0, len(pks), INSERT_CHUNK):
        conn.execute(t.delete().where(_pk_where(t, pks[s:s + INSERT_CHUNK])))
    undo.append(("insert", t.name, rows))


def _write(conn, t, chunk: list[dict], pk_cols: list[str]) -> None:
    """Write snapshot rows, the primary key the conflict target: the snapshot's values win. (Before RT7: ON CONFLICT
    DO NOTHING — tests/costing_audit/test_rt7_pins.py puts that back as the negative control.)"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(t).values(chunk)
    conn.execute(stmt.on_conflict_do_update(index_elements=pk_cols, set_={
        c: stmt.excluded[c] for c in {k for r in chunk for k in r} if c not in pk_cols}))


def _displaced(t, col: str, value: str, pk: tuple) -> str:
    tag = f" ~displaced by the snapshot {'-'.join(map(str, pk))}"
    n = getattr(t.c[col].type, "length", None)
    return (value[:max(0, n - len(tag))] if n else value) + tag


def load_snapshot(path: Path, *, allow_non_test_db: bool = False, rollback: bool = False,
                  log=print, conn=None, inserted: dict | None = None) -> dict[str, int]:
    """Write the snapshot rows (ids preserved) into DATABASE_URL — THE SNAPSHOT'S ROWS WIN (RT7, RT7_RULING_1B §1).

    Before RT7 this was ON CONFLICT DO NOTHING: a row a migration or a seed had already put there kept its values,
    silently. Migration 0046 seeds `costings.pu_foam_4g_factor` (1.3631, the 2017 list's ratio), so from v1.57.3 every
    CI run priced 4G with the SEED, not prod's factor — 0.14 % off while prod held 5581/4100, 3.2 % once Michael set
    5400/4100 on 19 Oct; then every foam_4g cell FLAGged in CI and nowhere else. Now, in every table:
      * a row with a snapshot row's primary key is overwritten with the snapshot's values (upsert on the key);
      * a row holding a snapshot row's NATURAL key (a unique name / slug / key) under another id is replaced: its key is
        moved aside, the snapshot row is written, whatever pointed at the old row is re-pointed at the snapshot's, and
        the old row is deleted (the app's startup seeds: the FREEZER group, the Waste variable, the recipes);
      * a row a snapshot parent OWNS (OWNED_BY) that the snapshot does not carry is deleted.
    check_fidelity() then proves the result, column for column. A foreign key whose target the snapshot does not carry
    (orphans in the source database) is written NULL and logged — the one value that differs, by construction.

    Refuses a non-`_test` database unless explicitly allowed: this writes master data and belongs in CI / a scratch DB,
    never in dev or prod. `rollback=True` does everything inside a transaction that is rolled back.
    `conn`: load onto this connection inside a SAVEPOINT (the caller owns the outer transaction).
    `inserted`: a dict filled with {table: [primary keys THIS call inserted]} and, under UNDO, the ordered log of every
    change the load made; unload_snapshot() replays it backwards, so a shared test database is left exactly as found."""
    _ensure_backend_on_path()
    from sqlalchemy import select, text, tuple_
    from app.database import Base, engine
    _guard_test_db(allow_non_test_db, "load a snapshot into")
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    tables = Base.metadata.tables
    counts: dict[str, int] = {}
    replaced: dict[str, int] = {}
    deferred: list[tuple[str, dict, dict]] = []      # (table, pk-values, {col: value}) for cyclic FKs
    inserted_tables: list[str] = []
    undo: list = []
    # Every (table, pk) the snapshot carries. An FK whose target row is not in the snapshot (the source database's
    # orphans — body 51's on prod) is written NULL and logged rather than refused.
    present = {name: {_pk_of(tables[name], r) for r in items} for name, items in doc["tables"].items()}
    dangling: list[str] = []

    def _resolvable(t, col: str, val) -> bool:
        fk = next((f for f in t.foreign_keys if f.parent.name == col), None)
        if fk is None or val is None:
            return True
        return (val,) in present.get(fk.column.table.name, set())

    own_conn = conn is None
    if own_conn:
        conn = engine.connect()
        txn = conn.begin()
    else:
        txn = conn.begin_nested()
    try:
        # 1. natural keys: a database row holding a snapshot row's unique key under ANOTHER primary key is moved aside
        #    (its key renamed) so the snapshot row can be written; `gone` = those to re-point and delete after the write.
        gone: list[tuple[str, dict, tuple]] = []         # (table, the moved row, the snapshot pk that takes its place)
        for name, items in doc["tables"].items():
            t = tables[name]
            for key in _unique_keys(t):
                want = {tuple(r[k] for k in key): _pk_of(t, r) for r in items if all(r.get(k) is not None for k in key)}
                if not want:
                    continue
                cols = [t.c[k] for k in key]
                vals = list(want)
                clash = []
                for s in range(0, len(vals), 1000):
                    cond = cols[0].in_([v[0] for v in vals[s:s + 1000]]) if len(cols) == 1 \
                        else tuple_(*cols).in_(vals[s:s + 1000])
                    clash += [dict(r._mapping) for r in conn.execute(select(t).where(cond))]
                for row in clash:
                    nat, pk = tuple(row[k] for k in key), _pk_of(t, row)
                    if want[nat] == pk:
                        continue
                    col = next((k for k in key if isinstance(row[k], str)), None)
                    if col is None:
                        raise RuntimeError(f"{name} {dict(zip(key, nat))}: held by id {pk} in the database, by "
                                           f"{want[nat]} in the snapshot, and no text column to move it aside by")
                    undo.append(("restore", name, [dict(row)]))
                    _set_row(conn, t, row, {col: _displaced(t, col, row[col], pk)})
                    if pk not in present[name]:
                        gone.append((name, row, want[nat]))
                    replaced[name] = replaced.get(name, 0) + 1
        # 2. write every snapshot row, its primary key the conflict target: the snapshot's values win
        for name, items in doc["tables"].items():
            t = tables[name]
            fk_cols = {fk.parent.name for fk in t.foreign_keys}
            # FKs into tables not written yet (or into this table itself) are written NULL now and set by UPDATE once
            # every row exists.
            later = {fk.parent.name for fk in t.foreign_keys
                     if fk.column.table.name == name or fk.column.table.name not in inserted_tables}
            batch = []
            for r in items:
                row = dict(r)
                for col in fk_cols:
                    if row.get(col) is not None and not _resolvable(t, col, row[col]):
                        dangling.append(f"{name}.{col}={row[col]} (row {list(_pk_of(t, row))})")
                        row[col] = None
                for col in later:
                    if row.get(col) is not None:
                        pkv = {c.name: row[c.name] for c in t.primary_key.columns}
                        deferred.append((name, pkv, {col: row[col]}))
                        row[col] = None
                batch.append(row)
            before = _fetch(conn, t, present[name])         # the rows this write overwrites, as they are now
            pk_cols = [c.name for c in t.primary_key.columns]
            for start in range(0, len(batch), INSERT_CHUNK):
                _write(conn, t, batch[start:start + INSERT_CHUNK], pk_cols)
            new = [p for p in present[name] if p not in before]
            undo.append(("restore", name, list(before.values())))
            undo.append(("delete", name, new))
            if inserted is not None:
                inserted.setdefault(name, []).extend(new)
            counts[name] = len(new)
            snap_rows = {_pk_of(t, r): r for r in items}
            changed = sum(1 for p, b in before.items() if any(not _same(v, b.get(k)) for k, v in snap_rows[p].items()))
            if changed:
                replaced[name] = replaced.get(name, 0) + changed
            inserted_tables.append(name)
        for name, pkv, vals0 in deferred:
            t = tables[name]
            vals = {k: v for k, v in vals0.items() if _resolvable(t, k, v)}
            for k in set(vals0) - set(vals):
                dangling.append(f"{name}.{k}={vals0[k]} (row {list(pkv.values())})")
            if not vals:
                continue
            cond = " AND ".join(f"{k} = :pk_{k}" for k in pkv)
            sets = ", ".join(f"{k} = :v_{k}" for k in vals)
            conn.execute(text(f"UPDATE {t.fullname} SET {sets} WHERE {cond}"),
                         {**{f"pk_{k}": v for k, v in pkv.items()}, **{f"v_{k}": v for k, v in vals.items()}})
            undo.append(("null", name, pkv, list(vals)))
        # 3. the moved-aside rows: whatever points at one now points at the snapshot row that took its key; then it goes
        for name, row, spk in gone:
            t = tables[name]
            for rt, col in _referrers(t):
                refs = [dict(r._mapping) for r in conn.execute(select(rt).where(rt.c[col] == _pk_of(t, row)[0]))]
                for ref in refs:
                    undo.append(("restore", rt.name, [dict(ref)]))
                    _set_row(conn, rt, ref, {col: spk[0]})
            _delete_rows(conn, t, [_fetch(conn, t, [_pk_of(t, row)])[_pk_of(t, row)]], undo)
        # 4. rows a snapshot parent owns that the snapshot does not carry
        for child, col in OWNED_BY.items():
            if child not in doc["tables"]:
                continue
            t = tables[child]
            parent = next(fk.column.table.name for fk in t.foreign_keys if fk.parent.name == col)
            ids = [p[0] for p in present.get(parent, ())]
            extra = []
            for s in range(0, len(ids), 1000):
                extra += [dict(r._mapping) for r in conn.execute(select(t).where(t.c[col].in_(ids[s:s + 1000])))
                          if _pk_of(t, r._mapping) not in present[child]]
            if extra:
                _delete_rows(conn, t, extra, undo)
                replaced[child] = replaced.get(child, 0) + len(extra)
                log(f"[snapshot] {child}: {len(extra)} row(s) under a snapshot {parent} that the snapshot does not "
                    "carry, deleted")
        # sequences: bump past the preserved ids — FORWARD ONLY. setval is not transactional: the load deletes rows (a
        # seeded row replaced), so MAX(id) can fall below a row a rolled-back load puts back; a sequence set to it would
        # stay behind and the next insert would collide (RT7: test_rt3_bootstrap's report template, id 5).
        for name in doc["tables"]:
            t = tables[name]
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement is not False:
                seq = conn.execute(text(f"SELECT pg_get_serial_sequence('{t.fullname}', '{pk[0].name}')")).scalar()
                if seq:
                    conn.execute(text(
                        f"SELECT setval('{seq}', GREATEST(COALESCE((SELECT MAX({pk[0].name}) FROM {t.fullname}), 1), "
                        f"(SELECT last_value FROM {seq})))"))
        if rollback:
            txn.rollback()
        else:
            txn.commit()
    except Exception:
        txn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()
    if inserted is not None:
        if rollback:
            inserted.clear()                      # nothing stayed
        else:
            inserted[UNDO] = inserted.get(UNDO, []) + undo
    log("[snapshot] " + ("dry-run (rolled back): " if rollback else "loaded: ")
        + ", ".join(f"{k} {v}" for k, v in counts.items()) + " inserted"
        + ("; the snapshot's values written over " + ", ".join(f"{k} {v}" for k, v in replaced.items())
           if replaced else ""))
    if dangling:
        log(f"[snapshot] {len(dangling)} dangling FK(s) written NULL (orphans in the source database): "
            + "; ".join(dangling[:8]) + (" ..." if len(dangling) > 8 else ""))
    return counts


def _same(snap, db) -> bool:
    """A snapshot value (as JSON carries it) against the database's value for the same column."""
    if snap is None or db is None:
        return snap is None and db is None
    if isinstance(db, datetime):
        try:
            s = datetime.fromisoformat(snap) if isinstance(snap, str) else snap
        except ValueError:
            return False
        return (s.tzinfo is None) == (db.tzinfo is None) and s == db
    if isinstance(db, date):
        return str(snap) == db.isoformat()
    if isinstance(db, Decimal):
        try:
            return Decimal(str(snap)) == db
        except ArithmeticError:
            return False
    if isinstance(db, float) and isinstance(snap, (int, float)) and not isinstance(snap, bool):
        return float(snap) == db
    return json.loads(json.dumps(db, default=str)) == snap


_NOT_ALLOWED = object()


def check_fidelity(path: Path, *, conn=None, log=print) -> list[str]:
    """RT7 (RT7_RULING_1B §1, G1) — after a load, every snapshot row equals its database row, column for column, and
    no row a snapshot parent owns (OWNED_BY) is in the database without being in the snapshot. Returns the mismatches,
    each naming the table, the key and the column (empty = the database holds the snapshot). The one allowed difference
    is the loader's own: a foreign key whose target the snapshot does not carry must read NULL — and only for the
    DANGLING_ALLOWED keys (RT7_RULING_2 Q2); any other dangling foreign key is a mismatch."""
    _ensure_backend_on_path()
    from sqlalchemy import select
    from app.database import Base, engine
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    tables = Base.metadata.tables
    present = {name: {_pk_of(tables[name], r) for r in items} for name, items in doc["tables"].items()}
    problems: list[str] = []
    n_rows = n_cells = n_null = 0

    def run(c):
        nonlocal n_rows, n_cells, n_null
        for name, items in doc["tables"].items():
            t = tables[name]
            nat = next((k[0] for k in _unique_keys(t) if len(k) == 1), None)
            fks = {fk.parent.name: fk.column.table.name for fk in t.foreign_keys}
            have = _fetch(c, t, present[name])
            for r in items:
                pk = _pk_of(t, r)
                who = f"{name} " + ", ".join(f"{k.name}={v}" for k, v in zip(t.primary_key.columns, pk)) \
                    + (f" ({nat}={r.get(nat)!r})" if nat else "")
                db = have.get(pk)
                n_rows += 1
                if db is None:
                    problems.append(f"{who}: not in the database")
                    continue
                for col, v in r.items():
                    if col not in db:
                        problems.append(f"{who}: column {col} is not in the database model")
                        continue
                    want = v
                    if col in fks and v is not None and (v,) not in present.get(fks[col], set()):
                        want = None                      # dangling: written NULL by the loader
                        n_null += 1
                        if DANGLING_ALLOWED.get((name, pk[0] if len(pk) == 1 else pk, col), _NOT_ALLOWED) != v:
                            problems.append(f"{who}: {col}={v!r} points at a {fks[col]} row the snapshot does not "
                                            f"carry — not one of the {len(DANGLING_ALLOWED)} allowed ({DANGLING_REF})")
                    n_cells += 1
                    if not _same(want, db[col]):
                        problems.append(f"{who}: {col} — snapshot {want!r}, database {db[col]!r}")
        for child, col in OWNED_BY.items():
            if child not in doc["tables"]:
                continue
            t = tables[child]
            parent = next(fk.column.table.name for fk in t.foreign_keys if fk.parent.name == col)
            ids = [p[0] for p in present.get(parent, ())]
            for s in range(0, len(ids), 1000):
                for r in c.execute(select(t).where(t.c[col].in_(ids[s:s + 1000]))):
                    if _pk_of(t, r._mapping) not in present[child]:
                        problems.append(f"{child} id={r._mapping['id']}: {col}={r._mapping[col]} is a snapshot "
                                        f"{parent}, but the row is not in the snapshot")

    if conn is not None:
        run(conn)
    else:
        with engine.connect() as c:
            run(c)
    log(f"[fidelity] {n_rows} snapshot rows, {n_cells} values compared ({n_null} dangling FK(s) NULL, as written; "
        f"{len(DANGLING_ALLOWED)} allowed: {DANGLING_REF}): "
        + (f"{len(problems)} MISMATCH(ES)" if problems else "the database holds the snapshot"))
    for p in problems[:40]:
        log(f"[fidelity]   {p}")
    if len(problems) > 40:
        log(f"[fidelity]   ... and {len(problems) - 40} more")
    return problems


def unload_snapshot(inserted: dict, *, allow_non_test_db: bool = False, log=print, conn=None) -> dict[str, int]:
    """Undo a load_snapshot(inserted=...) call: replay its UNDO log backwards — delete the rows it inserted (by
    primary key, never by a natural key), put back the values it overwrote, re-insert the rows it deleted, and give
    re-pointed rows their old targets. A shared test database is left exactly as found. All in one transaction (or,
    with `conn`, a SAVEPOINT on it)."""
    _ensure_backend_on_path()
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import Base, engine
    _guard_test_db(allow_non_test_db, "unload a snapshot from")
    tables = Base.metadata.tables
    log_ = inserted.get(UNDO)
    if log_ is None:
        raise RuntimeError("no undo log — pass the dict a load_snapshot(inserted=...) call filled")
    counts: dict[str, int] = {}
    own_conn = conn is None
    if own_conn:
        conn = engine.connect()
        txn = conn.begin()
    else:
        txn = conn.begin_nested()
    try:
        for op in reversed(log_):
            kind, name = op[0], op[1]
            t = tables[name]
            if kind == "delete":
                pks = op[2]
                for s in range(0, len(pks), INSERT_CHUNK):
                    conn.execute(t.delete().where(_pk_where(t, pks[s:s + INSERT_CHUNK])))
                counts[name] = counts.get(name, 0) + len(pks)
            elif kind == "restore":
                _restore_rows(conn, t, op[2])
            elif kind == "insert":
                for s in range(0, len(op[2]), INSERT_CHUNK):
                    conn.execute(pg_insert(t).values(op[2][s:s + INSERT_CHUNK]))
            elif kind == "null":
                pkv, cols = op[2], op[3]
                cond = " AND ".join(f"{k} = :pk_{k}" for k in pkv)
                conn.execute(text(f"UPDATE {t.fullname} SET " + ", ".join(f"{c} = NULL" for c in cols)
                                  + f" WHERE {cond}"), {f"pk_{k}": v for k, v in pkv.items()})
            else:
                raise RuntimeError(f"unknown undo op {kind!r}")
        txn.commit()
    except Exception:
        txn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()
    log("[snapshot] unloaded: " + ", ".join(f"{k} {v}" for k, v in counts.items())
        + f" deleted; {len(log_)} logged change(s) undone")
    return counts


def snapshot_path(pack_name: str) -> Path:
    return MES_SNAPSHOT_DIR / f"{pack_name}.json"


def snapshot_digest(path: Path) -> str:
    """sha256 of a snapshot's CONTENT, line endings normalised to LF (RT7's matched pair): a Windows checkout with
    core.autocrlf holds the committed file as CRLF, git and CI hold it as LF — one content, one digest."""
    import hashlib
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
