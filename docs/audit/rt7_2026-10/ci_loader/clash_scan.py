"""What does a fresh `alembic upgrade head` database already hold that the snapshot also carries?
For each snapshot table: rows in the DB, PK clashes (same PK; differing columns), natural-key clashes (a unique key
equal to a snapshot row's under ANOTHER primary key). Read-only."""
import json
import sys
from pathlib import Path

from sqlalchemy import select, text, UniqueConstraint

from app.database import Base, engine

snap = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tables = Base.metadata.tables
with engine.connect() as c:
    for name, rows in snap["tables"].items():
        t = tables[name]
        pk = [col.name for col in t.primary_key.columns]
        uniques = [tuple(col.name for col in uc.columns) for uc in t.constraints if isinstance(uc, UniqueConstraint)]
        uniques += [tuple(col.name for col in ix.columns) for ix in t.indexes if ix.unique]
        n_db = c.execute(text(f"select count(*) from {t.fullname}")).scalar()
        db_rows = [dict(r._mapping) for r in c.execute(select(t))] if n_db else []
        by_pk = {tuple(r[k] for k in pk): r for r in db_rows}
        pk_clash = [tuple(r[k] for k in pk) for r in rows if tuple(r[k] for k in pk) in by_pk]
        nat = []
        for u in uniques:
            idx = {tuple(r[k] for k in u): r for r in db_rows}
            for r in rows:
                key = tuple(r[k] for k in u)
                if None in key:
                    continue
                d = idx.get(key)
                if d is not None and tuple(d[k] for k in pk) != tuple(r[k] for k in pk):
                    nat.append((u, key, tuple(d[k] for k in pk), tuple(r[k] for k in pk)))
        print(f"{name:28} snap {len(rows):5}  db {n_db:4}  pk={pk} uniques={uniques}  pk-clash {len(pk_clash)}  natural-clash {len(nat)}")
        for x in pk_clash[:5]:
            print("     pk clash", x)
        for x in nat[:5]:
            print("     natural clash", x)
