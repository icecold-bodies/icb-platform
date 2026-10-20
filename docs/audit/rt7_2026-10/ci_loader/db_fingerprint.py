"""Every table of the app schemas: row count + md5 over the rows (order-free). Read-only. Prints one line per table."""
from sqlalchemy import text
from app.database import engine

with engine.connect() as c:
    tabs = c.execute(text("select table_schema, table_name from information_schema.tables where table_type = 'BASE TABLE' "
                          "and table_schema in ('icb_costings', 'icb_mes') order by 1, 2")).fetchall()
    for s, t in tabs:
        n, h = c.execute(text(f'select count(*), md5(coalesce(string_agg(md5(x::text), \'\' order by md5(x::text)), \'\')) '
                              f'from "{s}"."{t}" x')).one()
        print(f"{s}.{t} {n} {h}")
