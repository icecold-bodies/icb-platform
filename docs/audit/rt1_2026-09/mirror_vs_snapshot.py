"""RT1 — READ ONLY: does the database hold exactly the snapshot? Every snapshot row, column by column.

    (DATABASE_URL = the mirror; PYTHONPATH = backend/)  python mirror_vs_snapshot.py <all.json> [<meat_hangers.json> …]

Values are compared as the snapshot stores them (the exporter's JSON form: datetimes as ISO text). Prints the
identical count, and every differing / missing row with its columns. Used after the mirror load (mirror = prod)
and after each revert (the revert is byte-exact: the mirror is back at the loaded snapshot).
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select, text

from app.database import Base, engine
import app.models.mes  # noqa: F401  (registers the icb_mes models, as alembic's env does)


def jsonable(v):
    """The exporter's JSON form: datetimes via isoformat, anything else non-JSON (Decimal, …) via str()."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if v is None or isinstance(v, (str, int, float, bool, list, dict)):
        return v
    return str(v)


def main(paths):
    tables = Base.metadata.tables
    rows = {}
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        for t, items in doc["tables"].items():
            for r in items:
                pk = tuple(r[c.name] for c in tables[t].primary_key.columns)
                rows.setdefault(t, {})[pk] = r
    same = total = 0
    problems = []
    with engine.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("database:", c.execute(text("select current_database()")).scalar())
        for t, want in rows.items():
            tab = tables[t]
            pkc = list(tab.primary_key.columns)
            have = {}
            keys = list(want)
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                if len(pkc) == 1:
                    q = select(tab).where(pkc[0].in_([k[0] for k in chunk]))
                else:
                    from sqlalchemy import tuple_
                    q = select(tab).where(tuple_(*pkc).in_(chunk))
                for r in c.execute(q):
                    m = dict(r._mapping)
                    have[tuple(m[x.name] for x in pkc)] = {k: jsonable(v) for k, v in m.items()}
            for pk, w in want.items():
                total += 1
                h = have.get(pk)
                if h is None:
                    problems.append(f"{t} {pk}: MISSING")
                    continue
                cols = [k for k in w if w[k] != h.get(k)]
                if cols:
                    problems.append(f"{t} {pk}: " + "; ".join(f"{k} snapshot {w[k]!r} db {h.get(k)!r}" for k in cols))
                else:
                    same += 1
    print(f"{same} of {total} snapshot rows identical, {len(problems)} not:")
    for p in problems[:60]:
        print("  ", p)
    if len(problems) > 60:
        print(f"   … {len(problems) - 60} more")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
