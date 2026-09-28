"""v1.59 — Admin -> Costing audit (BA dispatch 3, 27 Sep). Pins the ratified defaults:

  2  PROVABLY READ-ONLY   a full run leaves every pricing table (every table but the run
                          record) byte-identical — checksummed before and after, with the
                          checksum's own sensitivity proven; and a write attempted on the
                          probe's session RAISES (the negative control, counted).
  3  NEVER ON THE REQUEST POST returns a run id at once while the run executes on a
     THREAD, ONE AT A TIME background thread; a second start is refused with "already
                          running — started by X at HH:MM"; the session advisory lock dies
                          with its connection (a dead worker never jams it); a 'running'
                          record orphaned by a dead worker is failed by the next run; the
                          hard timeout marks the run failed with the reason.
  5  ENVIRONMENT          icb_platform -> prod (accepted_differences.prod.yaml), else dev.
  9  RUN PATH             imports with openpyxl blocked (and the block is proven to bite).
  10 PERMISSION IN CODE   admin.costing_audit gates the page, every endpoint and the menu;
                          a non-admin gets 403 from the API, and the key is grantable.

House pattern (test_capture_for_user.py): live test DB, REAL session rows sent as raw
Cookie headers, marker rows, purge by id on the way out.
"""
import json
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
_MARK = "V159CA"
_mark = _MARK.lower()
API = "/api/admin/costing-audit"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    # Entering the client runs startup, which is what seeds admin.costing_audit.
    with TestClient(m.app):
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture(scope="module")
def svc(app_mod):
    from app.services import costing_audit_runs
    return costing_audit_runs


def _session_for(user_id: int, role: str) -> dict:
    from app.database import SessionLocal, UserSession
    sid = f"v159-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        db.merge(UserSession(id=sid, user_id=user_id, role=role, expires_at=None, csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}


@pytest.fixture(scope="module")
def people(app_mod):
    """admin; a 'full' user (no key); a 'full' user GRANTED admin.costing_audit per user."""
    from app.database import Permission, SessionLocal, User, UserPermission, UserSession
    out = {}
    with SessionLocal() as db:
        for who in ("plain", "granted"):
            db.add(User(username=f"{_mark}_{who}_{uuid.uuid4().hex[:6]}", password_hash="x", role="full", email=""))
        db.commit()
        for who in ("plain", "granted"):
            u = (db.query(User).filter(User.username.like(f"{_mark}_{who}_%")).order_by(User.id.desc()).first())
            out[who] = {"id": u.id, "username": u.username, "headers": _session_for(u.id, "full")}
        perm = db.query(Permission).filter_by(name="admin.costing_audit").one()
        db.add(UserPermission(user_id=out["granted"]["id"], permission_id=perm.id, effect="allow"))
        db.commit()
        a = db.query(User).filter_by(username="admin").first()
        out["admin"] = {"id": a.id, "username": a.username, "headers": _session_for(a.id, a.role)}
    yield out
    with SessionLocal() as db:
        for p in out.values():
            sid = p["headers"]["Cookie"].split("session_id=")[1]
            db.query(UserSession).filter_by(id=sid).delete()
        db.execute(text("DELETE FROM icb_costings.user_permissions WHERE user_id IN "
                        "(SELECT id FROM icb_costings.users WHERE username LIKE :m)"), {"m": f"{_mark}_%"})
        db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE :m"), {"m": f"{_mark}_%"})
        db.commit()


@pytest.fixture
def run_ids():
    """Every run record a test creates is listed here and deleted BY ID afterwards."""
    ids: list[int] = []
    yield ids
    # The ENGINE, not SessionLocal: this teardown runs before `loaded`'s, while SessionLocal
    # is still bound to the connection `loaded` rolls back — a delete there would be undone.
    from app.database import engine
    if ids:
        with engine.begin() as c:
            c.execute(text("DELETE FROM icb_costings.costing_audit_runs WHERE id = ANY(:ids)"), {"ids": ids})


