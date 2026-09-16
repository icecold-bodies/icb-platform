"""v1.56 — the costing carries the parameters it was priced at (length, width, height).

Michael (16 Sep): "Please also add to where the users views the captured costing the
parameters of the body i.e. Len, width and height. currently there is only the body
options."

The costing page reads its row from GET /api/calculations, which until now carried the
length alone (v1.44 R6, for the "(5.6 m)" suffix). These tests pin the two halves that
matter: the three parameters come back AS ENTERED, and a costing with no geometry — every
repair — reports None rather than a zero that would read as a real measurement.

House pattern: live test DB, marker rows 'V156BP*', module-local fixtures, purge on both
sides.
"""
import json

import pytest

_MARK = "V156BP"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    """Admin client — see [[testclient-session-cookie]]: the calculator endpoints resolve
    the user INSIDE the handler, so a real UserSession row sent as a raw Cookie header is
    what authenticates, not a dependency override."""
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


def _costing(dimensions, *, is_repair=False) -> int:
    """A costing whose geometry is `dimensions` (a dict, or a raw JSON string)."""
    from app.database import SessionLocal, CalculationRecord, Customer
    with SessionLocal() as db:
        cust = db.query(Customer).filter(Customer.name.like(f"{_MARK}%")).first()
        if cust is None:
            cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
            db.add(cust)
            db.flush()
        rec = CalculationRecord(
            customer_id=cust.id,
            dimensions_json=dimensions if isinstance(dimensions, str) else json.dumps(dimensions),
            result_json='{"items": []}', status="pending", is_repair=is_repair,
        )
        db.add(rec)
        db.commit()
        return rec.id


def _row(api, rec_id: int) -> dict:
    res = api.get("/api/calculations?limit=200")
    assert res.status_code == 200, res.text
    row = next((r for r in res.json() if r["id"] == rec_id), None)
    assert row is not None, f"costing {rec_id} is not in the list"
    return row


def test_the_costing_reports_the_parameters_it_was_priced_at(api):
    rec_id = _costing({"length": 6.8, "width": 2.5, "height": 2.7,
                       "floor_thickness": 60, "num_axles": 3})
    row = _row(api, rec_id)
    assert (row["body_length"], row["body_width"], row["body_height"]) == (6.8, 2.5, 2.7)


def test_a_costing_with_no_geometry_reports_no_parameters(api):
    """Every repair stores `{}` — the page must show nothing there, not 0 × 0 × 0."""
    rec_id = _costing({}, is_repair=True)
    row = _row(api, rec_id)
    assert (row["body_length"], row["body_width"], row["body_height"]) == (None, None, None)


@pytest.mark.parametrize("dims, why", [
    ({"length": 6.8}, "a legacy row that only ever stored the length"),
    ({"length": 6.8, "width": 0, "height": None}, "a zero or a null is not a measurement"),
    ({"length": "6.8", "width": "2.5", "height": "2.7"}, "numbers stored as strings"),
    ("not json at all", "a corrupted dimensions column must not take the list down"),
])
def test_odd_rows_degrade_to_no_parameter_rather_than_a_wrong_one(api, dims, why):
    row = _row(api, _costing(dims))
    if dims == {"length": "6.8", "width": "2.5", "height": "2.7"}:
        assert (row["body_length"], row["body_width"], row["body_height"]) == (6.8, 2.5, 2.7), why
    else:
        assert row["body_width"] is None and row["body_height"] is None, why


def test_the_length_still_reads_exactly_as_it_did_before(api):
    """v1.44 R6 behaviour is unchanged — the dashboard's "(6.8 m)" suffix rides on it."""
    assert _row(api, _costing({"length": 6.8, "width": 2.5, "height": 2.7}))["body_length"] == 6.8
    assert _row(api, _costing({"length": 0, "width": 2.5}))["body_length"] is None
