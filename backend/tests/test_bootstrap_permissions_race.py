"""v1.45.2 — _bootstrap_permissions must survive concurrent workers.

Prod runs `uvicorn --workers 4` and every worker bootstraps at startup. Before
the advisory lock this was a read-then-insert race: on 8 Aug 2026 a deploy adding
two new keys had two workers pass the existence check together, one insert won
and the other died on `permissions_name_key`. The loser's whole transaction rolled
back — including the ROLE GRANTS it had queued — while the app still logged
"Application startup complete", so nothing surfaced until someone read the
journal. That is the failure these tests pin.

Both tables carry unique constraints (permissions.name and uq_role_perm), so the
grant half could race too; the lock covers both because it wraps the whole
transaction.
"""
import threading
import uuid

import pytest


@pytest.fixture()
def temp_catalogue_entry(monkeypatch):
    """Append a brand-new permission to the catalogue — a new key is the only
    thing that triggers the race (existing ones are read, not inserted)."""
    import app.database as dbmod

    name = f"test.race_{uuid.uuid4().hex[:8]}"
    entry = (name, "Concurrency probe", "admin", {"full", "sales"})
    monkeypatch.setattr(dbmod, "PERMISSION_CATALOGUE",
                        list(dbmod.PERMISSION_CATALOGUE) + [entry])
    yield name
    from app.database import Permission, RolePermission, SessionLocal
    with SessionLocal() as db:
        p = db.query(Permission).filter_by(name=name).first()
        if p:
            db.query(RolePermission).filter_by(permission_id=p.id).delete()
            db.delete(p)
        db.commit()


def _run_concurrently(fn, n: int):
    """Fire fn() from n threads as simultaneously as a barrier allows, and return
    every exception raised."""
    errors: list[BaseException] = []
    barrier = threading.Barrier(n)

    def _worker():
        try:
            barrier.wait(timeout=30)     # line them all up on the starting gun
            fn()
        except BaseException as e:       # noqa: BLE001 — the point is to collect them
            errors.append(e)

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "a bootstrap thread hung"
    return errors


def test_concurrent_bootstrap_seeds_exactly_once(temp_catalogue_entry):
    """Four workers, one new key: nobody raises, one row exists, grants intact."""
    from app.database import (Permission, RolePermission, SessionLocal,
                              _bootstrap_permissions)

    errors = _run_concurrently(_bootstrap_permissions, 4)
    assert not errors, f"bootstrap raised under concurrency: {errors[:3]}"

    with SessionLocal() as db:
        rows = db.query(Permission).filter_by(name=temp_catalogue_entry).all()
        assert len(rows) == 1, f"expected exactly one row, got {len(rows)}"
        grants = {g.role for g in
                  db.query(RolePermission).filter_by(permission_id=rows[0].id).all()}
        # The rollback of a losing worker used to take the grants with it — the
        # part that actually locked Nadie out. Assert they survived.
        assert grants == {"full", "sales"}, f"grants lost or duplicated: {grants}"


def test_repeated_bootstrap_is_idempotent(temp_catalogue_entry):
    """A second wave (the next restart) adds nothing and still raises nothing."""
    from app.database import (Permission, RolePermission, SessionLocal,
                              _bootstrap_permissions)

    assert not _run_concurrently(_bootstrap_permissions, 3)
    assert not _run_concurrently(_bootstrap_permissions, 3)

    with SessionLocal() as db:
        p = db.query(Permission).filter_by(name=temp_catalogue_entry).one()
        grants = db.query(RolePermission).filter_by(permission_id=p.id).all()
        assert len(grants) == 2, f"duplicate grant rows: {len(grants)}"


def test_bootstrap_takes_the_advisory_lock(monkeypatch):
    """The serialization is the whole fix, so assert it is actually requested —
    a silently-skipped lock would leave the race in place and every other
    assertion here would still pass."""
    import app.database as dbmod

    seen: list[str] = []
    real_session = dbmod.SessionLocal

    class _SpySession:
        def __init__(self):
            self._s = real_session()

        def execute(self, stmt, *a, **kw):
            seen.append(str(stmt))
            return self._s.execute(stmt, *a, **kw)

        def __getattr__(self, item):
            return getattr(self._s, item)

    monkeypatch.setattr(dbmod, "SessionLocal", _SpySession)
    dbmod._bootstrap_permissions()
    assert any("pg_advisory_xact_lock" in s for s in seen), \
        "the bootstrap no longer takes the advisory lock — the race is back"
