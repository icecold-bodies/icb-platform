"""v1.43 — MES sole front door (micro-WO, Michael ratified 24 Jul).

The bare root "/" no longer lands on the legacy GRP Costings dashboard: it 302s to
/mes-app/ (302 exactly, NOT 301 — browsers hard-cache 301, which would make the
front-door swap painful to reverse). Unauthenticated, the chain continues to
/login?next=/mes-app/ through the v1.40.1 SPA gate — that chain is intended.

Everything the MES embeds must stay reachable, so this file doubles as the
regression-guard bundle for the DO-NOT-BREAK surface:

* /calculator                 — New Costing iframe target's live sibling (dark UI)
* /results/{id} (+?skin=mes)  — CostingResultsView iframe + "Print costing PDF"
* /mes-app/                   — the SPA shell + its login chain
* /api/mes-materials          — canary for the live ERP read surface (/api/* untouched)

Runs against icb_test (conftest db-guard). Auth uses the raw-Cookie-header
UserSession pattern (test_integration_token_auth.py precedent) so the shared
session-scoped TestClient's jar stays unauthenticated for the smoke tests.
Costing rows are seeded directly — the /api/approve pipeline needs the full BOM
universe the test DB doesn't have (test_costings_contact_column_journey.py
precedent); marker rows ZLFD* purged both sides.
"""
import uuid

import pytest

MARK = "ZLFD"

# Just enough result_json for results.html to render: the template pipes these
# through strict filters (|float) and iterates the dicts, so absent keys raise
# even under lenient Jinja undefined.
RESULT_JSON = ('{"items": [], "grand_total": 0, "selling_price": 0, "cost_per_sqm": 0, '
               '"profit_margin": 0, "profit_amount": 0, "ratio_label": "", "ratio_amount": 0, '
               '"geometry": {}, "category_totals": {}, "category_multipliers": {}}')


@pytest.fixture
def admin_cookie():
    """A real UserSession row for the seeded admin (expires_at=None is valid),
    returned as a raw Cookie header — per-request auth, no client-jar pollution."""
    from app.database import SessionLocal, User, UserSession
    sid = "zzlfd-session-1"
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        assert admin is not None, "seeded admin user missing"
        db.merge(UserSession(id=sid, user_id=admin.id, role=admin.role,
                             csrf_token="zzlfd-csrf"))
        db.commit()
    yield {"Cookie": f"session_id={sid}"}
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.id.like("zzlfd-%")).delete(
            synchronize_session=False)
        db.commit()


@pytest.fixture
def seeded_costing():
    """Minimal CalculationRecord — enough for /results/{id} to render (lenient
    Jinja undefined; trailer_type_id stays NULL, resolve_report_template(None)
    is a supported path)."""
    from app.database import CalculationRecord, SessionLocal
    quote = f"{MARK}{uuid.uuid4().hex[:5].upper()}"
    with SessionLocal() as db:
        rec = CalculationRecord(quote_number=quote, dimensions_json="{}",
                                result_json=RESULT_JSON, status="pending")
        db.add(rec)
        db.commit()
        rec_id = rec.id
    yield {"id": rec_id, "quote": quote}
    with SessionLocal() as db:
        for r in db.query(CalculationRecord).filter(
                CalculationRecord.quote_number.like(f"{MARK}%")).all():
            db.delete(r)
        db.commit()


# ── The new front door ───────────────────────────────────────────────────────

def test_root_redirects_to_mes_app_unauth(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302          # exactly 302 — a drift to 301 must fail loudly
    assert r.headers["location"] == "/mes-app/"


def test_root_redirects_to_mes_app_authed(client, admin_cookie):
    # Auth state must not matter at the root: the SPA gate (not this route) owns auth.
    r = client.get("/", headers=admin_cookie, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/mes-app/"


def test_root_chain_ends_at_login_unauth(client):
    # Intended chain: "/" → /mes-app/ → /login?next=/mes-app/ (v1.40.1 SPA gate).
    r = client.get("/")
    assert r.status_code == 200
    assert r.url.path == "/login"
    assert r.url.params.get("next") == "/mes-app/"
    assert "Trailer Costing System" in r.text  # the Jinja login page, no app chrome


# ── Regression guards — the MES-embedded legacy surface stays untouched ──────

def test_calculator_still_renders_authed(client, admin_cookie):
    r = client.get("/calculator", headers=admin_cookie)
    assert r.status_code == 200
    assert "Cost Calculator" in r.text


def test_results_still_renders_both_skins_authed(client, admin_cookie, seeded_costing):
    # Plain /results/{id} — the "Print costing PDF" / "Open full page" target.
    plain = client.get(f"/results/{seeded_costing['id']}", headers=admin_cookie)
    assert plain.status_code == 200
    assert seeded_costing["quote"] in plain.text
    # ?skin=mes — the CostingResultsView iframe target (results_mes.html wrapper).
    skinned = client.get(f"/results/{seeded_costing['id']}?skin=mes",
                         headers=admin_cookie)
    assert skinned.status_code == 200
    assert seeded_costing["quote"] in skinned.text
    assert "theme-mes.css" in skinned.text   # the wrapper actually applied


def test_mes_app_gate_unchanged(client):
    # The SPA shell's own gate is byte-identical: 303 with the next= deep-link.
    r = client.get("/mes-app/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/mes-app/"


def test_api_mes_materials_unchanged(client, admin_cookie):
    # Canary for the live ERP read surface: still 401 unauth, still JSON when authed.
    unauth = client.get("/api/mes-materials")
    assert unauth.status_code == 401
    authed = client.get("/api/mes-materials", headers=admin_cookie)
    assert authed.status_code == 200
    assert isinstance(authed.json(), list)