def _admin(people):
    return SimpleNamespace(id=people["admin"]["id"], username=people["admin"]["username"])


def _row(run_id):
    from app.database import CostingAuditRun, SessionLocal
    with SessionLocal() as db:
        r = db.get(CostingAuditRun, run_id)
        db.expunge(r)
        return r


def _insert_run(ids, **kw):
    from app.database import CostingAuditRun, SessionLocal
    fields = dict(started_at=datetime.now(timezone.utc), started_by=f"{_mark}_someone", pack="smoke",
                  environment="dev", db_name="icb_test", accepted_list="accepted_differences.yaml",
                  tolerance_pct=1.0, status="running", progress_done=0, progress_total=18)
    fields.update(kw)
    with SessionLocal() as db:
        r = CostingAuditRun(**fields)
        db.add(r)
        db.commit()
        ids.append(r.id)
        return r.id


def _lock_is_free(svc) -> bool:
    got = svc._try_lock()
    if got is None:
        return False
    svc._release(got)
    return True


# ── a small synthetic report (the history / downloads / change-summary tests) ──

def _synthetic_report(mes_total: float) -> dict:
    from tools.costing_audit.compare import build_report
    from tools.costing_audit.mes_probe import MesLine, MesResult
    sections = {"FLOOR": 1000.0, "ROOF": 500.0}
    g = {"scenario": {"id": "t~as_sheet", "sheet": "TEST BODY", "trailer_id": 999, "variant": "as_sheet",
                      "length": 5.0, "width": 2.0, "height": 2.0, "door": "drd", "foam": "32D",
                      "panels": {}, "flags": {}, "gate_mode": "as_sheet", "section_map": {}},
         "grand_total": 1500.0, "findings": [],
         "sections": {k: {"total": v, "raw_total": v, "status": "OK", "reason": None, "gates": {},
                          "lines": [{"desc": "SKIN", "qty": 1.0, "price": v, "total": v, "stale": False}],
                          "multiplier": 1.0} for k, v in sections.items()}}
    mes = {"FLOOR": mes_total, "ROOF": 500.0}
    m = MesResult(trailer_id=999, trailer_name="TEST", sections=mes, grand_total=sum(mes.values()),
                  lines=[MesLine(section=k, desc="SKIN", qty=1.0, price=v, total=v) for k, v in mes.items()],
                  payload={})
    rep = build_report(pack_name="smoke", tolerance_pct=1.0, manifest={"generated_at": "2026-09-25T14:09:05+00:00"},
                       mes_source="test", goldens={"t~as_sheet": g}, results={"t~as_sheet": m},
                       scenario_ids=["t~as_sheet"], accepted=[], warnings=[], today=date(2026, 9, 27))
    return rep.to_dict()


def _finished(svc, ids, mes_total: float, *, started_at, environment="dev", status=None, pack="smoke"):
    d = _synthetic_report(mes_total)
    return _insert_run(ids, started_at=started_at, finished_at=started_at + timedelta(seconds=5), pack=pack,
                       environment=environment, status=status or ("flagged" if d["exit_code"] else "passed"),
                       report_json_gz=svc.encode_report(d), **svc.counts_of(d["counts"]))


# ── 5: environment ────────────────────────────────────────────────────────────

def test_environment_is_decided_by_the_database_name(svc):
    assert svc.environment_for("icb_platform") == "prod"
    for name in ("icb", "icb_test", "icb_platform_test", "ICB_PLATFORM", "icb_mes", "", None):
        assert svc.environment_for(name) == "dev", name
    prod, dev = svc.accepted_file_for("prod"), svc.accepted_file_for("dev")
    assert prod.name == "accepted_differences.prod.yaml" and prod.is_file()
    assert dev.name == "accepted_differences.yaml" and dev.is_file()
    assert svc.environment_for(svc.current_db_name()) == "dev"          # pytest only ever runs on *_test
    assert "Development" in svc.environment_label("dev", "icb") and "Production" in svc.environment_label("prod", "icb_platform")


