"""v1.50 P3 — repair from body categories + reusable repair templates.

What these units pin:

CATEGORY PULL (Feature 1)
  * the category list is the body's real sections, in section order — body-option
    master rows and archived (Unassigned-tray) sections never appear
  * preview quantities are the SAME numbers a body costing of the same body +
    dimensions computes for that category (same _build_bom_items + calculate_bom,
    section multiplier and waste included) — the "shared, not reimplemented" proof
  * an OPTIONAL section the user explicitly picked comes back INCLUDED — picking
    the category IS the opt-in; the preview's tick boxes do the excluding
  * validation refuses, with a plain message: unknown body (404), missing/zero
    dimensions (422), a category the body does not have (422)
  * pulled-style lines (origin + material_id provenance on a free_hand line)
    survive calculate → approve → reopen intact — chips and template-saving both
    read them back

TEMPLATES (Feature 2)
  * create/edit/retire is gated by costings.repair_templates_manage: role
    'user' is refused (403), role 'full' passes (the seeded grant), admin passes
  * the gate string IS in PERMISSION_CATALOGUE (v1.48 lesson: a gate string that
    is not a catalogue key is invisible — admin short-circuits user_can)
  * NO PRICES ARE STORED: /expand prices a stock line at TODAY's material-list
    price (changed price → changed expand), offers today's price on a pulled
    free-hand line, and leaves a plain free-hand line to be priced at use
  * a stock line whose material has left the list comes back `unavailable`, not
    priced at a stale value
  * retire is SOFT: gone from the default list, visible with include_retired
    (manage-gated), /expand refuses with 409, restore brings it back

Sessions are real UserSession rows via raw Cookie headers (banked pattern).
"""
import uuid

import pytest

TT_NAME = "V150 P3 BODY"
SEC_SIDES = "V150 SIDES"
SEC_FLOOR = "V150 FLOOR"
SEC_OPT = "V150 OPTIONAL BITS"
SEC_ARCHIVED = "V150 PARKED"

