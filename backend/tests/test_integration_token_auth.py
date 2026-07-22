"""v1.43 ERP enablement — read-only integration bearer-token auth (ADR 0038).

The WO §3.2 B-suite, against app/integration_auth.py + the deps.get_current_user
chokepoint guard:

  * valid token on an allowlisted GET        → 200 (or the handler's own 404 —
    auth passed), including the two new Pack §4 contract paths /api/floor/state
    and /api/floor-events and the legacy-idiom GET /api/calculations/{id}
  * valid token on writes / admin / any non-allowlisted route → 403
  * bad token anywhere                       → 401, token never echoed back
  * no token                                 → session behaviour byte-identical
  * feature off (INTEGRATION_API_TOKENS="")  → every bearer request 401,
    session behaviour untouched

Runs against icb_test (conftest db-guard). Session rows use the raw-Cookie-header
idiom (httpx's jar won't match the dot-less 'testserver' host) with zzerp-* ids,
cleaned up after each test.

Design note locked by regression here: allowlisted handlers KEEP Depends(require_user)
and opt in via the @integration_readable endpoint marker — the first CI run proved a
wrapper dependency detaches marked routes from the house
app.dependency_overrides[require_user] idiom (dozens of suites 401'd).
"""
import pytest

TOKEN = "test-erp-token-3f9a1c77"        # test-only value; never a real credential
BAD_TOKEN = "not-a-configured-token"

ALLOWLISTED_GETS = [
    "/api/production-jobs",
    "/api/production-jobs/in-progress",
    "/api/production-jobs/kpis",
    "/api/production-jobs/unlinked",
    "/api/floor/state",
    "/api/floor-events",
    "/api/mes-materials",
    "/api/stock-counts",
    "/api/discrepancies",
    "/api/demand-lines",
    "/api/chassis-records",
    "/api/chassis-records/checklists",
]

SESSION_ONLY_SURFACES = [
    "/api/session",              # session/branch info
    "/api/plan/floor-state",     # the SPA's floor path — token uses /api/floor/state
    "/api/admin/feedback",       # admin inbox
    "/api/users",                # user admin
]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tokens_on(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "INTEGRATION_API_TOKENS", f"{TOKEN}=erp")


@pytest.fixture
def tokens_off(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "INTEGRATION_API_TOKENS", "")


@pytest.fixture
def admin_session():
    """A real UserSession row for the seeded admin (expires_at=None is valid),
    returned as the raw Cookie header value. Cleaned up by _cleanup."""
    from app.database import SessionLocal, User, UserSession
    sid = "zzerp-session-1"
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        assert admin is not None, "seeded admin user missing"
        db.merge(UserSession(id=sid, user_id=admin.id, role=admin.role,
                             csrf_token="zzerp-csrf"))
        db.commit()
    return {"Cookie": f"session_id={sid}"}


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from app.database import SessionLocal, UserSession
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.id.like("zzerp-%")).delete(
            synchronize_session=False)
        db.commit()


# ── Valid token: the allowlist answers ───────────────────────────────────────

def test_valid_token_allowlisted_gets_200(client, tokens_on):
    for path in ALLOWLISTED_GETS:
        r = client.get(path, headers=_bearer(TOKEN))
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_valid_token_floor_events_shape(client, tokens_on):
    r = client.get("/api/floor-events?since_id=0&limit=5", headers=_bearer(TOKEN))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"events", "count", "last_id"}
    assert body["count"] == len(body["events"])


def test_valid_token_calculations_detail_auth_passes(client, tokens_on):
    # Auth is the thing under test: a missing record must yield the handler's own
    # 404 (past the auth gate), never 401/403.
    r = client.get("/api/calculations/99999999", headers=_bearer(TOKEN))
    assert r.status_code == 404


# ── Valid token: everything else is 403 ──────────────────────────────────────

def test_valid_token_on_write_routes_403(client, tokens_on):
    # Valid body shapes, so the 403 provably comes from auth, not validation.
    r = client.post("/api/plan/floor-transitions", json={"type": "move_body"},
                    headers=_bearer(TOKEN))
    assert r.status_code == 403
    r = client.post("/api/plan/floor-reset", json={"confirm": True},
                    headers=_bearer(TOKEN))
    assert r.status_code == 403