def test_run_limits_and_packs_are_pinned(svc):
    assert svc.TIMEOUT_S == 300
    assert svc.PACK_CHOICES == ("smoke", "chillers", "freezers", "icecream", "explosive", "all")
    assert "smoke" not in svc.ALL_PACKS and set(svc.ALL_PACKS) == set(svc.PACKS) - {"smoke"}
    with pytest.raises(svc.UnknownPack):
        svc.start_run("everything", SimpleNamespace(id=None, username="x"))


# ── 9: no openpyxl on the run path ────────────────────────────────────────────

_BLOCK = "import sys\nsys.modules['openpyxl'] = None\n"


def _py(code: str):
    return subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND), capture_output=True, text=True, timeout=120)


def test_run_path_imports_with_openpyxl_blocked():
    ok = _py(_BLOCK + (
        "import app.services.costing_audit_runs as s\n"
        "s._tools()\n"
        "import app.routers.costing_audit, app.routers.calculator, app.formula_engine, app.services.insulation_foam\n"
        "bad = [m for m in sys.modules if m.startswith('tools.costing_audit.') and m.rsplit('.', 1)[1] in "
        "('excel_oracle', 'sheet_map', 'soffice')]\n"
        "print('RUN-PATH-OK', bad)\n"))
    assert ok.returncode == 0, ok.stderr[-2000:]
    assert "RUN-PATH-OK []" in ok.stdout
    # negative control: the same block DOES stop the oracle side (so the pass above means something)
    bad = _py(_BLOCK + "import tools.costing_audit.excel_oracle\n")
    assert bad.returncode != 0 and "openpyxl" in bad.stderr


# ── 2: read-only ──────────────────────────────────────────────────────────────

_WRITES = [
    ("insert", "INSERT INTO icb_costings.admin_settings (key, value) VALUES ('v159_probe_negative', 'x')"),
    ("update bom", "UPDATE icb_costings.bill_of_materials SET id = id WHERE false"),
    ("update materials", "UPDATE icb_costings.materials SET id = id WHERE false"),
    ("update trailer_types", "UPDATE icb_costings.trailer_types SET id = id WHERE false"),
    ("delete globals", "DELETE FROM icb_costings.global_variables WHERE false"),
    ("delete formulas", "DELETE FROM icb_costings.formulas WHERE false"),
    ("ddl", "CREATE TABLE icb_costings.v159_probe_negative (i int)"),
]


def test_the_probe_session_refuses_every_write(svc):
    """NEGATIVE CONTROL — every write on the probe's own session raises, including after
    a COMMIT opens a fresh transaction (the connection itself defaults to read-only)."""
    assert svc.probe_session_factory is svc._open_probe_session       # what a real run uses
    raised = attempted = 0
    with svc._open_probe_session() as s:
        assert s.execute(text("SHOW transaction_read_only")).scalar() == "on"
        assert s.execute(text("SHOW default_transaction_read_only")).scalar() == "on"
        assert s.execute(text("SELECT count(*) FROM icb_costings.bill_of_materials")).scalar() >= 0   # reads work
        for phase in ("first transaction", "after commit"):
            if phase == "after commit":
                s.commit()
            for label, sql in _WRITES:
                attempted += 1
                with pytest.raises(DBAPIError, match="read-only transaction"):
                    s.execute(text(sql))
                raised += 1
                s.rollback()
    assert (raised, attempted) == (2 * len(_WRITES), 2 * len(_WRITES))
    print(f"\n[negative control] {raised}/{attempted} writes on the probe session raised")


def _checksums(conn) -> dict:
    """count + md5 over every row of every base table in icb_costings and icb_mes,
    except the run record itself."""
    tables = conn.execute(text(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('icb_costings', 'icb_mes') AND table_type = 'BASE TABLE' "
        "AND table_name <> 'costing_audit_runs' ORDER BY 1, 2")).all()
    return {f"{s}.{t}": tuple(conn.execute(text(
        f'SELECT count(*), md5(coalesce(string_agg(md5(x::text), \'\' ORDER BY md5(x::text)), \'\')) '
        f'FROM "{s}"."{t}" x')).one()) for s, t in tables}