DIMS = {"length": 7.5, "width": 2.3, "height": 2.3}


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:   # triggers startup → seeds permissions
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _make_session(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"v150p3-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role,
                             expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    return _make_session("admin")


@pytest.fixture(scope="module")
def seeded(app_mod):
    """One body with a doubled SIDES section, a FLOOR section, an OPTIONAL
    section and an ARCHIVED section; catalogue materials; a customer; and two
    marked users (roles full + user) for the permission gate. Marked names
    throughout — bom_sections are GLOBAL (identity by name)."""
    from datetime import datetime, timezone
    from app.database import (SessionLocal, TrailerType, BillOfMaterial,
                              BOMSection, Material, Customer, User)
    ids = {}
    with SessionLocal() as db:
        m_side = Material(name=f"{TT_NAME} SIDE PANEL", unit_of_measure="m2",
                          price_per_unit=100.0, is_active=True)
        m_rivet = Material(name=f"{TT_NAME} RIVETS", unit_of_measure="each",
                           price_per_unit=2.0, is_active=True)
        m_floor = Material(name=f"{TT_NAME} FLOOR PLY", unit_of_measure="m2",
                           price_per_unit=80.0, is_active=True)
        m_opt = Material(name=f"{TT_NAME} EXTRA TRAY", unit_of_measure="each",
                         price_per_unit=60.0, is_active=True)
        m_parked = Material(name=f"{TT_NAME} PARKED THING", unit_of_measure="each",
                            price_per_unit=5.0, is_active=True)
        m_glue = Material(name=f"{TT_NAME} GLUE", unit_of_measure="each",
                          price_per_unit=250.0, is_active=True)
        db.add_all([m_side, m_rivet, m_floor, m_opt, m_parked, m_glue])
        db.flush()

        s_sides = BOMSection(name=SEC_SIDES, sort_order=20, multiplier=2.0,
                             is_optional=False)
        s_floor = BOMSection(name=SEC_FLOOR, sort_order=21, is_optional=False)
        s_opt = BOMSection(name=SEC_OPT, sort_order=22, is_optional=True)
        s_parked = BOMSection(name=SEC_ARCHIVED, sort_order=23,
                              archived_at=datetime.now(timezone.utc))
        db.add_all([s_sides, s_floor, s_opt, s_parked])
        db.flush()

        tt = TrailerType(name=TT_NAME, is_active=True, default_length=7.5,
                         default_width=2.3, default_height=2.3)
        db.add(tt)
        db.flush()
        rows = [
            # length * height at 7.5 x 2.3 = 17.25; SIDES multiplier 2 → qty 34.5
            BillOfMaterial(trailer_type_id=tt.id, material_id=m_side.id,
                           formula_expression="length * height", waste_percentage=0,
                           bom_section=SEC_SIDES, bom_section_id=s_sides.id, sort_order=1),
            # waste rides into the quantity: 100 * 2 * 1.10 = 220
            BillOfMaterial(trailer_type_id=tt.id, material_id=m_rivet.id,
                           formula_expression="100", waste_percentage=10,
                           bom_section=SEC_SIDES, bom_section_id=s_sides.id, sort_order=2),
            # length * width at 7.5 x 2.3 = 17.25
            BillOfMaterial(trailer_type_id=tt.id, material_id=m_floor.id,
                           formula_expression="length * width", waste_percentage=0,
                           bom_section=SEC_FLOOR, bom_section_id=s_floor.id, sort_order=3),
            BillOfMaterial(trailer_type_id=tt.id, material_id=m_opt.id,
                           formula_expression="2", waste_percentage=0,
                           bom_section=SEC_OPT, bom_section_id=s_opt.id, sort_order=4),
            BillOfMaterial(trailer_type_id=tt.id, material_id=m_parked.id,
                           formula_expression="1", waste_percentage=0,
                           bom_section=SEC_ARCHIVED, bom_section_id=s_parked.id, sort_order=5),
        ]
        cust = Customer(name=f"{TT_NAME} CUSTOMER", is_active=True)
        u_full = User(username="v150p3-full", password_hash="x", role="full",
                      email="v150p3-full@test.local")
        u_user = User(username="v150p3-user", password_hash="x", role="user",
                      email="v150p3-user@test.local")
        db.add_all(rows + [cust, u_full, u_user])
        db.commit()
        # The section snapshot is cached with a ~30 s TTL. Another module may
        # have warmed it seconds ago, in which case these fresh sections would
        # be invisible (order + multiplier fall back to defaults) and the exact
        # 34.5 / ordering assertions below turn flaky with suite order.
        from app.services import invalidate_sections
        invalidate_sections()
        ids = {"tt": tt.id, "customer": cust.id,
               "mats": [m_side.id, m_rivet.id, m_floor.id, m_opt.id,
                        m_parked.id, m_glue.id],
               "m_side": m_side.id, "m_glue": m_glue.id, "m_floor": m_floor.id,
               "secs": [s_sides.id, s_floor.id, s_opt.id, s_parked.id],
               "users": [u_full.id, u_user.id]}
    yield ids
    with SessionLocal() as db:
        from sqlalchemy import text as _text
        from app.database import (CalculationRecord, RepairTemplate, UserSession)
        _owned = ("SELECT id FROM icb_costings.calculations "
                  "WHERE trailer_type_id = :tt OR customer_id = :cu")
        for _tbl, _col in (("icb_mes.prejob_cards", "calculation_id"),
                           ("icb_mes.production_jobs", "calculation_record_id")):
            db.execute(_text(f"DELETE FROM {_tbl} WHERE {_col} IN ({_owned})"),
                       {"tt": ids["tt"], "cu": ids["customer"]})
        db.query(CalculationRecord).filter(
            (CalculationRecord.trailer_type_id == ids["tt"])
            | (CalculationRecord.customer_id == ids["customer"])).delete(
                synchronize_session=False)
        db.query(RepairTemplate).filter(
            RepairTemplate.name.like("V150 P3%")).delete(synchronize_session=False)
        db.query(BillOfMaterial).filter(
            BillOfMaterial.trailer_type_id == ids["tt"]).delete(synchronize_session=False)
        db.query(TrailerType).filter_by(id=ids["tt"]).delete()
        db.query(Customer).filter_by(id=ids["customer"]).delete()
        db.query(BOMSection).filter(BOMSection.id.in_(ids["secs"])).delete(
            synchronize_session=False)
        db.query(Material).filter(Material.id.in_(ids["mats"])).delete(
            synchronize_session=False)
        db.query(UserSession).filter(UserSession.id.like("v150p3-%")).delete(
            synchronize_session=False)
        db.execute(_text("DELETE FROM icb_costings.users WHERE username LIKE 'v150p3-%'"))
        db.commit()
    from app.services import invalidate_sections as _inval
    _inval()   # the sections are gone; no later module may see them cached


@pytest.fixture(scope="module")
def full_headers(seeded):
    return _make_session("v150p3-full")


@pytest.fixture(scope="module")
def user_headers(seeded):
    return _make_session("v150p3-user")


# ── Feature 1: the category list ─────────────────────────────────────────────

def test_categories_lists_real_sections_only(client, seeded, admin_headers):
    r = client.get(f"/api/repair/body-categories?trailer_type_id={seeded['tt']}",
                   headers=admin_headers)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["categories"]]
    assert names == [SEC_SIDES, SEC_FLOOR, SEC_OPT]      # section order; no archived
    assert SEC_ARCHIVED not in names


