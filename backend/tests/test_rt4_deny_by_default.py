"""RT4 Part C — deny by default (RT4_RULING_1 Q7–Q9).

  * EVERY registered route that is not in deps.PUBLIC_ROUTES answers 401 with no session (the §3.0 sweep of all
    routes, made permanent). The gate runs before the handler, so these calls write nothing.
  * The public routes still answer: /, /login, /logout, /health, /health/version, /debug/health/ping, /mes-app.
  * /docs, /redoc, /docs/oauth2-redirect are off; /openapi.json is admin-only.
  * A page without a session still goes to /login (now with ?next=).
  * A signed-in SALES user still gets everything the calculator needs, and can price a body.
  * Prod's configuration (MES_DEMO_AUTOLOGIN_USER empty) leaves /api/mes/autologin unmounted and not public.
  * The gate is ONE app-wide dependency on every route (G1): a route added tomorrow is gated by default.

Negative control (RT4_RETURN_2): with the app-wide dependency removed from main.py, the first test fails.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text

_MARK = "RT4DD"
JSON = {"accept": "application/json"}


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _routes(app):
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods):
                yield r, m


def _url(route) -> str:
    path = route.path_format
    for name, conv in (route.param_convertors or {}).items():
        path = path.replace("{" + name + "}", "x" if type(conv).__name__ == "PathConvertor" else "1")
    return path


def test_every_route_not_on_the_public_list_needs_a_session(app_mod, client):
    from app.deps import PUBLIC_ROUTES
    open_, checked = [], 0
    for r, m in _routes(app_mod.app):
        if (r.path, m) in PUBLIC_ROUTES:
            continue
        resp = client.request(m, _url(r), headers=JSON, follow_redirects=False,
                              **({"json": {}} if m in ("POST", "PUT", "PATCH", "DELETE") else {}))
        checked += 1
        if resp.status_code != 401:
            open_.append(f"{m} {r.path} -> {resp.status_code}")
    assert checked > 400, checked                         # the whole app, not a sample
    assert not open_, "answered without a session:\n" + "\n".join(open_)


def test_the_public_routes_still_answer(client):
    h = client.get("/health")
    assert h.status_code == 200 and h.json() == {"status": "ok"}
    v = client.get("/health/version")
    assert v.status_code == 200 and set(v.json()) == {"version"} and v.json()["version"]
    assert client.get("/debug/health/ping").status_code == 200
    assert client.get("/login").status_code == 200
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 302 and root.headers["location"] == "/mes-app/"
    shell = client.get("/mes-app/", follow_redirects=False)
    assert shell.status_code == 303 and shell.headers["location"].startswith("/login?next=")
    out = client.get("/logout", follow_redirects=False)
    assert out.status_code in (302, 303) and out.headers["location"].startswith("/login")


def test_the_api_docs_are_off_and_openapi_is_admin_only(client, people):
    for url in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        assert client.get(url, follow_redirects=False).status_code == 404, url
    assert client.get("/openapi.json", headers=JSON).status_code == 401
    assert client.get("/openapi.json", headers=people["sales"]).status_code == 403
    r = client.get("/openapi.json", headers=people["admin"])
    assert r.status_code == 200 and "/api/trailers" in r.json()["paths"]


def test_a_page_without_a_session_still_goes_to_login_with_next(client):
    r = client.get("/admin/templates?x=1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/admin/templates%3Fx%3D1"
    assert client.get("/api/trailers", follow_redirects=False).status_code == 401
    assert client.get("/api/materials", follow_redirects=False).status_code == 401


# ── a signed-in sales user still prices ─────────────────────────────────────────────

def _purge(db):
    m = {"m": f"{_MARK}%"}
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
                    "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), m)
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), m)
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), m)
    db.execute(text("DELETE FROM icb_costings.user_sessions WHERE id LIKE 'rt4dd-%'"))
    db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE 'rt4dd_%'"))
    db.commit()


def _session(user_id: int, role: str) -> dict:
    from app.database import SessionLocal, UserSession
    sid = f"rt4dd-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        db.add(UserSession(id=sid, user_id=user_id, role=role, expires_at=None, csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}


@pytest.fixture
def people(app_mod):
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType, User
    with SessionLocal() as db:
        _purge(db)
        sales = User(username=f"rt4dd_sales_{uuid.uuid4().hex[:6]}", password_hash="x", role="sales", email="")
        body = TrailerType(name=f"{_MARK} BODY", is_active=True, default_length=6.0, default_width=2.5,
                           default_height=2.5)
        mat = Material(name=f"{_MARK} PANEL", unit_of_measure="each", price_per_unit=100.0)
        db.add_all([sales, body, mat])
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=body.id, material_id=mat.id, formula_expression="length*2",
                              bom_section="FRONT"))
        db.commit()
        admin = db.query(User).filter_by(username="admin").first()
        out = {"sales": _session(sales.id, "sales"), "admin": _session(admin.id, "admin"), "body": body.id}
    yield out
    with SessionLocal() as db:
        _purge(db)


def test_a_signed_in_sales_user_still_gets_what_the_calculator_needs(client, people):
    h = people["sales"]
    for url in ("/api/trailers", f"/api/trailers/{people['body']}/bom", f"/api/trailers/{people['body']}/ratios",
                "/api/bom-sections", "/api/body-option-groups", "/api/formulas", "/api/global-variables",
                "/api/materials", "/api/categories", "/api/skin-formulas", "/api/taping-blocks",
                "/api/floor-plates", "/api/mounting-cleats", "/api/sap-item-codes"):
        assert client.get(url, headers=h).status_code == 200, url
    payload = {"trailer_type_id": people["body"],
               "dimensions": {"length": 6.0, "width": 2.5, "height": 2.5},
               "overrides": {}, "body_option_selections": {}, "body_variable_overrides": {},
               "excluded_categories": [], "flag_overrides": {}, "user_excluded_bom_ids": [],
               "optional_sections_enabled": [], "insulation_foam": "32D", "profit_margin": 0,
               "chassis": {"enabled": False}}
    r = client.post("/api/calculate", json=payload, headers=h)
    assert r.status_code == 200, r.text
    assert round(float(r.json()["grand_total"]), 2) == 1200.00          # 6 m x 2 x R100


# ── autologin is never public in prod ───────────────────────────────────────────────

def _autologin_state(value: str) -> str:
    env = {**os.environ, "MES_DEMO_AUTOLOGIN_USER": value}
    code = ("import app.main as m; from app.deps import PUBLIC_ROUTES, DEV_AUTOLOGIN_ROUTE; "
            "print(any(getattr(r, 'path', '') == '/api/mes/autologin' for r in m.app.routes), "
            "DEV_AUTOLOGIN_ROUTE in PUBLIC_ROUTES)")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parents[1]), timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


def test_prods_configuration_leaves_autologin_unmounted_and_not_public():
    assert _autologin_state("") == "False False"           # prod: MES_DEMO_AUTOLOGIN_USER= (empty)
    assert _autologin_state("admin") == "True True"        # dev / journey servers


# ── G1: one shared dependency ───────────────────────────────────────────────────────

def test_the_gate_is_one_app_wide_dependency_on_every_route(app_mod):
    from app.deps import require_session_unless_public
    missing = [f"{sorted(r.methods)} {r.path}" for r in app_mod.app.routes if isinstance(r, APIRoute)
               and not any(d.call is require_session_unless_public for d in r.dependant.dependencies)]
    assert not missing, missing
