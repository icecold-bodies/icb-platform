"""RT4 Part C §3.0 — call EVERY registered route with NO session cookie and record what answers.

Runs in-process (TestClient, startup NOT run) with EVERY database session read-only at the server
(PGOPTIONS default_transaction_read_only=on, asserted before the first call): nothing can be written, and an
open route that tries to write shows up as a 500. Every outbound channel off, demo autologin off (wt4.ps1).
Writes routes x methods -> status / content-type / bytes / shape.
Pass 1: ints = 1, strings = 'x', body {}. Pass 2 (only rows that came back 400/404/405/422/500): real ids
picked by parameter name, required query params filled, so a lookup-before-auth shows up.
"""
import json, re, sys
from pathlib import Path

import os
assert "default_transaction_read_only=on" in os.environ.get("PGOPTIONS", ""), "PGOPTIONS read-only is required"
from app.config import settings
assert os.environ.get("MES_DEMO_AUTOLOGIN_USER") == "", "autologin must be OFF (prod-like)"
assert not settings.SMTP_URL and not settings.TWILIO_AUTH_TOKEN and not os.environ.get("ANTHROPIC_API_KEY")

from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from starlette.routing import Mount, Route
from sqlalchemy import text
from app.main import app
from app.database import engine

OUT = Path(sys.argv[1])


def shape(resp) -> str:
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        try:
            j = resp.json()
        except Exception:
            return "json?"
        if isinstance(j, list):
            keys = sorted(j[0].keys())[:14] if j and isinstance(j[0], dict) else []
            return f"list[{len(j)}]" + (f" of {{{', '.join(keys)}}}" if keys else "")
        if isinstance(j, dict):
            if set(j) == {"detail"}:
                return f"detail: {str(j['detail'])[:90]}"
            return "{" + ", ".join(sorted(j.keys())[:16]) + (", …" if len(j) > 16 else "") + "}"
        return type(j).__name__
    if "html" in ct:
        m = re.search(r"<title>(.*?)</title>", resp.text, re.S | re.I)
        return f"html <title>{(m.group(1).strip() if m else '')[:60]}</title>"
    return ct.split(";")[0] or "-"


# ---- ids for pass 2, by parameter name -------------------------------------------------------------------
with engine.connect() as c:
    ro = c.execute(text("show transaction_read_only")).scalar()
    assert ro == "on", f"session is not read-only ({ro}) — refusing to sweep"
    print("db:", c.execute(text("select current_database()")).scalar(), "| read-only:", ro)

    def first(sql):
        try:
            return c.execute(text(sql)).scalar()
        except Exception:
            c.rollback()
            return None
    REAL = {
        "trailer": first("select id from trailer_types where is_active order by id desc limit 1"),
        "bom": first("select id from bill_of_materials order by id limit 1"),
        "calc": first("select id from calculations order by id desc limit 1"),
        "section": first("select id from bom_sections order by id limit 1"),
        "material": first("select id from materials order by id limit 1"),
        "customer": first("select id from customers order by id limit 1"),
        "user": first("select id from users order by id limit 1"),
        "formula": first("select id from formulas order by id limit 1"),
        "skin": first("select id from skin_formulas order by id limit 1"),
        "group": first("select id from trailer_groups order by id limit 1"),
    }
print("pass-2 ids:", REAL)


def pick(name: str, pass_no: int) -> str:
    if pass_no == 1:
        return "1"
    n = name.lower()
    for key, val in (("trailer", "trailer"), ("tt_id", "trailer"), ("body", "trailer"), ("bom", "bom"),
                     ("record", "calc"), ("calc", "calc"), ("costing", "calc"), ("section", "section"),
                     ("material", "material"), ("customer", "customer"), ("user", "user"),
                     ("formula", "formula"), ("skin", "skin"), ("group", "group"), ("family", "group")):
        if key in n and REAL.get(val) is not None:
            return str(REAL[val])
    return "1"


def concrete(route, pass_no):
    path = route.path_format if hasattr(route, "path_format") else route.path
    for pname, conv in (route.param_convertors or {}).items():
        cname = type(conv).__name__
        if cname == "PathConvertor":
            val = "x"
        elif cname in ("IntegerConvertor", "FloatConvertor"):
            val = pick(pname, pass_no)
        else:
            # untyped {param}: FastAPI validates it against the handler annotation
            val = pick(pname, pass_no)
        path = path.replace("{" + pname + "}", val)
    return path


def query_for(route, pass_no):
    if pass_no == 1 or not isinstance(route, APIRoute):
        return {}
    q = {}
    for p in route.dependant.query_params:
        if p.required:
            ann = getattr(p, "type_", None) or getattr(p.field_info, "annotation", None)
            q[p.alias] = "1" if ann in (int, float) else "x"
    return q


rows = []
client = TestClient(app, raise_server_exceptions=False)     # no `with`: the startup seed never runs
if True:
    client.cookies.clear()
    for pass_no in (1, 2):
        targets = []
        if pass_no == 1:
            for r in app.routes:
                if isinstance(r, Mount):
                    continue
                for m in sorted(getattr(r, "methods", None) or []):
                    if m == "HEAD" and "GET" in r.methods:
                        continue
                    targets.append((r, m))
        else:
            redo = {(x["path"], x["method"]) for x in rows if x["status"] in (400, 404, 405, 422, 500)}
            targets = [(r, m) for r in app.routes if not isinstance(r, Mount)
                       for m in sorted(getattr(r, "methods", None) or []) if (r.path, m) in redo]
        for r, m in targets:
            url = concrete(r, pass_no)
            kw = {"params": query_for(r, pass_no), "follow_redirects": False,
                  "headers": {"accept": "application/json, text/html;q=0.9, */*;q=0.8"}}
            if m in ("POST", "PUT", "PATCH", "DELETE"):
                kw["json"] = {}
            client.cookies.clear()
            try:
                resp = client.request(m, url, **kw)
                st, sh, ct, n = resp.status_code, shape(resp), resp.headers.get("content-type", ""), len(resp.content)
                loc = resp.headers.get("location", "")
            except Exception as e:                       # a handler that blows up in-process
                st, sh, ct, n, loc = 599, f"EXC {type(e).__name__}: {str(e)[:80]}", "", 0, ""
            ep = getattr(r, "endpoint", None)
            rows.append({"pass": pass_no, "method": m, "path": r.path, "url": url, "status": st,
                         "location": loc, "content_type": ct.split(";")[0], "bytes": n, "shape": sh,
                         "endpoint": f"{getattr(ep, '__module__', '?')}.{getattr(ep, '__qualname__', '?')}",
                         "in_schema": getattr(r, "include_in_schema", True)})
        print(f"pass {pass_no}: {len(targets)} calls")

OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
final = {}
for x in rows:
    final[(x["path"], x["method"])] = x          # pass 2 overrides pass 1
from collections import Counter
print("final status counts:", Counter(x["status"] for x in final.values()))