def test_categories_requires_auth(client, seeded):
    r = client.get(f"/api/repair/body-categories?trailer_type_id={seeded['tt']}")
    assert r.status_code == 401


def test_categories_unknown_trailer_404(client, admin_headers):
    r = client.get("/api/repair/body-categories?trailer_type_id=99999999",
                   headers=admin_headers)
    assert r.status_code == 404


# ── Feature 1: the preview computes with the body costing's own engine ───────

def _preview(client, headers, seeded, categories, dims=DIMS):
    return client.post("/api/repair/category-preview", headers=headers,
                       json={"trailer_type_id": seeded["tt"],
                             "dimensions": dims, "categories": categories})


def test_preview_quantities_match_body_costing(client, seeded, admin_headers):
    """THE proof the computation is shared, not reimplemented: the same body +
    dimensions through POST /api/calculate shows the same SIDES quantities,
    prices and line totals the preview returns."""
    body = client.post("/api/calculate", headers=admin_headers,
                       json={"trailer_type_id": seeded["tt"], "dimensions": DIMS})
    assert body.status_code == 200
    body_sides = {it["material"]: it for it in body.json()["items"]
                  if it["category"] == SEC_SIDES}

    r = _preview(client, admin_headers, seeded, [SEC_SIDES])
    assert r.status_code == 200
    data = r.json()
    prev = {ln["description"]: ln for ln in data["lines"]}

    assert set(prev) == set(body_sides) and prev, "same lines, and there are lines"
    for name, ln in prev.items():
        assert ln["qty"] == body_sides[name]["quantity"]
        assert ln["unit_price"] == body_sides[name]["unit_price"]
        assert ln["line_total"] == body_sides[name]["line_cost"]

    # And the numbers themselves are the geometry's numbers: length*height at
    # 7.5 x 2.3 = 17.25, doubled by the SIDES multiplier; 100 rivets + 10% waste.
    assert prev[f"{TT_NAME} SIDE PANEL"]["qty"] == pytest.approx(34.5)
    assert prev[f"{TT_NAME} RIVETS"]["qty"] == pytest.approx(220.0)
    assert prev[f"{TT_NAME} SIDE PANEL"]["material_id"] == seeded["m_side"]


def test_preview_multiple_categories(client, seeded, admin_headers):
    r = _preview(client, admin_headers, seeded, [SEC_SIDES, SEC_FLOOR])
    assert r.status_code == 200
    cats = {ln["category"] for ln in r.json()["lines"]}
    assert cats == {SEC_SIDES, SEC_FLOOR}
    floor = [ln for ln in r.json()["lines"] if ln["category"] == SEC_FLOOR][0]
    assert floor["qty"] == pytest.approx(17.25)          # 7.5 * 2.3