@pytest.fixture
def loaded(svc, monkeypatch):
    """The committed MES snapshot loaded onto ONE connection inside a transaction that is
    rolled back at the end — icb_test is left exactly as found. The run's pricing reads
    (the probe session and the calculator's lookup caches) go through that connection;
    the run record goes through its own, as in production."""
    from app import cache
    from app import database as _db
    from tools.costing_audit.mes_snapshot import load_snapshot, snapshot_path
    conn = _db.engine.connect()
    outer = conn.begin()
    load_snapshot(snapshot_path("all"), conn=conn, log=lambda *_: None)
    real_sessionlocal = _db.SessionLocal
    monkeypatch.setattr(_db, "SessionLocal",
                        sessionmaker(bind=conn, join_transaction_mode="create_savepoint", autoflush=False))
    monkeypatch.setattr(svc, "record_session", real_sessionlocal)
    writes_refused = []

    @contextmanager
    def probe_on_conn():
        s = Session(bind=conn, join_transaction_mode="create_savepoint", autoflush=False)
        try:
            s.execute(text("SET TRANSACTION READ ONLY"))
            # the test's probe session is exactly as strict as the real one
            sp = s.begin_nested()
            try:
                s.execute(text("UPDATE icb_costings.bill_of_materials SET id = id WHERE false"))
            except DBAPIError as exc:
                writes_refused.append("read-only transaction" in str(exc))
            sp.rollback()
            yield s
        finally:
            s.rollback()
            s.close()

    monkeypatch.setattr(svc, "probe_session_factory", probe_on_conn)
    cache.invalidate_all()
    yield SimpleNamespace(conn=conn, writes_refused=writes_refused)
    cache.invalidate_all()
    outer.rollback()
    conn.close()


def test_a_full_run_changes_no_pricing_data(svc, loaded, people, run_ids):
    conn = loaded.conn
    before = _checksums(conn)
    assert len(before) > 50
    # the checksum sees a one-cell change (so "identical" below means something)
    sp = conn.begin_nested()
    conn.execute(text("UPDATE icb_costings.global_variables SET value = value + 1 "
                      "WHERE id = (SELECT min(id) FROM icb_costings.global_variables)"))
    assert _checksums(conn) != before
    sp.rollback()
    assert _checksums(conn) == before

    t0 = time.monotonic()
    rid = svc.start_run("all", _admin(people), submit=lambda fn, *a: fn(*a))
    run_ids.append(rid)
    took = time.monotonic() - t0
    after = _checksums(conn)
    changed = [k for k in before if before[k] != after.get(k)]
    assert changed == [] and set(after) == set(before)
    assert loaded.writes_refused == [True]

    r = _row(rid)
    assert r.status in ("passed", "flagged"), r.error
    assert r.progress_done == r.progress_total == 240
    assert r.count_pass > 0 and r.finished_at is not None
    d = svc.decode_report(r.report_json_gz)
    assert d["pack"] == "all" and set(d["golden_manifest"]["packs"]) == set(svc.ALL_PACKS)
    assert any("accepted list: accepted_differences.yaml" in w for w in d["warnings"])
    raw = len(json.dumps(d, default=str, separators=(",", ":")).encode("utf-8"))
    print(f"\n[read-only proof] {len(before)} tables identical after a full 'all' run "
          f"({r.progress_total} scenarios, {took:.1f} s); report {raw / 1e6:.2f} MB raw, "
          f"{len(r.report_json_gz) / 1e3:.0f} kB stored")