def test_valid_token_on_session_only_surfaces_403(client, tokens_on):
    for path in SESSION_ONLY_SURFACES:
        r = client.get(path, headers=_bearer(TOKEN))
        assert r.status_code == 403, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_valid_token_on_ui_route_403_not_redirect(client, tokens_on):
    r = client.get("/mes-app/costings", headers=_bearer(TOKEN),
                   follow_redirects=False)
    assert r.status_code == 403


# ── Bad token: 401 everywhere, never echoed ──────────────────────────────────

def test_bad_token_401_and_never_echoed(client, tokens_on):
    for path in ["/api/mes-materials", "/api/plan/floor-state", "/api/floor/state"]:
        r = client.get(path, headers=_bearer(BAD_TOKEN))
        assert r.status_code == 401, f"{path} -> {r.status_code}"
        assert BAD_TOKEN not in r.text
    r = client.post("/api/plan/floor-transitions", json={"type": "move_body"},
                    headers=_bearer(BAD_TOKEN))
    assert r.status_code == 401
    assert BAD_TOKEN not in r.text


# ── No token: session behaviour byte-identical ───────────────────────────────

def test_no_token_api_behaviour_unchanged(client, tokens_on):
    r = client.get("/api/mes-materials")
    assert r.status_code == 401
    assert r.json()["detail"] == "Session expired — please log in again"
    assert client.get("/health").status_code == 200


def test_session_user_unaffected_feature_on_vs_off(client, admin_session, monkeypatch):
    from app.config import settings
    responses = {}
    for mode, raw in (("on", f"{TOKEN}=erp"), ("off", "")):
        monkeypatch.setattr(settings, "INTEGRATION_API_TOKENS", raw)
        for path in ("/api/mes-materials", "/api/plan/floor-state", "/api/session"):
            r = client.get(path, headers=admin_session)
            assert r.status_code == 200, f"{mode}/{path} -> {r.status_code}"
            body = r.json()
            if isinstance(body, dict):
                body.pop("server_now", None)      # floor-state's clock anchor is per-call
            responses.setdefault(path, []).append(body)
    # Identical session responses whether the token feature is on or off.
    for path, (on_body, off_body) in responses.items():
        assert on_body == off_body, f"session response drifted with feature flag: {path}"


# ── Feature off: every bearer request is rejected ────────────────────────────

def test_feature_off_all_bearer_requests_401(client, tokens_off):
    for path in ["/api/mes-materials", "/api/floor/state", "/api/session"]:
        r = client.get(path, headers=_bearer(TOKEN))
        assert r.status_code == 401, f"{path} -> {r.status_code}"
        assert TOKEN not in r.text


# ── House test-override compatibility (the first CI run's lesson) ────────────

def test_dependency_override_of_require_user_still_covers_marked_routes(client):
    """Marked GET routes MUST stay overridable via
    app.dependency_overrides[require_user] — the idiom every existing API suite
    uses. This is the regression that reshaped the design from a wrapper
    dependency to the @integration_readable endpoint marker."""
    import app.main as app_mod
    from app.database import SessionLocal, User
    from app.deps import require_user
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    try:
        for path in ("/api/chassis-records/bays/assembly", "/api/mes-materials",
                     "/api/production-jobs", "/api/floor-events"):
            r = client.get(path)
            assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:120]}"
    finally:
        app_mod.app.dependency_overrides.pop(require_user, None)


# ── Parser hygiene ───────────────────────────────────────────────────────────

def test_malformed_env_entries_never_widen_access(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "INTEGRATION_API_TOKENS",
                        " , =noname, tokenless= , spaced-token = erp ")
    r = client.get("/api/mes-materials", headers=_bearer("spaced-token"))
    assert r.status_code == 200          # whitespace-tolerant pair still parses
    for junk in ("", "noname", "tokenless"):
        r = client.get("/api/mes-materials", headers=_bearer(junk or "x"))
        assert r.status_code == 401      # malformed entries grant nothing


def test_non_bearer_authorization_scheme_ignored(client, tokens_on):
    # A Basic header is not this feature's claim: no session -> the ordinary 401.
    r = client.get("/api/mes-materials",
                   headers={"Authorization": "Basic dXNlcjpwdw=="})
    assert r.status_code == 401
    assert r.json()["detail"] == "Session expired — please log in again"