def test_preview_optional_section_is_included_when_picked(client, seeded, admin_headers):
    """Picking the category IS the opt-in — an optional section arrives priced,
    never soft-excluded. (In a body costing this section contributes nothing
    until enabled; the explicit pick replaces that gate.)"""
    r = _preview(client, admin_headers, seeded, [SEC_OPT])
    assert r.status_code == 200
    (ln,) = r.json()["lines"]
    assert ln["qty"] == pytest.approx(2.0)
    assert ln["line_total"] == pytest.approx(120.0)      # 2 x 60
    assert r.json()["total"] == pytest.approx(120.0)


def test_preview_validation(client, seeded, admin_headers):
    # unknown body
    r = client.post("/api/repair/category-preview", headers=admin_headers,
                    json={"trailer_type_id": 99999999, "dimensions": DIMS,
                          "categories": [SEC_SIDES]})
    assert r.status_code == 404
    # missing dimensions — a plain message, not a silent zero-quantity preview
    r = _preview(client, admin_headers, seeded, [SEC_SIDES],
                 dims={"length": 7.5, "width": 0, "height": 2.3})
    assert r.status_code == 422
    assert "dimensions" in r.json()["detail"].lower()
    # a category the body does not have (the archived section is not a category)
    r = _preview(client, admin_headers, seeded, [SEC_ARCHIVED])
    assert r.status_code == 422
    # no categories at all
    r = _preview(client, admin_headers, seeded, [])
    assert r.status_code == 422


def test_preview_writes_nothing(client, seeded, admin_headers):
    from app.database import SessionLocal, CalculationRecord, Material
    with SessionLocal() as db:
        before_calcs = db.query(CalculationRecord).count()
        before_mats = db.query(Material).count()
    r = _preview(client, admin_headers, seeded, [SEC_SIDES])
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(CalculationRecord).count() == before_calcs
        assert db.query(Material).count() == before_mats


# ── Feature 1: pulled lines ride the repair save + reopen intact ─────────────

def test_pulled_lines_save_and_reopen_with_origin(client, seeded, admin_headers):
    pulled = _preview(client, admin_headers, seeded, [SEC_SIDES]).json()["lines"]
    repair_lines = [{
        "kind": "free_hand", "key": ln["key"], "description": ln["description"],
        "qty": ln["qty"], "unit": ln["unit"], "unit_price": ln["unit_price"],
        "material_id": ln["material_id"], "origin": ln["category"],
    } for ln in pulled]
    payload = {
        "is_repair": True, "trailer_type_id": None,
        "repair_type": "Side panel replacement",
        "repair_lines": repair_lines,
        "repair_vehicle": {"trailer_type_id": seeded["tt"], "trailer_name": TT_NAME,
                           **DIMS},
        "customer_id": seeded["customer"],
        "profit_margin": 0, "dimensions": {},
    }
    calc = client.post("/api/calculate", headers=admin_headers, json=payload)
    assert calc.status_code == 200
    expected_total = round(sum(ln["line_total"] for ln in pulled), 2)
    assert calc.json()["grand_total"] == pytest.approx(expected_total)

    saved = client.post("/api/approve", headers=admin_headers, json=payload)
    assert saved.status_code == 200
    rec_id = saved.json()["record_id"]

    got = client.get(f"/api/calculations/{rec_id}", headers=admin_headers)
    assert got.status_code == 200
    rd = got.json()
    assert rd["is_repair"] is True and rd["trailer_type_id"] is None
    assert rd["repair_vehicle"] == {"trailer_type_id": seeded["tt"],
                                    "trailer_name": TT_NAME, **DIMS}
    lines = rd["repair_lines"]
    assert {ln["origin"] for ln in lines} == {SEC_SIDES}
    assert all(ln["material_id"] for ln in lines)
    assert all(ln["kind"] == "free_hand" for ln in lines)


# ── Feature 2: permission gate ───────────────────────────────────────────────