def test_the_page_run_matches_the_ci_gate_on_smoke(svc, loaded, people, run_ids):
    """Same code as the CLI: on the committed snapshot the smoke pack has no unaccepted
    difference — exactly what the Costing audit CI gate asserts with `audit run`."""
    rid = svc.start_run("smoke", _admin(people), submit=lambda fn, *a: fn(*a))
    run_ids.append(rid)
    r = _row(rid)
    assert r.status == "passed", (r.error, r.count_flag)
    assert r.count_flag == 0 and r.count_expired == 0 and r.count_pass > 0


# ── 3: background, one at a time, lock, stale, timeout ────────────────────────

def test_a_second_start_is_refused_while_one_runs(svc, people, run_ids):
    holder = svc._try_lock()
    assert holder is not None
    try:
        started = datetime.now(timezone.utc) - timedelta(minutes=1)
        _insert_run(run_ids, started_by=f"{_mark}_holder", started_at=started)
        from app.database import CostingAuditRun, SessionLocal
        with SessionLocal() as db:
            n0 = db.query(CostingAuditRun).count()
        with pytest.raises(svc.AlreadyRunning) as e:
            svc.start_run("smoke", _admin(people), submit=lambda *a: pytest.fail("must not start"))
        assert f"An audit is already running — started by {_mark}_holder at {started.astimezone():%H:%M}" in str(e.value)
        with SessionLocal() as db:
            assert db.query(CostingAuditRun).count() == n0        # refused, not queued
    finally:
        svc._release(holder)
    assert _lock_is_free(svc)


def test_the_lock_dies_with_its_connection(svc):
    """A worker that dies takes its connection with it; Postgres drops the session lock."""
    from app.database import engine
    holder = svc._try_lock()
    assert holder is not None and svc._try_lock() is None
    pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
    with engine.connect() as c:
        assert c.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid}).scalar() is True
    for _ in range(50):
        got = svc._try_lock()
        if got is not None:
            svc._release(got)
            break
        time.sleep(0.1)
    else:
        pytest.fail("the lock outlived its connection")
    try:
        holder.close()
    except Exception:
        pass


def test_a_dead_workers_running_record_is_failed_by_the_next_run(svc, people, run_ids):
    orphan = _insert_run(run_ids, started_at=datetime.now(timezone.utc) - timedelta(minutes=20))
    rid = svc.start_run("smoke", _admin(people), submit=lambda fn, run_id, pack, lock: svc._release(lock))
    run_ids.append(rid)
    o = _row(orphan)
    assert o.status == "failed" and o.error.startswith("interrupted") and o.finished_at is not None
    assert _row(rid).status == "running"
    # and a record far past the timeout already READS as failed, before any sweep
    s = svc.summary(_row(rid), now=datetime.now(timezone.utc) + timedelta(seconds=svc.TIMEOUT_S + svc.STALE_GRACE_S + 1))
    assert s["status"] == "failed" and "no longer running" in s["error"]


def test_the_timeout_fails_the_run_with_the_reason(svc, people, run_ids):
    rid = svc.start_run("smoke", _admin(people),
                        submit=lambda fn, run_id, pack, lock: fn(run_id, pack, lock, timeout_s=0))
    run_ids.append(rid)
    r = _row(rid)
    assert r.status == "failed" and r.finished_at is not None
    assert r.error == "timed out after 0 seconds — the run was stopped"
    assert _lock_is_free(svc)


def test_a_run_audits_the_lookups_as_they_are_now(svc, people, run_ids, monkeypatch):
    """The calculator caches sections / formulas / globals per worker for 30 s; a run
    drops them first, so a fix made on another worker a second ago is what gets audited."""
    from app import cache
    for k in ("sections", "formulas", "global_vars"):
        cache.get(k, lambda: "STALE", ttl=3600)
    calls = []
    real = svc.fresh_lookups
    monkeypatch.setattr(svc, "fresh_lookups", lambda: (calls.append(1), real()))
    rid = svc.start_run("smoke", _admin(people),
                        submit=lambda fn, run_id, pack, lock: fn(run_id, pack, lock, timeout_s=0))
    run_ids.append(rid)
    assert calls == [1]
    for k in ("sections", "formulas", "global_vars"):
        assert cache.get(k, lambda: "FRESH", ttl=1) == "FRESH", k
    cache.invalidate_all()


