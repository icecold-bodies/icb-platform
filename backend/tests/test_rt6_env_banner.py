"""RT6 — the "TEST SERVER" banner (RT6_DISPATCH default 6; RT6_RULING_1 Q6).

  1. Off ONLY when the server is positively identified as prod: ICB_ENVIRONMENT exactly "prod" (trimmed, any case).
     Unset, "dev", "mirror", a typo: the bar "TEST SERVER — <host:port> — not prod" shows and the tab title starts
     with "[TEST] ".
  2. Every HTML page (a Jinja page, the login page, the SPA shell) — never a JSON or static response, and never a page
     loaded into an iframe (the MES SPA embeds /mes/calculator: one bar, not two). The bar ignores the pointer.
  3. /health/version says which server this is; the admin dashboard's PROD / TEST badge reads the same key.
"""
from __future__ import annotations

import uuid

import pytest

from app import env_banner as eb
from app.config import settings


@pytest.fixture(scope="module")
def client():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as c:
        yield c


@pytest.fixture()
def env(monkeypatch):
    def set_(value):
        monkeypatch.setattr(settings, "ICB_ENVIRONMENT", value, raising=False)
    return set_


def _admin():
    from app.database import SessionLocal, User, UserSession
    sid = f"rt6b-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin").first()
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None, csrf_token=f"c-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"c-{sid}"}


@pytest.mark.parametrize("value", ["", "dev", "mirror", "production", "prod-mirror", "test"])
def test_anything_but_prod_shows_the_bar_and_the_title(client, env, value):
    env(value)
    for enc in ("identity", "gzip"):                       # the bar goes in BEFORE GZip compresses the page
        r = client.get("/login", headers={"Host": "localhost:8000", "Accept-Encoding": enc})
        assert r.status_code == 200
        assert 'id="icb-test-banner"' in r.text and "TEST SERVER — localhost:8000 — not prod" in r.text
        assert "<title>[TEST] " in r.text and r.text.count('id="icb-test-banner"') == 1
        assert "pointer-events:none" in r.text
        if enc == "identity":
            assert int(r.headers["content-length"]) == len(r.content)


@pytest.mark.parametrize("value", ["prod", " PROD ", "Prod"])
def test_prod_shows_nothing(client, env, value):
    env(value)
    r = client.get("/login")
    assert r.status_code == 200 and "icb-test-banner" not in r.text and "[TEST]" not in r.text


def test_not_inside_an_iframe_and_never_on_json(client, env):
    env("dev")
    assert "icb-test-banner" not in client.get("/login", headers={"Sec-Fetch-Dest": "iframe"}).text
    v = client.get("/health/version")
    assert v.headers["content-type"].startswith("application/json") and "icb-test-banner" not in v.text


def test_the_spa_shell_and_a_signed_in_page_carry_it(client, env):
    env("")
    h = _admin()
    r = client.get("/admin/quote-templates", headers=h)
    assert r.status_code == 200 and "icb-test-banner" in r.text and "<title>[TEST] " in r.text
    r = client.get("/mes-app/", headers=h)                 # the SPA shell, when a build is present on this machine
    if r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "<body" in r.text:
        assert "icb-test-banner" in r.text and "<title>[TEST] " in r.text


def test_health_version_says_which_server_this_is(client, env):
    env("prod")
    assert client.get("/health/version").json()["environment"] == "prod"
    env("")
    assert client.get("/health/version").json()["environment"] == "unset"
    env("Mirror")
    assert client.get("/health/version").json()["environment"] == "mirror"


def test_the_dashboard_badge_reads_the_same_key_not_the_database_host(env):
    from app.database import get_db_info
    env("prod")
    label, _detail, is_prod = get_db_info()
    assert is_prod and label.startswith("PROD")       # prod's database is on 127.0.0.1: it used to read DEV
    env("")
    label, _detail, is_prod = get_db_info()
    assert not is_prod and "PROD" not in label and "unset" in label


def test_the_injection_is_one_bar_after_body_and_one_title_prefix():
    page = b"<html><head><title>X</title></head><body class=a><p>hi</p></body></html>"
    out = eb.inject(page, "h:1")
    assert out.count(b'id="icb-test-banner"') == 1 and out.index(b"icb-test-banner") > out.index(b"<body class=a>")
    assert b"<title>[TEST] X</title>" in out
    assert eb.inject(out, "h:1").count(b"<title>[TEST] ") == 1          # the title is never prefixed twice
    assert eb.inject(b"<p>fragment</p>", "h") == b"<p>fragment</p>"