def _tpl_lines(seeded):
    return [
        {"kind": "stock", "material_id": seeded["m_glue"], "qty": 2},
        {"kind": "free_hand", "description": "SIDE PANEL FROM PULL", "qty": 34.5,
         "unit": "m2", "material_id": seeded["m_side"], "origin": SEC_SIDES},
        {"kind": "free_hand", "description": "LABOUR", "qty": 8, "unit": "hours"},
    ]


def test_gate_string_is_a_catalogue_key():
    """v1.48 lesson: a gate string that is NOT in PERMISSION_CATALOGUE is
    invisible — admin short-circuits user_can, so nothing notices."""
    from app.database import PERMISSION_CATALOGUE
    from app.routers.repair_templates import MANAGE_PERM
    entry = {name: roles for name, _d, _c, roles in PERMISSION_CATALOGUE}
    assert MANAGE_PERM in entry
    assert entry[MANAGE_PERM] == {"admin", "full"}


def test_create_template_denied_for_user_role(client, seeded, user_headers):
    r = client.post("/api/repair-templates", headers=user_headers,
                    json={"name": "V150 P3 NOPE", "lines": _tpl_lines(seeded)})
    assert r.status_code == 403


def test_full_role_creates_uses_and_retires(client, seeded, full_headers):
    r = client.post("/api/repair-templates", headers=full_headers,
                    json={"name": "V150 P3 FULL-ROLE", "lines": _tpl_lines(seeded)})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert client.get(f"/api/repair-templates/{tid}/expand",
                      headers=full_headers).status_code == 200
    assert client.post(f"/api/repair-templates/{tid}/retire",
                       headers=full_headers).status_code == 200


def test_user_role_can_still_USE_templates(client, seeded, admin_headers, user_headers):
    r = client.post("/api/repair-templates", headers=admin_headers,
                    json={"name": "V150 P3 USABLE", "lines": _tpl_lines(seeded)})
    tid = r.json()["id"]
    assert client.get("/api/repair-templates",
                      headers=user_headers).status_code == 200
    assert client.get(f"/api/repair-templates/{tid}/expand",
                      headers=user_headers).status_code == 200
    # ... but not manage: include_retired, PUT, retire are all refused.
    assert client.get("/api/repair-templates?include_retired=1",
                      headers=user_headers).status_code == 403
    assert client.put(f"/api/repair-templates/{tid}", headers=user_headers,
                      json={"name": "X"}).status_code == 403
    assert client.post(f"/api/repair-templates/{tid}/retire",
                       headers=user_headers).status_code == 403


# ── Feature 2: live prices, never stored ─────────────────────────────────────

def test_expand_prices_live_from_the_material_list(client, seeded, admin_headers):
    from app.database import SessionLocal, Material
    r = client.post("/api/repair-templates", headers=admin_headers,
                    json={"name": "V150 P3 LIVE PRICE", "lines": _tpl_lines(seeded)})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    by_desc = {ln["description"]: ln for ln in r.json()["lines"]}
    assert by_desc[f"{TT_NAME} GLUE"]["unit_price"] == 250.0
    assert by_desc["SIDE PANEL FROM PULL"]["unit_price"] == 100.0   # offered live
    assert by_desc["LABOUR"]["unit_price"] is None                  # typed at use

    with SessionLocal() as db:      # the price moves; the template must follow
        db.query(Material).filter_by(id=seeded["m_glue"]).update(
            {"price_per_unit": 300.0})
        db.query(Material).filter_by(id=seeded["m_side"]).update(
            {"price_per_unit": 111.0})
        db.commit()
    try:
        got = client.get(f"/api/repair-templates/{tid}/expand", headers=admin_headers)
        by_desc = {ln["description"]: ln for ln in got.json()["lines"]}
        assert by_desc[f"{TT_NAME} GLUE"]["unit_price"] == 300.0
        assert by_desc[f"{TT_NAME} GLUE"]["qty"] == 2               # default qty kept
        assert by_desc["SIDE PANEL FROM PULL"]["unit_price"] == 111.0
        assert by_desc["SIDE PANEL FROM PULL"]["origin"] == SEC_SIDES
    finally:
        with SessionLocal() as db:
            db.query(Material).filter_by(id=seeded["m_glue"]).update(
                {"price_per_unit": 250.0})
            db.query(Material).filter_by(id=seeded["m_side"]).update(
                {"price_per_unit": 100.0})
            db.commit()