def test_post_returns_at_once_and_the_run_is_a_background_thread(svc, client, people, run_ids, monkeypatch):
    gate, entered, seen = threading.Event(), threading.Event(), {}

    @contextmanager
    def blocking_probe():
        seen["thread"] = threading.current_thread().name
        entered.set()
        if not gate.wait(30):
            raise RuntimeError("the test never opened the gate")
        raise RuntimeError("stopped by the test")
        yield  # pragma: no cover

    monkeypatch.setattr(svc, "probe_session_factory", blocking_probe)
    t0 = time.monotonic()
    r = client.post(f"{API}/runs", json={"pack": "smoke"}, headers=people["admin"]["headers"])
    took = time.monotonic() - t0
    assert r.status_code == 202, r.text
    rid = r.json()["id"]
    run_ids.append(rid)
    try:
        assert entered.wait(15), "the run never started"
        assert seen["thread"].startswith("costing-audit-run-")
        assert took < 5
        g = client.get(f"{API}/runs/{rid}", headers=people["admin"]["headers"])
        assert g.status_code == 200 and g.json()["status"] == "running"
        assert g.headers["cache-control"].startswith("no-store")
        busy = client.post(f"{API}/runs", json={"pack": "chillers"}, headers=people["granted"]["headers"])
        assert busy.status_code == 409
        assert busy.json()["detail"].startswith(f"An audit is already running — started by {people['admin']['username']} at ")
    finally:
        gate.set()
    for _ in range(100):
        if _row(rid).status != "running":
            break
        time.sleep(0.1)
    r = _row(rid)
    assert r.status == "failed" and "stopped by the test" in r.error
    for _ in range(50):
        if _lock_is_free(svc):
            break
        time.sleep(0.1)
    else:
        pytest.fail("the lock was not released after the run ended")


# ── 10: permission, enforced in code ──────────────────────────────────────────

def test_every_route_is_gated_on_the_permission(svc, client, people, run_ids):
    rid = _finished(svc, run_ids, 1000.0, started_at=datetime.now(timezone.utc))
    gets = ["/admin/costing-audit", f"{API}/overview", f"{API}/runs", f"{API}/runs/{rid}",
            f"{API}/runs/{rid}/changes", f"{API}/runs/{rid}/report?format=html", f"{API}/runs/{rid}/report?format=csv"]
    plain = people["plain"]["headers"]
    for url in gets:
        r = client.get(url, headers=plain, follow_redirects=False)
        assert r.status_code == 403, (url, r.status_code)
        if url.startswith(API):
            assert r.json()["detail"] == "Permission denied: admin.costing_audit", url
    r = client.post(f"{API}/runs", json={"pack": "smoke"}, headers=plain)
    assert r.status_code == 403 and r.json()["detail"] == "Permission denied: admin.costing_audit"
    # anonymous: 401 from the API, the page sends you to log in
    for url in gets[1:]:
        assert client.get(url, follow_redirects=False).status_code == 401, url
    page = client.get("/admin/costing-audit", follow_redirects=False)
    assert page.status_code in (302, 303, 307) and page.headers["location"].startswith("/login")
    # admin, and a non-admin granted the key per user: in
    for who in ("admin", "granted"):
        h = people[who]["headers"]
        for url in gets:
            r = client.get(url, headers=h, follow_redirects=False)
            assert r.status_code == 200, (who, url, r.status_code)


def test_the_menu_entry_follows_the_permission(client, people):
    for who, shown in (("admin", True), ("granted", True), ("plain", False)):
        html = client.get("/calculator", headers=people[who]["headers"]).text
        assert ('data-testid="nav-costing-audit"' in html) is shown, who


# ── history, report, downloads, change summary ────────────────────────────────

