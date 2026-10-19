"""Every serial sequence in the app schemas whose last_value is below its table's MAX(id). Read-only unless --fix,
which moves each such sequence FORWARD to MAX(id) (never back). Test databases only."""
import sys
from sqlalchemy import text
from app.config import settings
from app.db_guard import resolve_db_name
from app.database import engine

db = resolve_db_name(settings.DATABASE_URL)
fix = "--fix" in sys.argv
if fix and not db.endswith("_test"):
    raise SystemExit(f"REFUSED: {db} is not a _test database")
q = text("""select n.nspname, c.relname, a.attname, pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) as seq
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
           where c.relkind = 'r' and n.nspname in ('icb_costings', 'icb_mes')
             and pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) is not null""")
with engine.begin() as c:
    behind = 0
    for s, t, col, seq in c.execute(q).fetchall():
        mx = c.execute(text(f'select max("{col}") from "{s}"."{t}"')).scalar()
        last = c.execute(text(f"select last_value from {seq}")).scalar()
        if mx is not None and last < mx:
            behind += 1
            print(f"BEHIND {s}.{t}.{col}: sequence {last} < max {mx}" + (" -> fixed" if fix else ""))
            if fix:
                c.execute(text(f"select setval('{seq}', :m)"), {"m": mx})
    print(f"{db}: {behind} sequence(s) behind")