def test_expand_marks_a_gone_material_unavailable(client, seeded, admin_headers):
    from app.database import SessionLocal, Material
    r = client.post("/api/repair-templates", headers=admin_headers,
                    json={"name": "V150 P3 GONE MAT",
                          "lines": [{"kind": "stock", "material_id": seeded["m_floor"],
                                     "qty": 1}]})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    with SessionLocal() as db:
        db.query(Material).filter_by(id=seeded["m_floor"]).update({"is_active": False})
        db.commit()
    try:
        (ln,) = client.get(f"/api/repair-templates/{tid}/expand",
                           headers=admin_headers).json()["lines"]
        assert ln["unavailable"] is True
        assert ln["unit_price"] is None
        assert ln["description"] == f"{TT_NAME} FLOOR PLY"   # snapshot still names it
    finally:
        with SessionLocal() as db:
            db.query(Material).filter_by(id=seeded["m_floor"]).update({"is_active": True})
            db.commit()


def test_template_validation(client, seeded, admin_headers):
    # no name
    assert client.post("/api/repair-templates", headers=admin_headers,
                       json={"name": "", "lines": _tpl_lines(seeded)}).status_code == 422
    # no lines
    assert client.post("/api/repair-templates", headers=admin_headers,
                       json={"name": "V150 P3 EMPTY", "lines": []}).status_code == 422
    # a stock line must name a real material
    assert client.post("/api/repair-templates", headers=admin_headers,
                       json={"name": "V150 P3 BAD STOCK",
                             "lines": [{"kind": "stock", "material_id": 99999999,
                                        "qty": 1}]}).status_code == 422


# ── Feature 2: soft retire ───────────────────────────────────────────────────

def test_retire_is_soft_and_refuses_use(client, seeded, admin_headers):
    r = client.post("/api/repair-templates", headers=admin_headers,
                    json={"name": "V150 P3 RETIRE ME", "lines": _tpl_lines(seeded)})
    tid = r.json()["id"]
    assert client.post(f"/api/repair-templates/{tid}/retire",
                       headers=admin_headers).status_code == 200

    listed = client.get("/api/repair-templates", headers=admin_headers).json()
    assert tid not in [t["id"] for t in listed]                    # gone from the picker
    with_retired = client.get("/api/repair-templates?include_retired=1",
                              headers=admin_headers).json()
    mine = [t for t in with_retired if t["id"] == tid]
    assert mine and mine[0]["retired_at"] and mine[0]["retired_by"] == "admin"

    r = client.get(f"/api/repair-templates/{tid}/expand", headers=admin_headers)
    assert r.status_code == 409                                    # unusable, said plainly
    assert "retired" in r.json()["detail"].lower()

    assert client.post(f"/api/repair-templates/{tid}/restore",
                       headers=admin_headers).status_code == 200
    assert client.get(f"/api/repair-templates/{tid}/expand",
                      headers=admin_headers).status_code == 200


def test_rename_and_replace_lines(client, seeded, admin_headers):
    r = client.post("/api/repair-templates", headers=admin_headers,
                    json={"name": "V150 P3 RENAME ME", "lines": _tpl_lines(seeded)})
    tid = r.json()["id"]
    r = client.put(f"/api/repair-templates/{tid}", headers=admin_headers,
                   json={"name": "V150 P3 RENAMED",
                         "lines": [{"kind": "free_hand", "description": "just glue",
                                    "qty": 1, "unit": "each"}]})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "V150 P3 RENAMED"
    assert data["updated_by"] == "admin"
    assert [ln["description"] for ln in data["lines"]] == ["JUST GLUE"]  # upper-cased
