"""v1.42 — DELETE /api/bom-sections/{id} (the Edit Section modal's delete).

Fail-loud contract: deletion is refused (409, with a used-by count in the
message) while ANY bill-of-materials row references the section by FK id or by
the legacy string column; an unused section deletes cleanly; missing id → 404.
Admin-gated via the in-handler require_admin (cookie pattern — a real
UserSession row + raw Cookie header, [[testclient-session-cookie]]).

House pattern (test_calculation_contact_api.py): live test DB, marker rows
'J142SEC*', module-local fixtures, purge on both sides.
"""
import pytest

_MARK = "J142SEC"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    import uuid
    from app.database import SessionLocal, User, UserSession
    from starlette.testclient import TestClient
    sid = str(uuid.uuid4())
    with SessionLocal() as db:
        _purge(db)
        admin = db.query(User).filter_by(username="admin").first()
        db.add(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None))
        db.commit()
    with TestClient(app_mod.app) as c:
        c.headers["Cookie"] = f"session_id={sid}"
        yield c
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()
        _purge(db)


@pytest.fixture
def staged():
    """One unused marker section + one referenced by a BOM row (FK id) + one
    referenced only via the legacy string column."""
    from app.database import BillOfMaterial, BOMSection, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{_MARK} TRAILER", is_active=True)
        unused = BOMSection(name=f"{_MARK} UNUSED", sort_order=9101)
        by_fk = BOMSection(name=f"{_MARK} BY FK", sort_order=9102)
        by_str = BOMSection(name=f"{_MARK} BY STRING", sort_order=9103)
        mat = Material(name=f"{_MARK} WIDGET", unit_of_measure="each", price_per_unit=1.0)
        db.add_all([trailer, unused, by_fk, by_str, mat])
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                              formula_expression="1", bom_section=by_fk.name,
                              bom_section_id=by_fk.id))
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                              formula_expression="1", bom_section=by_str.name,
                              bom_section_id=None))          # legacy string-only reference
        db.commit()
        ids = {"unused": unused.id, "by_fk": by_fk.id, "by_str": by_str.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def test_delete_unused_section_succeeds(api, staged):
    r = api.delete(f"/api/bom-sections/{staged['unused']}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == f"{_MARK} UNUSED"
    assert api.get("/api/bom-sections").json() == [
        s for s in api.get("/api/bom-sections").json() if s["id"] != staged["unused"]]


def test_delete_refused_while_referenced_by_fk(api, staged):
    r = api.delete(f"/api/bom-sections/{staged['by_fk']}")
    assert r.status_code == 409
    assert "used by 1 BOM line" in r.json()["detail"]


def test_delete_refused_while_referenced_by_legacy_string(api, staged):
    r = api.delete(f"/api/bom-sections/{staged['by_str']}")
    assert r.status_code == 409
    assert "used by 1 BOM line" in r.json()["detail"]


def test_delete_missing_section_404(api):
    assert api.delete("/api/bom-sections/99999999").status_code == 404


def test_delete_requires_admin_session(app_mod, staged):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:      # no session cookie at all
        r = c.delete(f"/api/bom-sections/{staged['unused']}")
        assert r.status_code in (401, 403)
