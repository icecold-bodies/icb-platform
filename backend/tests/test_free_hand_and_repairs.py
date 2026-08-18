"""v1.47 Lane C — free-hand lines + the REPAIRS costing mode.

Two features, one mechanism (Nadie, 17 Aug): a line carrying description · qty ·
unit · unit price · notes that costs exactly like a BOM line.

What these units pin:

FREE-HAND OPTIONAL EXTRAS
  * a free-hand line lands in its section's category total, the materials cost
    and the grand total — by qty × unit price, with no special-casing
  * the line is marked free_hand in the items payload and carries its own key
  * a line the user unticks contributes nothing (line_cost 0, out of the total)
  * a line in an OPTIONAL section the user has NOT opted into is soft-excluded,
    exactly as the real rows in that section are
  * malformed lines are refused with 422, not silently coerced
  * NOTHING is written to the materials master — the master's row count and the
    line's own material are unchanged after a save
  * a costing with no free-hand lines produces the identical payload it did
    before v1.47 (no stray keys on any item)

REPAIRS MODE
  * calculate/approve with is_repair and no trailer_type_id needs no body: no
    dimensions, no BOM, no geometry
  * a stock line is priced from the CATALOGUE, ignoring any price the client
    sends; a free-hand line uses the typed price
  * margin / ratio / discount come from the same functions the body path uses
  * the saved record carries is_repair=True with a NULL trailer_type_id, gets a
    quote number, and shows up under ?filter=repair
  * the existing downstream machinery accepts it untouched: POST
    /api/calculations/{id}/schedule-repair (which 409s on non-repairs) succeeds
  * a repair cannot be marked as a validated reference (no body configuration to
    fingerprint) — 409, not a 500
  * the repair document renders in all three formats with the REPAIR heading

Sessions are real UserSession rows via raw Cookie headers (banked pattern).
"""
import uuid

import pytest

TT_NAME = "V147 LANEC BODY"
OPT_SECTION = "V147 OPTIONAL EXTRAS"
PLAIN_SECTION = "V147 FLOOR"


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
    sid = f"v147c-{uuid.uuid4().hex[:12]}"
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
    """One body with a PLAIN section and an OPTIONAL section, plus a catalogue
    material for the repair stock-line path. Ids are tracked for teardown."""
    from app.database import (SessionLocal, TrailerType, BillOfMaterial,
                              BOMSection, Material, Customer)
    ids = {}
    with SessionLocal() as db:
        mat = Material(name=f"{TT_NAME} PLYWOOD", unit_of_measure="m2",
                       price_per_unit=100.0, is_active=True)
        stock = Material(name=f"{TT_NAME} REPAIR SEAL", unit_of_measure="each",
                         price_per_unit=250.0, is_active=True)
        opt_mat = Material(name=f"{TT_NAME} EXTRA TRAY", unit_of_measure="each",
                           price_per_unit=60.0, is_active=True)
        db.add_all([mat, stock, opt_mat])
        db.flush()

        # BOMSection rows are GLOBAL (identity by name) — use marked names so this
        # module cannot collide with, or perturb, any real section.
        plain_sec = BOMSection(name=PLAIN_SECTION, sort_order=10, is_optional=False)
        opt_sec = BOMSection(name=OPT_SECTION, sort_order=11, is_optional=True)
        db.add_all([plain_sec, opt_sec])
        db.flush()

        tt = TrailerType(name=TT_NAME, is_active=True, default_length=10.0,
                         default_width=2.5, default_height=2.6)
        db.add(tt)
        db.flush()
        r1 = BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                            formula_expression="10", waste_percentage=0,
                            bom_section=PLAIN_SECTION, bom_section_id=plain_sec.id,
                            sort_order=1)
        r2 = BillOfMaterial(trailer_type_id=tt.id, material_id=opt_mat.id,
                            formula_expression="2", waste_percentage=0,
                            bom_section=OPT_SECTION, bom_section_id=opt_sec.id,
                            sort_order=2)
        cust = Customer(name=f"{TT_NAME} CUSTOMER", is_active=True)
        db.add_all([r1, r2, cust])
        db.commit()
        ids = {"tt": tt.id, "bom_plain": r1.id, "bom_opt": r2.id,
               "mat": mat.id, "stock": stock.id, "opt_mat": opt_mat.id,
               "plain_sec": plain_sec.id, "opt_sec": opt_sec.id,
               "customer": cust.id}
    yield ids
    with SessionLocal() as db:
        from app.database import CalculationRecord
        db.query(CalculationRecord).filter(
            (CalculationRecord.trailer_type_id == ids["tt"])
            | (CalculationRecord.customer_id == ids["customer"])).delete(
                synchronize_session=False)
        db.query(BillOfMaterial).filter(
            BillOfMaterial.trailer_type_id == ids["tt"]).delete(synchronize_session=False)
        db.query(TrailerType).filter_by(id=ids["tt"]).delete()
        db.query(Customer).filter_by(id=ids["customer"]).delete()
        db.query(BOMSection).filter(BOMSection.id.in_(
            [ids["plain_sec"], ids["opt_sec"]])).delete(synchronize_session=False)
        db.query(Material).filter(Material.id.in_(
            [ids["mat"], ids["stock"], ids["opt_mat"]])).delete(synchronize_session=False)
        db.commit()


