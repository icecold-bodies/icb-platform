"""WO v4.26.1 — shared substrate for the MES end-to-end *journey* tests.

These tests drive a REAL browser (Playwright / Chromium) against a REAL uvicorn
server that serves the built React SPA (`frontend/dist`) backed by the seeded
`icb_mes` database. They are deliberately kept OUT of the default ``pytest`` run
(see ``.github/workflows/ci.yml`` -> ``pytest --ignore=tests/journeys``) because
they need a browser binary plus a booted HTTP server; CI runs them in a dedicated
"Journey tests" step on both Linux and Windows.

Design notes
------------
* **Server** — a session-scoped fixture (:func:`live_server`) boots
  ``uvicorn app.main:app`` on 127.0.0.1:8000 as a subprocess with
  ``MES_DEMO_AUTOLOGIN_USER=admin`` so the SPA can mint an admin session without
  a password (see ``app/routers/pre_job_card.py`` autologin). Set the ``MES_BASE``
  env var to point at an already-running server and the boot is skipped — handy
  for local debugging against ``start`` + ``npm run dev`` proxies.
* **Browser** — raw ``playwright.sync_api`` (NOT the pytest-playwright plugin, to
  keep the dependency surface minimal): one Chromium per session, a fresh
  context + page per test for isolation.
* **Autologin gotcha** (learned the hard way in v4.26): you MUST load ``/mes-app/``
  FIRST so the React app autologins before deep-linking any sub-route, otherwise
  the auth guard bounces you to the Jinja ``/login`` page. :func:`admin_session`
  encapsulates that ordering — always start a journey through it.

Selector policy (WO v4.26.1 §5): journey tests select on ``data-testid`` only —
never CSS class names (which are styling, not contract).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

# ── Repo layout ──────────────────────────────────────────────────────────────
# This file lives at backend/tests/journeys/_common.py
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_DIST_DIR = _REPO_ROOT / "frontend" / "dist"
SCREENSHOT_ROOT = _REPO_ROOT / "docs" / "screenshots" / "journeys"

# ── Server boot config ───────────────────────────────────────────────────────
_HOST = "127.0.0.1"
_PORT = 8000
_DEFAULT_BASE = f"http://{_HOST}:{_PORT}"
_HEALTH_TIMEOUT_S = 90.0

# Headed mode for local debugging: MES_JOURNEY_HEADED=1
_HEADLESS = os.environ.get("MES_JOURNEY_HEADED", "").strip().lower() not in ("1", "true", "yes")


# ── Low-level helpers ────────────────────────────────────────────────────────
def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_health(base: str, proc: "subprocess.Popen | None" = None,
                     log_path: "Path | None" = None, timeout: float = _HEALTH_TIMEOUT_S) -> None:
    """Poll ``<base>/health`` until it returns 200, or fail with the server log."""
    url = f"{base.rstrip('/')}/health"
    deadline = time.monotonic() + timeout
    last_err: object = None
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"uvicorn exited early (code {proc.returncode}).\n{_tail(log_path)}"
            )
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (URLError, OSError) as exc:  # connection refused while booting
            last_err = exc
        time.sleep(0.4)
    raise RuntimeError(
        f"Server health check failed at {url} after {timeout:.0f}s "
        f"(last error: {last_err}).\n{_tail(log_path)}"
    )


def _tail(log_path: "Path | None", n: int = 40) -> str:
    if not log_path or not log_path.exists():
        return "(no server log captured)"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(server log unreadable)"
    return "----- server log (tail) -----\n" + "\n".join(lines[-n:])


# ── Session-scoped fixtures ──────────────────────────────────────────────────
@pytest.fixture(scope="session")
def live_server():
    """Yield a base URL for a running MES server.

    If ``MES_BASE`` is set, assume an external server is already up and just
    return it. Otherwise boot ``uvicorn app.main:app`` on 127.0.0.1:8000 as a
    subprocess (autologin user = admin) and tear it down at session end.
    """
    external = os.environ.get("MES_BASE")
    if external:
        base = external.rstrip("/")
        _wait_for_health(base)
        yield base
        return

    if not _DIST_DIR.exists():
        pytest.fail(
            f"Frontend build not found at {_DIST_DIR}.\n"
            "Run `npm run build` in frontend/ before the journey tests "
            "(CI does this in the 'Build frontend' step)."
        )
    if _port_in_use(_HOST, _PORT):
        pytest.fail(
            f"Port {_PORT} is already in use. Stop that process, or set MES_BASE "
            "to point the journey tests at the running server instead."
        )

    env = {**os.environ, "MES_DEMO_AUTOLOGIN_USER": "admin"}
    log_handle = tempfile.NamedTemporaryFile(
        prefix="mes-journey-uvicorn-", suffix=".log", delete=False
    )
    log_path = Path(log_handle.name)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", _HOST, "--port", str(_PORT)],
        cwd=str(_BACKEND_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_health(_DEFAULT_BASE, proc=proc, log_path=log_path)
        yield _DEFAULT_BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        log_handle.close()
        try:
            log_path.unlink()
        except OSError:
            pass


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance) -> "Browser":  # type: ignore[valid-type]
    browser = playwright_instance.chromium.launch(headless=_HEADLESS)
    yield browser
    browser.close()


# ── Per-test fixtures ────────────────────────────────────────────────────────
@pytest.fixture()
def browser_context(browser: "Browser", live_server: str) -> "BrowserContext":  # type: ignore[valid-type]
    context = browser.new_context(base_url=live_server, viewport={"width": 1440, "height": 900})
    yield context
    context.close()


# Local repro knob for CI-only reds. The journey suite has now produced several
# failures that appear ONLY on the slower Linux runner, and "add a wait and push
# again" is an expensive way to debug. Set MES_JOURNEY_CPU_THROTTLE=6 to make
# Chromium run ~6x slower via CDP and reproduce that class locally. Off (1x) by
# default, so CI behaviour is unchanged.
_CPU_THROTTLE = float(os.environ.get("MES_JOURNEY_CPU_THROTTLE", "1") or 1)


@pytest.fixture()
def page(browser_context: "BrowserContext") -> "Page":  # type: ignore[valid-type]
    page = browser_context.new_page()
    page.set_default_timeout(15_000)
    if _CPU_THROTTLE > 1:
        cdp = browser_context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": _CPU_THROTTLE})
    yield page


# ── Journey helpers ──────────────────────────────────────────────────────────
def wait_for_dashboard(page: "Page") -> None:
    """Block until the authenticated React shell has rendered.

    ``data-testid="top-nav"`` only mounts inside :class:`Layout`, which the auth
    guard refuses to render until a session exists — so its presence proves the
    autologin round-trip completed.
    """
    page.wait_for_selector("[data-testid='top-nav']", timeout=30_000)


def admin_session(page: "Page", base: str = _DEFAULT_BASE) -> "Page":
    """Mint an admin demo session in this browser context, then load the SPA shell.

    v1.40.1: the SPA no longer self-autologins, and the ``/mes-app/*`` shell is now
    gated server-side (unauthenticated navigation → the Jinja ``/login``). So we POST
    the demo autologin FIRST — exactly like :func:`role_session` — which sets the
    context's ``session_id`` cookie; then navigate. The shell gate sees the cookie and
    serves the app, and because the POST returns only after Set-Cookie, the session is
    ready before any in-SPA fetch fires (this also retires the old v4.34 autologin-race
    flake — no more expect_response gymnastics).

    Always call this (or :func:`role_session`) before deep-linking any ``/mes-app`` route.
    """
    base = base.rstrip("/")
    resp = page.request.post(f"{base}/api/mes/autologin", headers={"Origin": base})
    assert resp.ok, f"admin autologin failed: HTTP {resp.status}"
    page.goto("/mes-app/")
    wait_for_dashboard(page)
    return page


# ── Per-role journeys (WO v4.29 §3.6) ────────────────────────────────────────
# The journey server boots with MES_DEMO_AUTOLOGIN_USER=admin, but the autologin endpoint accepts an
# optional `username` (demo-mode only, origin-guarded) so a single server boot can mint any role per
# browser context — the prerequisite for per-role coverage (the v4.29 prevention shift).
ROLE_USERS = {"sales": "journey_sales", "production": "journey_production", "planner": "journey_planner",
              "workshop": "journey_workshop",   # WO v4.31 §3.5 — bay-model/job-card per-role coverage
              "qc_inspector": "journey_qc_inspector"}   # WO v4.36c §3.6 — Kenny QC role (0028 grants)


@pytest.fixture(scope="session")
def role_users():
    """Ensure demo users for the per-role journeys exist (idempotent; cleaned up at session end).
    The journey server runs as a subprocess against this same DB, so the autologin endpoint resolves
    these usernames. 0005/0013 grant each role its perms; this only seeds the user rows."""
    from app.database import SessionLocal, User
    created = []
    with SessionLocal() as db:
        for role, uname in ROLE_USERS.items():
            if db.query(User).filter_by(username=uname).first() is None:
                db.add(User(username=uname, password_hash="x", role=role))
                created.append(uname)
        db.commit()
    yield ROLE_USERS
    with SessionLocal() as db:
        for uname in created:
            u = db.query(User).filter_by(username=uname).first()
            if u is not None:
                db.delete(u)
        db.commit()


def role_session(page: "Page", username: str, base: str = _DEFAULT_BASE) -> "Page":
    """Mint `username`'s demo session in this browser context, then load the SPA on the shell.

    Mirrors :func:`admin_session` for an arbitrary seeded role: POST the autologin with the requested
    username FIRST (sets the context's session cookie), then load ``/mes-app/`` — the SPA's own
    autologin sees the existing valid session and keeps it (WO v4.29 §3.6).
    """
    base = base.rstrip("/")
    resp = page.request.post(f"{base}/api/mes/autologin",
                             data={"username": username}, headers={"Origin": base})
    assert resp.ok, f"autologin as {username!r} failed: HTTP {resp.status}"
    page.goto("/mes-app/")
    wait_for_dashboard(page)
    return page


def shot(page: "Page", name: str, journey: str = "admin") -> Path:
    """Save a full-page screenshot under docs/screenshots/journeys/<journey>/."""
    out_dir = SCREENSHOT_ROOT / journey
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