def test_history_report_and_downloads(svc, client, people, run_ids):
    h = people["admin"]["headers"]
    now = datetime.now(timezone.utc)
    older = _finished(svc, run_ids, 1100.0, started_at=now - timedelta(minutes=2))
    newer = _finished(svc, run_ids, 1000.0, started_at=now - timedelta(minutes=1))
    running = _insert_run(run_ids, started_at=now - timedelta(minutes=3), status="failed", error="x")

    ids = [r["id"] for r in client.get(f"{API}/runs", headers=h).json()["runs"]]
    assert ids.index(newer) < ids.index(older) < ids.index(running)          # newest first
    listed = next(r for r in client.get(f"{API}/runs", headers=h).json()["runs"] if r["id"] == newer)
    assert listed["status"] == "passed" and listed["counts"]["pass"] == 2 and listed["report_bytes"] > 0

    page = client.get(f"{API}/runs/{newer}/report?format=html", headers=h)
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "window.__AUDIT__" in page.text and "content-disposition" not in page.headers
    assert page.headers["cache-control"].startswith("no-store")
    dl = client.get(f"{API}/runs/{newer}/report?format=html&download=1", headers=h)
    assert dl.headers["content-disposition"].startswith("attachment;") and dl.headers["content-disposition"].endswith('.html"')
    csv = client.get(f"{API}/runs/{newer}/report?format=csv", headers=h)
    assert csv.headers["content-type"].startswith("text/csv") and csv.headers["content-disposition"].endswith('.csv"')
    assert csv.text.splitlines()[0].startswith("scenario_id,sheet,trailer_id")
    assert csv.headers["cache-control"].startswith("no-store")
    assert client.get(f"{API}/runs/{newer}/report?format=xlsx", headers=h).status_code == 400
    assert client.get(f"{API}/runs/{running}/report", headers=h).status_code == 409
    assert client.get(f"{API}/runs/987654321", headers=h).status_code == 404


def test_changed_since_the_previous_run_of_the_same_pack_and_environment(svc, client, people, run_ids):
    h = people["admin"]["headers"]
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    first = _finished(svc, run_ids, 1100.0, started_at=base, pack="chillers")           # FLOOR FLAG
    _finished(svc, run_ids, 1000.0, started_at=base + timedelta(minutes=1), pack="chillers", environment="prod")
    _insert_run(run_ids, started_at=base + timedelta(minutes=2), pack="chillers", status="failed", error="x")
    _finished(svc, run_ids, 1000.0, started_at=base + timedelta(minutes=3), pack="freezers")
    fixed = _finished(svc, run_ids, 1000.0, started_at=base + timedelta(minutes=4), pack="chillers")  # FLOOR PASS
    again = _finished(svc, run_ids, 1000.0, started_at=base + timedelta(minutes=5), pack="chillers")

    c0 = client.get(f"{API}/runs/{first}/changes", headers=h).json()
    assert c0["previous"] is None and c0["changes"] == []
    c1 = client.get(f"{API}/runs/{fixed}/changes", headers=h).json()
    assert c1["previous"]["id"] == first                    # prod, failed and other-pack runs skipped
    assert [(c["kind"], c["section"], c["old_status"], c["new_status"]) for c in c1["changes"]] == \
        [("status", "FLOOR", "FLAG", "PASS")]
    c2 = client.get(f"{API}/runs/{again}/changes", headers=h).json()
    assert c2["previous"]["id"] == fixed and c2["changes"] == []          # the page says "No change since …"


def test_counts_map_every_unaccepted_difference_to_flag(svc):
    assert svc.counts_of({"PASS": 3, "FLAG": 1, "PRESENCE": 2, "UNMAPPED": 1, "NO_GOLDEN": 1, "ACCEPTED": 4,
                          "EXPIRED": 5, "UNVERIFIABLE": 6, "SKIP": 9}) == \
        {"count_pass": 3, "count_flag": 5, "count_accepted": 4, "count_expired": 5, "count_unverifiable": 6}