def _body(seeded, **over):
    payload = {
        "trailer_type_id": seeded["tt"],
        "dimensions": {"length": 10.0, "width": 2.5, "height": 2.6},
        "profit_margin": 0,
        # Opt into the OPTIONAL section so its rows (and free-hand lines) count.
        "optional_sections_enabled": [seeded["opt_sec"]],
    }
    payload.update(over)
    return payload


def _fh(**over):
    line = {"kind": "free_hand", "key": "k1", "description": "Rubber seal kit",
            "qty": 2, "unit": "each", "unit_price": 450}
    line.update(over)
    return line


def _item_by_key(result, key):
    for it in result["items"]:
        if it.get("free_hand_key") == key:
            return it
    return None


# ── free-hand OPTIONAL EXTRAS ────────────────────────────────────────────────

def test_free_hand_line_adds_qty_times_price_to_the_totals(client, admin_headers, seeded):
    """The whole point: R900 of free-hand extra moves the total by R900."""
    base = client.post("/api/calculate", json=_body(seeded), headers=admin_headers)
    assert base.status_code == 200, base.text
    before = base.json()

    withfh = client.post("/api/calculate", json=_body(
        seeded,
        free_hand_lines=[_fh(bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert withfh.status_code == 200, withfh.text
    after = withfh.json()

    assert after["grand_total"] == pytest.approx(before["grand_total"] + 900.0)
    assert after["category_totals"][OPT_SECTION] == pytest.approx(
        before["category_totals"][OPT_SECTION] + 900.0)

    it = _item_by_key(after, "k1")
    assert it is not None, "the free-hand line is missing from items"
    assert it["free_hand"] is True
    assert it["material"] == "Rubber seal kit"
    assert it["quantity"] == pytest.approx(2.0)
    assert it["unit_price"] == pytest.approx(450.0)
    assert it["line_cost"] == pytest.approx(900.0)
    # A typed quantity is not a formula, so it can never read as a formula error.
    assert it["formula_error"] is False
    assert it["formula"] == ""


def test_free_hand_line_rides_the_margin_and_ratio_maths(client, admin_headers, seeded):
    """No special-casing: the extra flows through margin and ratio like any line."""
    r = client.post("/api/calculate", json=_body(
        seeded, profit_margin=10, ratio_value=0.5, ratio_label="50%",
        free_hand_lines=[_fh(bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    grand = d["grand_total"]
    assert d["profit_amount"] == pytest.approx(round(grand * 0.10, 2))
    assert d["selling_price"] == pytest.approx(round((grand + d["profit_amount"]) / 0.5, 2))


def test_unticked_free_hand_line_contributes_nothing(client, admin_headers, seeded):
    base = client.post("/api/calculate", json=_body(seeded), headers=admin_headers).json()
    r = client.post("/api/calculate", json=_body(
        seeded,
        free_hand_lines=[_fh(bom_section_id=seeded["opt_sec"], category=OPT_SECTION,
                             excluded=True)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grand_total"] == pytest.approx(base["grand_total"])
    it = _item_by_key(d, "k1")
    assert it["excluded"] is True
    assert it["line_cost"] == pytest.approx(0.0)
    assert it["excluded_reason"] == "Excluded by user"


def test_free_hand_line_follows_its_optional_sections_optin(client, admin_headers, seeded):
    """A line in an OPTIONAL section the user has not opted into is soft-excluded —
    the same treatment _build_bom_items gives the real rows there."""
    r = client.post("/api/calculate", json=_body(
        seeded,
        optional_sections_enabled=[],   # section NOT opted into
        free_hand_lines=[_fh(bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    it = _item_by_key(r.json(), "k1")
    assert it["excluded"] is True
    assert it["excluded_reason"] == "Optional section not included"
    assert it["line_cost"] == pytest.approx(0.0)


@pytest.mark.parametrize("bad, why", [
    ({"description": ""},               "empty description"),
    ({"description": "   "},            "whitespace-only description"),
    ({"qty": -1},                       "negative qty"),
    ({"qty": "abc"},                    "non-numeric qty"),
    ({"qty": None},                     "missing qty"),
    ({"unit_price": -0.01},             "negative price"),
    ({"unit_price": "R450"},            "non-numeric price"),
    ({"unit_price": None},              "missing price"),
    ({"description": "x" * 201},        "over-long description"),
    ({"qty": 1e12},                     "absurd qty"),
    ({"unit_price": 1e12},              "absurd price"),
])
def test_malformed_free_hand_line_is_refused_cleanly(client, admin_headers, seeded, bad, why):
    r = client.post("/api/calculate", json=_body(seeded, free_hand_lines=[_fh(**bad)]),
                    headers=admin_headers)
    assert r.status_code == 422, f"{why} should 422, got {r.status_code}: {r.text[:200]}"
    assert r.json().get("detail"), "a 422 must carry a message fit to show the user"


def test_too_many_free_hand_lines_is_refused(client, admin_headers, seeded):
    lines = [_fh(key=f"k{i}") for i in range(201)]
    r = client.post("/api/calculate", json=_body(seeded, free_hand_lines=lines),
                    headers=admin_headers)
    assert r.status_code == 422


def test_comma_decimal_is_accepted_like_sa_money(client, admin_headers, seeded):
    """"450,50" is how SA money is typed — the server accepts it, as the unit-price
    inputs on the costing page already do."""
    r = client.post("/api/calculate", json=_body(
        seeded,
        free_hand_lines=[_fh(qty="2", unit_price="450,50",
                             bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    assert _item_by_key(r.json(), "k1")["line_cost"] == pytest.approx(901.0)


def test_free_hand_never_writes_to_the_materials_master(client, admin_headers, seeded):
    """The invariant Nadie's feature turns on: a free-hand line is quote-local."""
    from app.database import SessionLocal, Material
    with SessionLocal() as db:
        before = db.query(Material).count()
    r = client.post("/api/approve", json=_body(
        seeded, customer_id=seeded["customer"],
        free_hand_lines=[_fh(description="Ghost material XYZ",
                             bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.query(Material).count() == before, "a free-hand line created a material row"
        assert db.query(Material).filter_by(name="Ghost material XYZ").first() is None


def test_free_hand_line_survives_the_save_snapshot(client, admin_headers, seeded):
    """It rides input_state so an edit re-hydrates it — no new column anywhere."""
    r = client.post("/api/approve", json=_body(
        seeded, customer_id=seeded["customer"], version_action="save_as_new",
        free_hand_lines=[_fh(notes="ex stock Cape Town",
                             bom_section_id=seeded["opt_sec"], category=OPT_SECTION)],
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    rec_id = r.json()["record_id"]
    got = client.get(f"/api/calculations/{rec_id}", headers=admin_headers)
    assert got.status_code == 200, got.text
    lines = got.json()["free_hand_lines"]
    assert len(lines) == 1
    assert lines[0]["description"] == "Rubber seal kit"
    assert lines[0]["qty"] == pytest.approx(2.0)
    assert lines[0]["unit_price"] == pytest.approx(450.0)
    assert lines[0]["notes"] == "ex stock Cape Town"


def test_a_costing_without_free_hand_lines_is_unchanged(client, admin_headers, seeded):
    """The regression guard: no stray keys on any item, so every existing costing,
    export and journey sees exactly the pre-v1.47 payload."""
    r = client.post("/api/calculate", json=_body(seeded), headers=admin_headers)
    assert r.status_code == 200, r.text
    for it in r.json()["items"]:
        assert "free_hand" not in it
        assert "free_hand_key" not in it
        assert "notes" not in it


# ── REPAIRS mode ─────────────────────────────────────────────────────────────

def _repair(seeded, **over):
    payload = {
        "is_repair": True,
        "trailer_type_id": None,
        "repair_type": "Side panel replacement",
        "repair_scope": "Strip damaged panel, fit new panel, laminate joints.",
        "repair_lines": [
            {"kind": "stock", "key": "s1", "material_id": seeded["stock"], "qty": 3},
            {"kind": "free_hand", "key": "f1", "description": "Spray booth time",
             "qty": 4, "unit": "hour", "unit_price": 300},
        ],
        "profit_margin": 0,
        "dimensions": {},
    }
    payload.update(over)
    return payload


def test_repair_costs_without_a_body(client, admin_headers, seeded):
    r = client.post("/api/calculate", json=_repair(seeded), headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_repair"] is True
    assert d["repair_type"] == "Side panel replacement"
    # 3 × 250 (catalogue) + 4 × 300 (typed) = 1950
    assert d["grand_total"] == pytest.approx(1950.0)
    assert list(d["category_totals"].keys()) == ["REPAIR LINES"]
    assert d["category_totals"]["REPAIR LINES"] == pytest.approx(1950.0)
    # A repair result keeps the SHAPE of a body result — the summary panel and the
    # document builders read result.geometry directly, and a missing block took
    # the whole summary render down (caught in the §3.4 journey). The geometry is
    # all zeros, and cost_per_sqm is zeroed rather than left as grand_total ÷ the
    # "or 1" floor-area fallback, which would print the repair's whole value as
    # its cost per m². The per-m² row is hidden for repairs client-side.
    assert d["geometry"]["floor_area"] == pytest.approx(0.0)
    assert d["cost_per_sqm"] == pytest.approx(0.0)


def test_stock_line_is_priced_from_the_catalogue_not_the_client(client, admin_headers, seeded):
    """A tampered or stale client price on a stock line is ignored outright."""
    r = client.post("/api/calculate", json=_repair(seeded, repair_lines=[
        {"kind": "stock", "key": "s1", "material_id": seeded["stock"], "qty": 1,
         "unit_price": 999999, "description": "FREE STUFF"},
    ]), headers=admin_headers)
    assert r.status_code == 200, r.text
    it = _item_by_key(r.json(), "s1")
    assert it["unit_price"] == pytest.approx(250.0), "client price must not win"
    assert it["material"] == f"{TT_NAME} REPAIR SEAL", "catalogue name must win"
    assert it["line_cost"] == pytest.approx(250.0)


def test_repair_reuses_the_margin_ratio_discount_functions(client, admin_headers, seeded):
    r = client.post("/api/calculate", json=_repair(
        seeded, profit_margin=20, ratio_value=0.5, ratio_label="50%",
        discount_kind="percent", discount_input=10,
    ), headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grand_total"] == pytest.approx(1950.0)
    assert d["profit_amount"] == pytest.approx(390.0)          # 1950 × 20%
    assert d["selling_price"] == pytest.approx(4680.0)         # (1950+390) / 0.5
    assert d["discount_amount"] == pytest.approx(468.0)        # 10% of 4680
    assert d["net_total"] == pytest.approx(4212.0)


def test_repair_with_no_lines_is_refused(client, admin_headers, seeded):
    r = client.post("/api/calculate", json=_repair(seeded, repair_lines=[]),
                    headers=admin_headers)
    assert r.status_code == 422
    assert "at least one line" in r.json()["detail"]


def test_a_repair_prices_before_it_has_a_type(client, admin_headers, seeded):
    """Michael, 18 Aug: adding a repair line left every total on R0,00.

    The type of repair was required to CALCULATE as well as to save, so the
    header rail and the price summary stayed empty until it happened to be
    filled in — the surface looked broken. Pricing is a preview; the type is a
    commitment made at save time."""
    r = client.post("/api/calculate", json=_repair(seeded, repair_type=""),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grand_total"] == pytest.approx(1950.0), "the lines must still price"
    assert d["is_repair"] is True
    assert not d.get("repair_type")


def test_a_repair_still_cannot_be_SAVED_without_a_type(client, admin_headers, seeded):
    """The other half of the same rule — relaxing the calculate path must not
    let a repair reach the database with no type on it."""
    r = client.post("/api/approve", json=_repair(
        seeded, repair_type="", customer_id=seeded["customer"]), headers=admin_headers)
    assert r.status_code == 422, r.text
    assert "Type of repair" in r.json()["detail"]


def test_repair_stock_line_for_a_dead_material_is_refused(client, admin_headers, seeded):
    r = client.post("/api/calculate", json=_repair(seeded, repair_lines=[
        {"kind": "stock", "key": "s1", "material_id": 99999999, "qty": 1},
    ]), headers=admin_headers)
    assert r.status_code == 422
    assert "no longer in the list" in r.json()["detail"]


def test_stock_lines_are_not_accepted_on_a_body_costing(client, admin_headers, seeded):
    """The OPTIONAL EXTRAS surface has the real BOM for catalogue items; minting a
    stock line there would be a second, unaudited route to the same thing."""
    r = client.post("/api/calculate", json=_body(seeded, free_hand_lines=[
        {"kind": "stock", "key": "s1", "material_id": seeded["stock"], "qty": 1},
    ]), headers=admin_headers)
    assert r.status_code == 422
    assert "not valid here" in r.json()["detail"]


def test_saved_repair_carries_the_existing_repair_identity(client, admin_headers, seeded):
    """The ratified contract: the new surface CREATES a costing with the identity
    the downstream MES already models, so nothing downstream changes."""
    from app.database import SessionLocal, CalculationRecord
    r = client.post("/api/approve", json=_repair(seeded, customer_id=seeded["customer"]),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    rec_id = d["record_id"]
    assert d["quote_number"], "a repair must get a quote number like any costing"
    assert d["version"] == 1

    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=rec_id).first()
        assert rec.is_repair is True
        assert rec.trailer_type_id is None, "a repair is a MODE, not a trailer template"
        assert rec.customer_id == seeded["customer"]
        assert rec.net_total is not None

    rows = client.get("/api/calculations?filter=repair", headers=admin_headers).json()
    row = next((x for x in rows if x["id"] == rec_id), None)
    assert row is not None, "the repair does not appear where repairs appear"
    assert row["is_repair"] is True
    assert row["trailer"] == "REPAIRS"
    assert row["repair_type"] == "Side panel replacement"
    assert row["repair_scope"].startswith("Strip damaged panel")


def test_created_repair_can_be_scheduled_into_the_mes(client, admin_headers, seeded):
    """The acceptance test: a repair created here reaches the existing scheduling
    machinery unchanged. /schedule-repair 409s unless is_repair is set, so this
    passing IS the proof the identity is right."""
    from app.database import SessionLocal, CalculationRecord
    import json as _json
    made = client.post("/api/approve", json=_repair(
        seeded, customer_id=seeded["customer"], version_action="save_as_new"),
        headers=admin_headers)
    assert made.status_code == 200, made.text
    rec_id = made.json()["record_id"]

    sched = client.post(f"/api/calculations/{rec_id}/schedule-repair",
                        json={"phases": [
                            {"phase": "DOORS", "bay_id": "DR-1", "estimated_hours": 6},
                            {"phase": "GRP", "bay_id": "GRP-2", "estimated_hours": 4},
                        ]}, headers=admin_headers)
    assert sched.status_code == 200, sched.text
    assert len(sched.json()["repair_phases"]) == 2

    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=rec_id).first()
        phases = _json.loads(rec.repair_phases_json)
    assert [p["phase"] for p in phases] == ["DOORS", "GRP"]
    # The work description must NOT have been written over the scheduler's column.
    assert isinstance(phases, list)


def test_repair_cannot_be_marked_as_a_validated_reference(client, admin_headers, seeded):
    """A repair has no body configuration to fingerprint. It must refuse cleanly
    rather than 500 inside config_fingerprint(int(None))."""
    made = client.post("/api/approve", json=_repair(
        seeded, customer_id=seeded["customer"], version_action="save_as_new"),
        headers=admin_headers)
    assert made.status_code == 200, made.text
    rec_id = made.json()["record_id"]
    r = client.post("/api/validated-references",
                    json={"calculation_id": rec_id, "label": "nope"},
                    headers=admin_headers)
    assert r.status_code == 409, r.text
    assert "no body configuration" in r.json()["detail"]


# ── documents ────────────────────────────────────────────────────────────────

def test_free_hand_line_is_marked_manual_in_the_documents(app_mod):
    """The document equivalent of the manual chip, shared by all three renderers."""
    from app.routers.exports import _formula_cell
    assert _formula_cell({"free_hand": True, "formula": ""}) == "manual"
    assert _formula_cell({"formula": "L*W*2"}) == "L*W*2", "normal lines untouched"
    assert _formula_cell({}) == ""


@pytest.mark.parametrize("fmt", ["excel", "word", "pdf"])
def test_repair_previews_in_all_three_formats(client, admin_headers, seeded, fmt):
    calc = client.post("/api/calculate", json=_repair(seeded, profit_margin=10,
                                                      ratio_value=0.5, ratio_label="50%"),
                       headers=admin_headers)
    assert calc.status_code == 200, calc.text
    r = client.post("/api/export/preview", json={
        "result": calc.json(), "dims": {}, "trailer_type_id": None,
        "is_repair": True, "repair_type": "Side panel replacement",
        "format": fmt, "detail": "items",
    }, headers=admin_headers)
    assert r.status_code == 200, r.text[:300]
    assert len(r.content) > 500, "a rendered document should not be empty"


def test_repair_document_heading_names_the_repair_and_its_type(app_mod):
    from app.routers.exports import _repair_heading_name, _repair_spec_pairs
    assert _repair_heading_name("Side panel replacement") == "REPAIR · Side panel replacement"
    assert _repair_heading_name("") == "REPAIR"
    pairs = _repair_spec_pairs("Panel swap", "Strip and refit.")
    assert pairs[0] == ("Type of repair", "Panel swap")
    assert pairs[1] == ("Work description", "Strip and refit.")
    # No work description → no empty row.
    assert len(_repair_spec_pairs("Panel swap", None)) == 1


def test_the_32m_zero_rule_never_fires_on_a_repair(client, admin_headers, seeded):
    """A repair has no length, so the length-pinned rule has nothing to match."""
    from app.services import zero_rule_note
    calc = client.post("/api/calculate", json=_repair(seeded), headers=admin_headers)
    assert calc.status_code == 200, calc.text
    assert zero_rule_note(calc.json()) is None


def test_a_repair_save_cannot_overwrite_a_body_costing(client, admin_headers, seeded):
    """Symmetrical-state guard (v1.45 lesson). A stale or hand-crafted payload
    must not drop a repair result onto a BODY costing, which would leave a record
    with a repair result_json and a trailer_type_id still set."""
    made = client.post("/api/approve", json=_body(
        seeded, customer_id=seeded["customer"], version_action="save_as_new"),
        headers=admin_headers)
    assert made.status_code == 200, made.text
    body_id = made.json()["record_id"]

    r = client.post("/api/approve", json=_repair(
        seeded, customer_id=seeded["customer"],
        version_action="overwrite", edit_record_id=body_id), headers=admin_headers)
    assert r.status_code == 409, r.text
    assert "not a repair" in r.json()["detail"]

    # And the body costing is untouched.
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=body_id).first()
        assert rec.trailer_type_id == seeded["tt"]
        assert not rec.is_repair


def test_a_body_save_cannot_overwrite_a_repair(client, admin_headers, seeded):
    """The mirror of the guard above — the two must be symmetrical or the hole
    simply moves to the other side."""
    made = client.post("/api/approve", json=_repair(
        seeded, customer_id=seeded["customer"]), headers=admin_headers)
    assert made.status_code == 200, made.text
    repair_id = made.json()["record_id"]

    r = client.post("/api/approve", json=_body(
        seeded, customer_id=seeded["customer"],
        version_action="overwrite", edit_record_id=repair_id), headers=admin_headers)
    assert r.status_code == 409, r.text
    assert "is a repair" in r.json()["detail"]

    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=repair_id).first()
        assert rec.trailer_type_id is None
        assert rec.is_repair is True


def test_a_repair_with_every_line_ticked_off_totals_zero(client, admin_headers, seeded):
    """Michael, 18 Aug (second report): ticking a repair's only line OFF struck
    the line through but left the rail and the summary showing what it used to
    cost. Excluded lines are still SENT — the server prices them at zero, which
    is the honest answer — so the client must not short-circuit the calculate
    when nothing is ticked in."""
    payload = _repair(seeded, profit_margin=10, ratio_value=0.55, ratio_label="55%")
    for line in payload["repair_lines"]:
        line["excluded"] = True
    r = client.post("/api/calculate", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grand_total"] == pytest.approx(0.0)
    assert d.get("profit_amount", 0) == pytest.approx(0.0)
    assert float(d.get("net_total") or 0) == pytest.approx(0.0)
    # Every line still comes back, struck through rather than dropped, so the
    # user can tick one back in.
    assert len(d["items"]) == len(payload["repair_lines"])
    assert all(it["excluded"] for it in d["items"])


def test_ticking_one_of_two_repair_lines_off_prices_only_the_other(
        client, admin_headers, seeded):
    """The partial case the zero test cannot see: the total must follow the
    lines that are still in, not fall to zero and not stay whole."""
    payload = _repair(seeded)          # stock 3 x 250 = 750, free-hand 4 x 300 = 1200
    payload["repair_lines"][0]["excluded"] = True
    r = client.post("/api/calculate", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["grand_total"] == pytest.approx(1200.0)
