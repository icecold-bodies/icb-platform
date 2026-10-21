"""RT8 (v1.62.0) — a re-opened quote is the saved quote.

Michael's rule (19 Oct 2026): when a quote is saved, an exact copy is saved, and anyone editing that quote gets that
exact copy back. Today's template and prices enter a saved quote only when a user asks for them ("Update to today's
prices"), after seeing line by line what would change — and then as a NEW REVISION only.

The N10022 scenario as a fixture (no customer data): a MEAT HANGER LARGE 7.8 x 2.6 x 2.56 at 4G is saved; then the
template changes the way Michael's did on 19 Oct — (a) the ROOF plywood row moves into a NEW radio group
(4MM / 6MM PF PLYWOOD), (b) the SIDES plywood row is re-pointed at another material at the same price, (c) one other
row is deleted, (d) the 4G factor moves from 5581/4100 to 5400/4100. The quote must re-open to the cent, save back
identical when nothing changed, recompute quantities at saved prices on a size change, and re-price only through the
comparison, as a new revision, with the original untouched.

House pattern: live test DB (the db-guard aborts on anything but *_test), marker rows (RT8F), real session rows,
purge child-first by id at setup and teardown.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

MARK = "RT8F"
DIMS = {"length": 7.8, "width": 2.6, "height": 2.56, "floor_thickness": 0.1, "panel_thickness": 0.06,
        "insulation_thickness": 0.06, "num_axles": 3, "num_doors": 2}
FACTOR_BEFORE = 5581.0 / 4100.0
FACTOR_AFTER = 5400.0 / 4100.0
CALC_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "calculator.js"


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):            # startup seeds the admin user + permissions
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _session(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"rt8f-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def admin(app_mod):
    from app.database import SessionLocal, UserSession
    h = _session("admin")
    yield h
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=h["Cookie"].split("session_id=")[1]).delete()
        db.commit()


def _purge() -> None:
    """Marker rows, child-first by id (never TRUNCATE)."""
    from app.database import (AdminSetting, BillOfMaterial, CalculationRecord, ConfiguratorDraft, Customer, Formula,
                              Material, SessionLocal, TrailerType)
    from app.services.insulation_foam import FACTOR_KEY
    with SessionLocal() as db:
        tids = [t.id for t in db.query(TrailerType).filter(TrailerType.name.like(f"{MARK}%")).all()]
        cids = [c.id for c in db.query(Customer).filter(Customer.name.like(f"{MARK}%")).all()]
        q = db.query(CalculationRecord)
        if tids or cids:
            from sqlalchemy import or_
            conds = []
            if tids:
                conds.append(CalculationRecord.trailer_type_id.in_(tids))
            if cids:
                conds.append(CalculationRecord.customer_id.in_(cids))
            for rec in q.filter(or_(*conds)).all():
                db.delete(rec)
        db.flush()
        if tids:
            db.query(ConfiguratorDraft).filter(ConfiguratorDraft.trailer_type_id.in_(tids)).delete(synchronize_session=False)
            db.query(BillOfMaterial).filter(BillOfMaterial.trailer_type_id.in_(tids)).delete(synchronize_session=False)
            db.query(TrailerType).filter(TrailerType.id.in_(tids)).delete(synchronize_session=False)
        db.query(Material).filter_by(material_code=MARK).delete(synchronize_session=False)
        db.query(Formula).filter(Formula.name.like(f"{MARK.lower()}%")).delete(synchronize_session=False)
        if cids:
            db.query(Customer).filter(Customer.id.in_(cids)).delete(synchronize_session=False)
        row = db.query(AdminSetting).filter_by(key=FACTOR_KEY).first()
        keep = db.query(AdminSetting).filter_by(key=f"{MARK}.factor_before").first()
        if row is not None and keep is not None:
            row.value = keep.value          # the factor as it was before this file touched it
        if keep is not None:
            db.delete(keep)
        db.commit()


def _set_factor(value: float) -> None:
    from app.database import AdminSetting, SessionLocal
    from app.services.insulation_foam import FACTOR_KEY
    with SessionLocal() as db:
        row = db.query(AdminSetting).filter_by(key=FACTOR_KEY).first()
        keep = db.query(AdminSetting).filter_by(key=f"{MARK}.factor_before").first()
        if keep is None:
            db.add(AdminSetting(key=f"{MARK}.factor_before", value=(row.value if row else str(FACTOR_BEFORE))))
        if row is None:
            db.add(AdminSetting(key=FACTOR_KEY, value=str(value)))
        else:
            row.value = str(value)
        db.commit()


def _stored(record_id: int) -> dict:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=record_id).first()
        assert rec is not None
        return json.loads(rec.result_json)


def _raw_result_json(record_id: int) -> str:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return db.query(CalculationRecord).filter_by(id=record_id).first().result_json


def _rewrite_result_json(record_id: int, data: dict) -> None:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=record_id).first()
        rec.result_json = json.dumps(data)
        db.commit()


def _snapshot(**over) -> dict:
    snap = {"body_option_selections": {}, "drd_srd": {}, "draft_flag_state": {}, "draft_flag_vars": {},
            "draft_category_radio": {}, "draft_masterless_cat": {}, "draft_folder": {},
            "optional_sections_enabled": [], "optional_row_excl": [], "price_overrides": {}, "ratio": "0.55",
            "chassis": {"enabled": False}, "body_variables": {}}
    snap.update(over)
    return snap


def _body_payload(ids: dict, **over) -> dict:
    p = {"trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5, "overrides": {},
         "override_reasons": {}, "chassis": {"enabled": False}, "insulation_foam": "4G",
         "user_excluded_bom_ids": [], "optional_sections_enabled": [], "customer_id": ids["customer"],
         "ratio_value": 0.55, "ratio_label": "55%", "ui_snapshot": _snapshot()}
    p.update(over)
    return p


def _screen(result: dict) -> dict:
    return {"grand_total": result["grand_total"], "net_total": result["net_total"]}


def _line(items, name_part, category=None):
    for it in items:
        if name_part in (it.get("material") or "") and (category is None or it.get("category") == category):
            return it
    return None


@pytest.fixture(scope="module")
def staged(app_mod, client, admin):
    """The N10022 scenario: the quote saved, THEN the four template changes."""
    from app.database import (BillOfMaterial, Customer, Material, SessionLocal, TrailerType)
    _purge()
    _set_factor(FACTOR_BEFORE)
    ids = {}
    with SessionLocal() as db:
        cust = Customer(name=f"{MARK} CUSTOMER")
        db.add(cust)
        tt = TrailerType(name=f"{MARK} MEAT HANGER LARGE", is_active=True, configurator_v2=True,
                         default_length=7.8, default_width=2.6, default_height=2.56, default_insulation_foam="4G")
        db.add(tt)
        db.flush()

        def mat(name, price, uom="m²"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price, material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            return m

        # "PU" is the exact name the foam grade keys on (services/insulation_foam.PU_FOAM_MATERIAL_NAMES)
        pu = mat("PU", 4100.0)
        ply6 = mat(f"{MARK} 6MM PF PLYWOOD", 86.58)
        ply4 = mat(f"{MARK} 4MM PF PLYWOOD", 68.79)
        birch = mat(f"{MARK} 6MM BIRCH PLYWOOD", 68.79)
        screws = mat(f"{MARK} ROOF SCREWS", 1.5, uom="each")
        floor = mat(f"{MARK} 12MM PF PLYWOOD", 316.78)

        def row(m, section, formula, sort, waste=0.0):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression=formula,
                               waste_percentage=waste, bom_section=section, sort_order=sort)
            db.add(r)
            db.flush()
            return r

        ids.update({
            "customer": cust.id, "tt": tt.id,
            "roof_ply": row(ply6, "ROOF", "length*width", 10, waste=2.5).id,
            "roof_pu": row(pu, "ROOF", "length*width*0.0943", 11).id,
            "roof_screws": row(screws, "ROOF", "length*4", 12).id,
            "sides_ply": row(ply4, "SIDES", "length*height*2", 20).id,
            "floor_ply": row(floor, "FLOOR", "length*width", 30).id,
            "mat_birch": birch.id, "mat_ply4": ply4.id, "mat_pu": pu.id,
        })
        db.commit()

    # ── the save (Nadie's N10022) ──────────────────────────────────────────
    r = client.post("/api/approve", json=_body_payload(ids), headers=admin)
    assert r.status_code == 200, r.text
    ids["rec"] = r.json()["record_id"]
    ids["qno"] = r.json()["quote_number"]
    ids["saved"] = _stored(ids["rec"])

    # ── Michael's four changes, afterwards ─────────────────────────────────
    draft = {"nextId": 4, "rootIds": ["1"], "itemRules": {}, "nodes": {
        "1": {"id": "1", "type": "category", "label": "ROOF plywood", "parentId": None, "childIds": ["2", "3"],
              "selectionMode": "container", "sourceCategoryKey": "ROOF PLYWOOD"},
        "2": {"id": "2", "type": "category", "label": "4MM PF PLYWOOD", "parentId": "1", "childIds": [],
              "selectionMode": "radio", "sourceCategoryKey": "4MM PF PLYWOOD", "selectionValue": 0},
        "3": {"id": "3", "type": "category", "label": "6MM PF PLYWOOD", "parentId": "1", "childIds": [],
              "selectionMode": "radio", "sourceCategoryKey": "6MM PF PLYWOOD", "selectionValue": 1}}}
    r = client.put(f"/api/configurator/trailers/{ids['tt']}/draft", json={"draft": draft}, headers=admin)
    assert r.status_code == 200, r.text
    ids["draft"] = draft
    with SessionLocal() as db:
        # (a) the ROOF plywood row becomes the 6MM option of a NEW radio group; a 4MM option row is added
        r6 = db.query(BillOfMaterial).filter_by(id=ids["roof_ply"]).first()
        r6.bom_section = "6MM PF PLYWOOD"
        r4 = BillOfMaterial(trailer_type_id=ids["tt"], material_id=ids["mat_ply4"], formula_expression="length*width",
                            waste_percentage=2.5, bom_section="4MM PF PLYWOOD", sort_order=13)
        db.add(r4)
        # (b) the SIDES plywood row is re-pointed at 6MM BIRCH PLYWOOD (same price)
        db.query(BillOfMaterial).filter_by(id=ids["sides_ply"]).first().material_id = ids["mat_birch"]
        # (c) one other row is deleted
        db.query(BillOfMaterial).filter_by(id=ids["roof_screws"]).delete()
        db.flush()
        ids["roof_ply4"] = r4.id
        db.commit()
    # (d) the 4G rate moves
    _set_factor(FACTOR_AFTER)
    yield ids
    _purge()


# ── the client's payloads, as the calculator sends them ──────────────────────
def _frozen_calc(ids, **over) -> dict:
    p = {"frozen_record_id": ids["rec"], "trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5,
         "overrides": {}, "override_reasons": {}, "user_excluded_bom_ids": [], "optional_sections_enabled": [],
         "ratio_value": 0.55, "ratio_label": "55%"}
    p.update(over)
    return p


def _today_calc(ids, *, chosen="3", **over) -> dict:
    """Today's payload as the calculator builds it with the overlay rule: the new radio group's choice decides
    which sibling section is excluded; `chosen` is the draft node id (None = nothing picked)."""
    excluded = {"2": ["6MM PF PLYWOOD"], "3": ["4MM PF PLYWOOD"], None: ["4MM PF PLYWOOD", "6MM PF PLYWOOD"]}[chosen]
    label = {"2": "4MM PF PLYWOOD", "3": "6MM PF PLYWOOD", None: None}[chosen]
    p = {"trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5, "overrides": {},
         "override_reasons": {}, "chassis": {"enabled": False}, "insulation_foam": "4G",
         "excluded_categories": excluded, "user_excluded_bom_ids": [], "optional_sections_enabled": [],
         "ratio_value": 0.55, "ratio_label": "55%", "discount_kind": None, "discount_input": None,
         "new_options": [{"key": "cat:1", "kind": "category_radio", "label": "ROOF plywood: new option",
                          "chosen": chosen, "chosen_label": label, "is_default": chosen == "3",
                          "text": f"ROOF plywood: new option → {label or 'not chosen'}"
                                  + (" (default)" if chosen == "3" else " (your pick)" if chosen else ""),
                          "members": [{"key": "2", "label": "4MM PF PLYWOOD", "is_default": False},
                                      {"key": "3", "label": "6MM PF PLYWOOD", "is_default": True}]}]}
    p.update(over)
    return p


# ── 1. re-open = the saved quote, to the cent ────────────────────────────────
def test_the_saved_copy_is_what_the_record_serves(client, admin, staged):
    ids = staged
    g = client.get(f"/api/calculations/{ids['rec']}", headers=admin).json()
    assert g["frozen_capable"] is True and g["frozen_reason"] is None
    assert g["saved_at"], "every save from v1.62.0 stamps saved_at"
    saved = g["saved_result"]
    # the four template changes left the stored copy alone
    assert _line(saved["items"], "6MM PF PLYWOOD", "ROOF") is not None, "ROOF plywood line, under ROOF, as saved"
    assert _line(saved["items"], f"{MARK} 4MM PF PLYWOOD", "SIDES") is not None, "SIDES line under its saved name"
    assert _line(saved["items"], "ROOF SCREWS") is not None, "the deleted row's line is present"
    assert _line(saved["items"], "PU", "ROOF")["unit_price"] == pytest.approx(5581.0, abs=0.005)


def test_reopen_replays_every_line_and_total_to_the_cent(client, admin, staged):
    ids = staged
    saved = ids["saved"]
    r = client.post("/api/calculate", json=_frozen_calc(ids), headers=admin)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["frozen"]["record_id"] == ids["rec"] and res["frozen"]["library"] == "none"
    by_saved = {it["bom_id"]: it for it in saved["items"]}
    assert len(res["items"]) == len(saved["items"])
    for it in res["items"]:
        s = by_saved[it["bom_id"]]
        assert (it["material"], it["category"]) == (s["material"], s["category"])
        assert it["quantity"] == pytest.approx(s["quantity"], abs=1e-9)
        assert it["unit_price"] == pytest.approx(s["unit_price"], abs=1e-9)
        assert it["line_cost"] == pytest.approx(s["line_cost"], abs=0.005)
    assert res["category_totals"] == pytest.approx(saved["category_totals"], abs=0.005)
    assert res["grand_total"] == pytest.approx(saved["grand_total"], abs=0.005)
    assert res["profit_amount"] == pytest.approx(saved["profit_amount"], abs=0.005)
    assert res["selling_price"] == pytest.approx(saved["selling_price"], abs=0.005)
    assert res["net_total"] == pytest.approx(saved["net_total"], abs=0.005)
    # the specific lines Michael found wrong
    assert _line(res["items"], "6MM PF PLYWOOD", "ROOF")["line_cost"] == pytest.approx(
        _line(saved["items"], "6MM PF PLYWOOD", "ROOF")["line_cost"], abs=0.005)
    assert _line(res["items"], f"{MARK} 4MM PF PLYWOOD", "SIDES") is not None
    assert _line(res["items"], "ROOF SCREWS") is not None
    assert _line(res["items"], "PU", "ROOF")["unit_price"] == pytest.approx(5581.0, abs=0.005)
    # and nothing of today's template leaked in
    assert _line(res["items"], "6MM BIRCH") is None
    assert all(it["category"] not in ("4MM PF PLYWOOD", "6MM PF PLYWOOD") for it in res["items"])


# ── 2. re-open + save, no change = identical ─────────────────────────────────
def test_reopen_and_overwrite_with_no_change_stores_identical_items_and_totals(client, admin, staged):
    ids = staged
    before = _stored(ids["rec"])
    calc = client.post("/api/calculate", json=_frozen_calc(ids), headers=admin).json()
    r = client.post("/api/approve", json={
        **_frozen_calc(ids), "customer_id": ids["customer"], "edit_record_id": ids["rec"],
        "version_action": "overwrite", "screen": _screen(calc), "ui_snapshot": _snapshot()}, headers=admin)
    assert r.status_code == 200, r.text
    after = _stored(ids["rec"])
    for key in ("items", "category_totals", "grand_total", "profit_amount", "selling_price", "net_total",
                "overrides_by_bom", "body_variables", "global_variables", "version"):
        assert after[key] == before[key], key
    assert after["saved_at"] >= before["saved_at"]
    assert after["input_state"]["insulation_foam"] == "4G"
    ids["saved"] = after


# ── 3. a dimension change in frozen mode ─────────────────────────────────────
def test_a_size_change_recomputes_quantities_at_saved_prices(client, admin, staged):
    ids = staged
    saved = ids["saved"]
    dims = {**DIMS, "length": 8.3}
    r = client.post("/api/calculate", json=_frozen_calc(ids, dimensions=dims), headers=admin)
    assert r.status_code == 200, r.text
    res = r.json()
    by_saved = {it["bom_id"]: it for it in saved["items"]}
    moved = 0
    for it in res["items"]:
        s = by_saved[it["bom_id"]]
        assert it["unit_price"] == pytest.approx(s["unit_price"], abs=1e-9), "unit prices stay as saved"
        assert it["formula"] == s["formula"], "each line's SAVED formula"
        if "length" in s["formula"]:
            # stored quantities are rounded to 4 dp, so the scaled saved figure can be off by half a unit of that
            assert it["quantity"] == pytest.approx(s["quantity"] * 8.3 / 7.8, abs=0.0006)
            moved += 1
    assert moved >= 4
    screws = _line(res["items"], "ROOF SCREWS")
    assert screws["quantity"] == pytest.approx(8.3 * 4, abs=1e-6), "the deleted row recomputes from its saved formula"
    assert res["grand_total"] > saved["grand_total"]


# ── 4. the comparison ────────────────────────────────────────────────────────
def test_the_reprice_preview_lists_the_four_changes_at_the_fixtures_numbers(client, admin, staged):
    ids = staged
    r = client.post(f"/api/calculations/{ids['rec']}/reprice-preview", json=_today_calc(ids), headers=admin)
    assert r.status_code == 200, r.text
    c = r.json()["comparison"]
    kinds = {(ln["kind"], ln["material"]): ln for ln in c["lines"]}
    # the new ROOF plywood option with its default
    assert c["new_options"][0]["text"] == "ROOF plywood: new option → 6MM PF PLYWOOD (default)"
    assert c["blocked"] == []
    # the ROOF plywood line now sits in the option's own section (same row, same money)
    moved = kinds[("moved", f"{MARK} 6MM PF PLYWOOD")]
    assert moved["category"] == "ROOF" and moved["today_category"] == "6MM PF PLYWOOD"
    assert moved["delta_cost"] == pytest.approx(0.0, abs=0.005)
    # the SIDES material change at the same price
    ren = kinds[("renamed", f"{MARK} 4MM PF PLYWOOD")]
    assert ren["today_material"] == f"{MARK} 6MM BIRCH PLYWOOD" and ren["delta_cost"] == pytest.approx(0.0, abs=0.005)
    # the deleted row as "removed from template"
    gone = kinds[("removed_from_template", f"{MARK} ROOF SCREWS")]
    assert gone["today"] is None and gone["delta_cost"] < 0
    # the PU unit price going from 5,581 to 5,400
    pu = kinds[("price", "PU")]
    assert pu["saved"]["unit_price"] == pytest.approx(5581.0, abs=0.005)
    assert pu["today"]["unit_price"] == pytest.approx(5400.0, abs=0.005)
    # the difference per section and in total (cost and selling)
    roof = next(s for s in c["sections"] if s["category"] == "ROOF")
    assert roof["delta"] < 0
    t = c["totals"]
    assert t["delta_cost"] == pytest.approx(t["today"]["grand_total"] - t["saved"]["grand_total"], abs=0.005)
    assert t["delta_selling"] == pytest.approx(t["today"]["selling_price"] - t["saved"]["selling_price"], abs=0.005)
    assert t["delta_cost"] < 0
    assert c["counts"]["removed_from_template"] == 1 and c["counts"]["price"] >= 1 and c["counts"]["renamed"] == 1


def test_apply_is_blocked_while_a_new_option_has_no_choice(client, admin, staged):
    ids = staged
    r = client.post(f"/api/calculations/{ids['rec']}/reprice-preview", json=_today_calc(ids, chosen=None), headers=admin)
    assert r.status_code == 200, r.text
    c = r.json()["comparison"]
    assert c["blocked"] == ["ROOF plywood: new option: pick one before Apply"]
    # and with nothing picked the re-cost drops BOTH plywood options — exactly what Michael saw
    assert _line([ln for ln in c["lines"] if ln["kind"] == "added"], "PLYWOOD") is None
    assert ("removed", f"{MARK} 6MM PF PLYWOOD") in {(ln["kind"], ln["material"]) for ln in c["lines"]}


# ── 5. Apply → a new revision only; the original untouched ───────────────────
def test_apply_saves_a_new_revision_only_and_the_original_is_untouched(client, admin, staged):
    ids = staged
    original_raw = _raw_result_json(ids["rec"])
    today = client.post("/api/calculate", json={**_today_calc(ids), "repriced_from_record_id": ids["rec"]}, headers=admin).json()
    assert today["frozen"] is None if "frozen" in today else True
    body = {**_today_calc(ids), "customer_id": ids["customer"], "repriced_from_record_id": ids["rec"],
            "edit_record_id": ids["rec"], "screen": _screen(today), "ui_snapshot": _snapshot(
                draft_category_radio={"1": "6MM PF PLYWOOD"})}
    # Overwrite is refused for a re-priced quote
    r = client.post("/api/approve", json={**body, "version_action": "overwrite"}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "repriced_new_revision_only"
    assert _raw_result_json(ids["rec"]) == original_raw
    # a new revision, reusing the quote number
    r = client.post("/api/approve", json={**body, "version_action": "new_version", "next_version": 2,
                                          "reuse_quote_number": True}, headers=admin)
    assert r.status_code == 200, r.text
    new_id = r.json()["record_id"]
    assert new_id != ids["rec"] and r.json()["version"] == 2 and r.json()["quote_number"] == ids["qno"]
    assert _raw_result_json(ids["rec"]) == original_raw, "the revision the customer received stays exactly as sent"
    rev = _stored(new_id)
    assert rev["repriced"]["from_record_id"] == ids["rec"] and rev["repriced"]["repriced_at"]
    assert rev["repriced"]["comparison"]["new_options"][0]["text"].endswith("6MM PF PLYWOOD (default)")
    assert {ln["kind"] for ln in rev["repriced"]["comparison"]["lines"]} >= {"removed_from_template", "price", "renamed"}
    # the re-priced revision carries the new option at its default, today's PU rate and the re-pointed SIDES line
    assert _line(rev["items"], f"{MARK} 6MM PF PLYWOOD", "6MM PF PLYWOOD") is not None
    assert _line(rev["items"], "PU")["unit_price"] == pytest.approx(5400.0, abs=0.005)
    assert _line(rev["items"], f"{MARK} 6MM BIRCH PLYWOOD", "SIDES") is not None
    assert _line(rev["items"], "ROOF SCREWS") is None
    ids["rev2"] = new_id


# ── 6–7. the refusals ────────────────────────────────────────────────────────
def test_an_overwrite_without_saved_prices_is_refused(client, admin, staged):
    ids = staged
    before = _raw_result_json(ids["rec"])
    calc = client.post("/api/calculate", json=_today_calc(ids), headers=admin).json()
    r = client.post("/api/approve", json={**_today_calc(ids), "customer_id": ids["customer"],
                                          "edit_record_id": ids["rec"], "version_action": "overwrite",
                                          "screen": _screen(calc)}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "overwrite_needs_saved_prices"
    assert _raw_result_json(ids["rec"]) == before


def test_a_save_that_does_not_equal_the_screen_is_refused_and_nothing_is_saved(client, admin, staged):
    ids = staged
    before = _raw_result_json(ids["rec"])
    calc = client.post("/api/calculate", json=_frozen_calc(ids), headers=admin).json()
    wrong = {"grand_total": calc["grand_total"] + 1.0, "net_total": calc["net_total"]}
    r = client.post("/api/approve", json={**_frozen_calc(ids), "customer_id": ids["customer"],
                                          "edit_record_id": ids["rec"], "version_action": "overwrite",
                                          "screen": wrong, "ui_snapshot": _snapshot()}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "frozen_mismatch"
    assert _raw_result_json(ids["rec"]) == before
    r = client.post("/api/approve", json={**_frozen_calc(ids), "customer_id": ids["customer"],
                                          "edit_record_id": ids["rec"], "version_action": "overwrite",
                                          "ui_snapshot": _snapshot()}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "screen_missing"
    assert _raw_result_json(ids["rec"]) == before


# ── 8. the library guard ─────────────────────────────────────────────────────
def test_a_size_change_needs_the_stored_library_expressions(client, admin, staged):
    ids = staged
    from app.database import BillOfMaterial, Formula, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        db.add(Formula(name=f"{MARK.lower()}_half_length", expression="length*0.5", is_active=True))
        tt = TrailerType(name=f"{MARK} LIB BODY", is_active=True, default_length=6, default_width=2.4, default_height=2.4)
        db.add(tt)
        db.flush()
        m = Material(name=f"{MARK} LIB MATERIAL", unit_of_measure="m", price_per_unit=10.0, material_code=MARK, is_active=True)
        db.add(m)
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression="{" + f"{MARK.lower()}_half_length" + "}*width",
                              waste_percentage=0, bom_section="FRONT", sort_order=1))
        db.commit()
        lib_tt = tt.id
    from app.services import invalidate_formulas
    invalidate_formulas()
    dims = {**DIMS, "length": 6.0}
    r = client.post("/api/approve", json=_body_payload(ids, trailer_type_id=lib_tt, dimensions=dims,
                                                       insulation_foam="32D", customer_id=None), headers=admin)
    assert r.status_code == 200, r.text
    rid = r.json()["record_id"]
    data = _stored(rid)
    assert data["formula_library"] == {f"{MARK.lower()}_half_length": "length*0.5"}, "stored on every save"
    frozen = {"frozen_record_id": rid, "trailer_type_id": lib_tt, "profit_margin": 5, "overrides": {}}
    # with the expressions stored: a size change prices at saved prices
    r = client.post("/api/calculate", json={**frozen, "dimensions": {**dims, "length": 7.0}}, headers=admin)
    assert r.status_code == 200 and r.json()["frozen"]["library"] == "stored"
    assert r.json()["items"][0]["quantity"] == pytest.approx(7.0 * 0.5 * DIMS["width"], abs=1e-6)
    # a record saved before v1.62.0 holds only the VALUES at its size
    stripped = copy.deepcopy(data)
    stripped.pop("formula_library")
    stripped.pop("saved_at", None)
    _rewrite_result_json(rid, stripped)
    r = client.post("/api/calculate", json={**frozen, "dimensions": dims}, headers=admin)
    assert r.status_code == 200 and r.json()["frozen"]["library"] == "values"
    assert r.json()["grand_total"] == pytest.approx(data["grand_total"], abs=0.005)
    r = client.post("/api/calculate", json={**frozen, "dimensions": {**dims, "length": 7.0}}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "frozen_library_missing"
    assert "Update to today" in r.json()["detail"]["message"]
    g = client.get(f"/api/calculations/{rid}", headers=admin).json()
    assert g["frozen_library"] == "values" and g["saved_at"] is None
    ids.update({"lib_rec": rid, "lib_tt": lib_tt, "lib_dims": dims})   # the refusal tests below meet this gate again


# ── 9. repairs ───────────────────────────────────────────────────────────────
def test_a_frozen_repair_keeps_its_stock_prices_and_a_deleted_material_still_saves(client, admin, staged):
    ids = staged
    from app.database import Material, SessionLocal
    with SessionLocal() as db:
        m = Material(name=f"{MARK} REPAIR HINGE", unit_of_measure="each", price_per_unit=120.0, material_code=MARK, is_active=True)
        db.add(m)
        db.commit()
        mid = m.id
    lines = [{"kind": "stock", "key": "s1", "material_id": mid, "qty": 2, "notes": None, "origin": None, "excluded": False},
             {"kind": "free_hand", "key": "f1", "description": "Labour", "qty": 1, "unit": "each", "unit_price": 500,
              "notes": None, "material_id": None, "bom_section_id": None, "category": None, "origin": None, "excluded": False}]
    base = {"is_repair": True, "trailer_type_id": None, "repair_type": f"{MARK} door repair", "repair_scope": None,
            "repair_lines": lines, "profit_margin": 5, "ratio_value": 0.55, "ratio_label": "55%",
            "discount_kind": None, "discount_input": None, "repair_vehicle": None, "dimensions": {},
            "customer_id": ids["customer"]}
    r = client.post("/api/approve", json=base, headers=admin)
    assert r.status_code == 200, r.text
    rid = r.json()["record_id"]
    saved = _stored(rid)
    assert _line(saved["items"], "REPAIR HINGE")["unit_price"] == pytest.approx(120.0)
    assert saved["saved_at"]
    # the catalogue moves, then the material goes
    with SessionLocal() as db:
        db.query(Material).filter_by(id=mid).first().price_per_unit = 150.0
        db.commit()
    r = client.post("/api/calculate", json={**base, "frozen_record_id": rid}, headers=admin)
    assert r.status_code == 200 and _line(r.json()["items"], "REPAIR HINGE")["unit_price"] == pytest.approx(120.0)
    assert r.json()["frozen"]["record_id"] == rid
    r = client.post("/api/calculate", json=base, headers=admin)
    assert _line(r.json()["items"], "REPAIR HINGE")["unit_price"] == pytest.approx(150.0), "a plain calc re-prices"
    pv = client.post(f"/api/calculations/{rid}/reprice-preview", json=base, headers=admin).json()["comparison"]
    assert ("price", f"{MARK} REPAIR HINGE") in {(ln["kind"], ln["material"]) for ln in pv["lines"]}
    with SessionLocal() as db:
        db.query(Material).filter_by(id=mid).first().is_active = False
        db.commit()
    r = client.post("/api/calculate", json=base, headers=admin)
    assert r.status_code == 422, "today's catalogue cannot price a deleted material"
    calc = client.post("/api/calculate", json={**base, "frozen_record_id": rid}, headers=admin)
    assert calc.status_code == 200, calc.text
    assert _line(calc.json()["items"], "REPAIR HINGE")["unit_price"] == pytest.approx(120.0)
    r = client.post("/api/approve", json={**base, "frozen_record_id": rid, "edit_record_id": rid,
                                          "version_action": "overwrite", "screen": _screen(calc.json())}, headers=admin)
    assert r.status_code == 200, r.text
    assert _line(_stored(rid)["items"], "REPAIR HINGE")["unit_price"] == pytest.approx(120.0)
    pv = client.post(f"/api/calculations/{rid}/reprice-preview", json=base, headers=admin).json()["comparison"]
    assert pv["kept_saved_price"] == [f"{MARK} REPAIR HINGE"]


# ── 10–11. what every save stores; what GET reports ──────────────────────────
def test_every_save_stamps_saved_at_and_the_three_keys(client, admin, staged):
    ids = staged
    data = _stored(ids["rec"])
    assert data["saved_at"] and data["pu_foam_4g_factor"] == pytest.approx(FACTOR_BEFORE)
    assert isinstance(data["formula_library"], dict)
    rev = _stored(ids["rev2"])
    assert rev["saved_at"] and rev["pu_foam_4g_factor"] == pytest.approx(FACTOR_AFTER)


def test_get_reports_a_record_that_cannot_be_frozen(client, admin, staged):
    ids = staged
    data = _stored(ids["rev2"])
    broken = copy.deepcopy(data)
    for it in broken["items"]:
        it.pop("formula", None)
    _rewrite_result_json(ids["rev2"], broken)
    g = client.get(f"/api/calculations/{ids['rev2']}", headers=admin).json()
    assert g["frozen_capable"] is False and "formula" in g["frozen_reason"]
    r = client.post("/api/calculate", json={**_frozen_calc(ids), "frozen_record_id": ids["rev2"]}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "frozen_not_capable"
    _rewrite_result_json(ids["rev2"], data)
    assert client.get(f"/api/calculations/{ids['rev2']}", headers=admin).json()["frozen_capable"] is True


# ── 12. the comparison, as a pure function ───────────────────────────────────
def test_compare_tells_a_deleted_row_from_a_line_todays_options_leave_out():
    from app.services.frozen_quote import compare
    saved = {"items": [{"bom_id": 1, "material": "A", "category": "X", "quantity": 1, "unit_price": 10, "line_cost": 10},
                       {"bom_id": 2, "material": "B", "category": "X", "quantity": 1, "unit_price": 10, "line_cost": 10},
                       {"bom_id": 3, "material": "C", "category": "Y", "quantity": 2, "unit_price": 5, "line_cost": 10}],
             "category_totals": {"X": 20, "Y": 10}, "grand_total": 30, "profit_amount": 1.5, "selling_price": 57.27}
    today = {"items": [{"bom_id": 1, "material": "A", "category": "X", "quantity": 1, "unit_price": 12, "line_cost": 12},
                       {"bom_id": 3, "material": "C", "category": "Y", "quantity": 3, "unit_price": 5, "line_cost": 15},
                       {"bom_id": 4, "material": "D", "category": "Y", "quantity": 1, "unit_price": 1, "line_cost": 1}],
             "category_totals": {"X": 12, "Y": 16}, "grand_total": 28, "profit_amount": 1.4, "selling_price": 53.45}
    c = compare(saved, today, today_bom_ids={1, 3, 4})
    kinds = {ln["bom_id"]: ln["kind"] for ln in c["lines"]}
    assert kinds == {1: "price", 2: "removed_from_template", 3: "qty", 4: "added"}
    c2 = compare(saved, today, today_bom_ids={1, 2, 3, 4})
    assert {ln["bom_id"]: ln["kind"] for ln in c2["lines"]}[2] == "removed"
    assert c["totals"]["delta_cost"] == pytest.approx(-2.0)
    assert c["counts"] == {"removed": 1, "removed_from_template": 1, "added": 1, "qty": 1, "price": 1, "renamed": 0, "unchanged": 0}
    assert [s["category"] for s in c["sections"]] == ["X", "Y"]


# ── 13. the race, by mechanism, pinned in the served file ────────────────────
def test_calculator_js_keeps_the_race_guards():
    src = CALC_JS.read_text(encoding="utf-8")
    sched = src[src.index("function scheduleCalc()"):src.index("function triggerLiveRecalc()")]
    assert "if (_calcSuspended) return;" in sched, "scheduleCalc must refuse while a saved quote is being opened"
    assert src.count("if (gen !== _calcGen) return;") >= 4, "runCalc / runRepairCalc drop a stale response"
    assert "++_calcGen;\n  clearTimeout(calcTimer);" in src.replace("\r\n", "\n"), "a save takes a generation"
    edit = src[src.index("async function editCalculation("):src.index("function showEditBanner(")]
    assert "_calcSuspended = true;" in edit and "_frozenDriftCheck();" in edit
    assert "await runCalc();\n    verifyEditBalance(saved);" not in edit.replace("\r\n", "\n"), "no calculation on open"
    assert "if (_userTouchedBody) return false;" in src, "the init restore stands down once the user changed the body"


# ── RT8_RULING_2: plain words for every refusal, nothing saved, and the negative control ─────────────────────────
PLAIN = {   # the ruling's table, verbatim — pinned here independently of the module's constant
    "overwrite_needs_saved_prices": "This page is out of date. Reload it (Ctrl+F5) and save again. Your quote has not been changed.",
    "frozen_mismatch": "The figures changed while saving, so nothing was saved. Reload the quote and try again.",
    "screen_missing": "The figures changed while saving, so nothing was saved. Reload the quote and try again.",
    "repriced_new_revision_only": "A quote moved to today's prices saves as a new revision, so the one the customer has stays as sent.",
    "frozen_library_missing": "This quote was saved before size changes could keep its prices. To change the size, use Update to today's prices.",
}


def _records() -> int:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return db.query(CalculationRecord).count()


def _meet(client, admin, ids, code):
    """One request that meets the gate named by `code`, the way the calculator (or a stale tab) would send it."""
    base = {"customer_id": ids["customer"], "edit_record_id": ids["rec"], "version_action": "overwrite"}
    if code == "overwrite_needs_saved_prices":            # a stale tab: today's payload, no frozen_record_id
        calc = client.post("/api/calculate", json=_today_calc(ids), headers=admin).json()
        return client.post("/api/approve", json={**_today_calc(ids), **base, "screen": _screen(calc)}, headers=admin)
    if code == "frozen_mismatch":                         # the screen no longer equals what the saved prices give
        calc = client.post("/api/calculate", json=_frozen_calc(ids), headers=admin).json()
        return client.post("/api/approve", json={**_frozen_calc(ids), **base, "ui_snapshot": _snapshot(),
                                                 "screen": {"grand_total": calc["grand_total"] + 1.0, "net_total": calc["net_total"]}}, headers=admin)
    if code == "screen_missing":                          # the figures never reached the server
        return client.post("/api/approve", json={**_frozen_calc(ids), **base, "ui_snapshot": _snapshot()}, headers=admin)
    if code == "repriced_new_revision_only":              # Overwrite after Update to today's prices
        today = client.post("/api/calculate", json={**_today_calc(ids), "repriced_from_record_id": ids["rec"]}, headers=admin).json()
        return client.post("/api/approve", json={**_today_calc(ids), **base, "repriced_from_record_id": ids["rec"],
                                                 "screen": _screen(today), "ui_snapshot": _snapshot(draft_category_radio={"1": "6MM PF PLYWOOD"})}, headers=admin)
    if code == "frozen_library_missing":                  # a size change on a record saved before the expressions were kept
        return client.post("/api/calculate", json={"frozen_record_id": ids["lib_rec"], "trailer_type_id": ids["lib_tt"],
                                                   "profit_margin": 5, "overrides": {}, "dimensions": {**ids["lib_dims"], "length": 7.0}}, headers=admin)
    raise AssertionError(code)


@pytest.mark.parametrize("code", list(PLAIN))
def test_the_refusal_reads_in_plain_words_and_saves_nothing(client, admin, staged, code):
    """RT8_RULING_2 — no raw 409 reaches a user: each refusal carries the ruling's sentence, and nothing is saved."""
    from app.services import frozen_quote
    ids = staged
    rid = ids["lib_rec"] if code == "frozen_library_missing" else ids["rec"]
    before, n = _raw_result_json(rid), _records()
    r = _meet(client, admin, ids, code)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == code and d["message"] == PLAIN[code] == frozen_quote.REFUSALS[code]
    assert code not in d["message"] and "409" not in d["message"]
    if code == "frozen_mismatch":
        assert d["label"] and d["shown"] == pytest.approx(d["saved"] + 1.0, abs=0.005)   # the figures ride for the audit
    assert _raw_result_json(rid) == before and _records() == n


def test_without_the_mapping_the_raw_code_shows(client, admin, staged, monkeypatch):
    """The negative control: with the table gone, the sentence IS the code — on a gate and on a FrozenError alike."""
    from app.services import frozen_quote
    monkeypatch.setattr(frozen_quote, "REFUSALS", {})
    for code in ("overwrite_needs_saved_prices", "frozen_library_missing"):
        d = _meet(client, admin, staged, code).json()["detail"]
        assert d["code"] == code and d["message"] == code, d
