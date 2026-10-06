"""RT6 — Burt's insulation rules enforced, in a real browser, on the light MES skin (RT6_DISPATCH; RT6_RULING_1 / 1a).

  1. Re-open -> warning -> Remove -> approve: a FREEZER quote saved with EPS on the SIDES (before the rule) re-opens
     with the red warning under the note and a Remove; saving it is refused (the 409's sentence); Remove clears it
     (SIDES goes to PU, the thickness carried); the overwrite then saves, and the database reads SIDES PU.
  2. The panels: PU on a chiller is greyed out, with the rule as its tooltip, in all three renderers (the Settings
     draft, the flat panel, the configurator tree) — and the INSULATION FOAM picker is hidden (greyed = not offered).
  3. "Switch ALL insulation" on a freezer skips the panels the rule forbids, and says so.
  4. Paste from Excel: the PU row is refused (red, "refused — <the rule>"); the other rows apply.
  5. RULING_1a: a soft-deleted breaching costing, restored, re-opens with the warning and Remove.
  6. RULING_1 Q8: a forbidden insulation on the door the quote does not use is named "— not used on this quote".
  7. The TEST SERVER bar and the "[TEST]" tab title (this side port is not prod).
Screenshots are element shots of the configuration card (no customer list). Marker JRT6 only — created and purged
here (setup AND teardown). Base-aware: admin_session(base=live_server), so it runs against MES_BASE (a side port).
"""
from __future__ import annotations

import json
import uuid

import pytest
from playwright.sync_api import Page, expect

from _common import SCREENSHOT_ROOT, admin_session  # noqa: E402  (sys.path set in conftest)

T = 20_000
JOURNEY = "rt6_rules"
MARK = "JRT6"
PANELS = ("FRONT", "SIDES", "ROOF", "FLOOR", "DRD", "SRD")
NOTE_C = "No PU insulation for Chillers"
NOTE_F = "Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors"


def _rule(allowed):
    return json.dumps({"allowed": {p: allowed[p] for p in PANELS}}, separators=(",", ":"))


CHILLER = _rule({p: ["EPS"] for p in PANELS})
FREEZER = _rule({"FRONT": ["PU"], "SIDES": ["PU"], "ROOF": ["EPS", "PU"], "FLOOR": ["EPS", "PU"], "DRD": ["PU"],
                 "SRD": ["PU"]})


def shot(page: Page, name: str) -> None:
    out = SCREENSHOT_ROOT / JOURNEY
    out.mkdir(parents=True, exist_ok=True)
    page.locator(".calc-panel--config").first.screenshot(path=str(out / f"{name}.png"))


def _purge(db) -> None:
    from sqlalchemy import text
    tt = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    for sql in (f"DELETE FROM icb_costings.calculations WHERE trailer_type_id IN {tt}",
                f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt}",
                f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt}",
                "DELETE FROM icb_costings.trailer_types WHERE name LIKE :m",
                "DELETE FROM icb_costings.trailer_groups WHERE name LIKE :m",
                "DELETE FROM icb_costings.materials WHERE material_code = :c",
                "DELETE FROM icb_costings.customers WHERE name LIKE :m"):
        db.execute(text(sql), {"m": f"{MARK}%", "c": MARK})
    db.commit()


def _flag(nid, name, parent, value, bind_id) -> dict:
    return {"id": nid, "type": "flag", "label": name, "parentId": parent, "childIds": [], "flagMode": "radio",
            "flagValue": value, "flagBindingName": name, "flagBindingId": bind_id}


@pytest.fixture(scope="module")
def staged():
    """Families CHILL (rule CHILLER, note) and FREEZE (rule FREEZER, note). Bodies, each with the 12 insulation masters
    (panel x EPS / PU) + their cost lines and a DOOR TYPE pair (DRD / SRD):
      chill_draft  v2, a Settings draft that still OFFERS PU on FRONT and SIDES (the Settings-draft renderer)
      chill_flat   not v2 (the flat renderer)
      chill_tree   v2 with no draft (the configurator-tree renderer)
      freeze       v2, a draft offering only PU on FRONT / SIDES (as prod since Michael's removals)
      freeze_flat  not v2 ("Switch ALL insulation")"""
    from app.database import (BillOfMaterial, ConfiguratorDraft, Customer, Material, SessionLocal, TrailerGroup,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)
        fam = {}
        for key, note, rule, colour, order in (("chill", NOTE_C, CHILLER, "#168ED9", 9701),
                                               ("freeze", NOTE_F, FREEZER, "#4263EB", 9702)):
            g = TrailerGroup(name=f"{MARK} {key.upper()} FAM", colour=colour, sort_order=order, rule_note=note,
                             insulation_rule=rule)
            db.add(g)
            db.flush()
            fam[key] = g.id
        customer = Customer(name=f"{MARK} CUSTOMER")
        db.add(customer)

        def mat(name, price=0.0, uom="each"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price, material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            return m
        line = {"EPS": mat("EPS", 120.0, "m2"), "PU": mat("PU", 380.0, "m2")}
        master = {(p, i): mat(f"{p} {i}") for p in PANELS for i in ("EPS", "PU")}
        door = {d: mat(d) for d in ("DRD", "SRD")}

        def body(suffix, key, v2):
            t = TrailerType(name=f"{MARK} {suffix}", is_active=True, configurator_v2=v2, group_id=fam[key],
                            default_length=6.0, default_width=2.4, default_height=2.4, default_insulation_foam="32D")
            db.add(t)
            db.flush()
            ids = {}
            for p in PANELS:
                for i in ("EPS", "PU"):
                    on = (i == "EPS") if key == "chill" else (i == "PU")
                    r = BillOfMaterial(trailer_type_id=t.id, material_id=master[(p, i)].id, formula_expression="1",
                                       is_body_option=True, body_option_group=p, body_option_subgroup="INSULATION",
                                       selection_mode="single", selection_group="INSULATION", body_option_default=on,
                                       variable_value=0.06 if on else 0.0, bom_section="BODY OPTIONS")
                    db.add(r)
                    db.flush()
                    ids[(p, i)] = r.id
                    db.add(BillOfMaterial(trailer_type_id=t.id, material_id=line[i].id, waste_percentage=0.0,
                                          formula_expression=f"length*height*{{{p} {i}}}", bom_section=p,
                                          bom_conditions=json.dumps([{"option": f"{p} {i}", "equals": "Y",
                                                                      "option_id": r.id}])))
            for d in ("DRD", "SRD"):
                r = BillOfMaterial(trailer_type_id=t.id, material_id=door[d].id, formula_expression="1",
                                   is_body_option=True, body_option_group="DOOR TYPE", body_option_subgroup="DOOR TYPE",
                                   selection_mode="single", selection_group="DOOR TYPE", body_option_default=(d == "DRD"),
                                   bom_section="BODY OPTIONS")
                db.add(r)
                db.flush()
                ids[d] = r.id
            return t.id, ids

        ids = {"fam": fam, "customer": None}
        for name, key, v2 in (("CHILL DRAFT", "chill", True), ("CHILL FLAT", "chill", False),
                              ("CHILL TREE", "chill", True), ("FREEZE", "freeze", True),
                              ("FREEZE FLAT", "freeze", False)):
            k = name.lower().replace(" ", "_")
            ids[k], ids[k + "_m"] = body(name, key, v2)
        db.flush()
        ids["customer"] = customer.id

        def draft(m, offer_pu, eps_on):
            nodes, roots, n = {}, [], 1
            for p in ("FRONT", "SIDES"):
                cid = str(n)
                kids = [str(n + 1)] + ([str(n + 2)] if offer_pu else [])
                nodes[cid] = {"id": cid, "type": "category", "label": p, "sourceCategoryKey": p, "parentId": None,
                              "childIds": kids}
                nodes[str(n + 1)] = _flag(str(n + 1), f"{p} EPS", cid, eps_on, m[(p, "EPS")])
                if offer_pu:
                    nodes[str(n + 2)] = _flag(str(n + 2), f"{p} PU", cid, 1 - eps_on, m[(p, "PU")])
                roots.append(cid)
                n += 3
            return {"nextId": n, "rootIds": roots, "itemRules": {}, "nodes": nodes}
        db.add(ConfiguratorDraft(trailer_type_id=ids["chill_draft"],
                                 payload=json.dumps(draft(ids["chill_draft_m"], True, 1))))
        fz = draft(ids["freeze_m"], True, 0)
        for nid, nd in list(fz["nodes"].items()):          # prod's freezer draft: EPS removed on FRONT / SIDES
            if nd.get("type") == "flag" and nd["label"].endswith(" EPS"):
                fz["nodes"][nd["parentId"]]["childIds"].remove(nid)
                del fz["nodes"][nid]
        db.add(ConfiguratorDraft(trailer_type_id=ids["freeze"], payload=json.dumps(fz)))
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _sel(m, picks, default):
    out = {}
    for p in PANELS:
        for i in ("EPS", "PU"):
            out[str(m[(p, i)])] = picks.get(p, default) == i
    out[str(m["DRD"])], out[str(m["SRD"])] = True, False
    return out


def _saved(ids, body, picks, default, deleted=False) -> int:
    """A costing saved BEFORE the rule (inserted as the app stored it then), with its UI snapshot."""
    from datetime import datetime, timezone
    from app.database import CalculationRecord, SessionLocal
    m = ids[body + "_m"]
    s = _sel(m, picks, default)
    bv = {f"{p} {i}": (0.06 if picks.get(p, default) == i else 0.0) for p in PANELS for i in ("EPS", "PU")}
    with SessionLocal() as db:
        rec = CalculationRecord(trailer_type_id=ids[body], status="pending", customer_id=ids["customer"],
                                quote_number=f"{MARK}{uuid.uuid4().hex[:5].upper()}", dimensions_json=json.dumps({
                                    "length": 6.0, "width": 2.4, "height": 2.4}),
                                result_json=json.dumps({"input_state": {
                                    "body_option_selections": s, "profit_margin": 0,
                                    "ui_snapshot": {"body_option_selections": s, "drd_srd": {"DRD": True}}},
                                    "body_variables": bv, "items": [], "grand_total": 1.0, "version": 1}),
                                deleted_at=datetime.now(timezone.utc) if deleted else None)
        db.add(rec)
        db.commit()
        return rec.id


def _calc(page: Page, action, tid: int, want=None):
    def ok(resp) -> bool:
        if resp.request.method != "POST" or not resp.url.split("?")[0].endswith("/api/calculate"):
            return False
        try:
            req = resp.request.post_data_json or {}
        except Exception:
            return False
        return req.get("trailer_type_id") == tid and (want is None or want(req))
    with page.expect_response(ok, timeout=30_000) as r:
        action()
    return r.value


def _open_calculator(page: Page) -> None:
    page.goto("/health/version")
    page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (_) {} }")
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)


def _breaches(page: Page):
    return page.locator("#body-rule-breaches")


def _db_selection(rec_id) -> dict:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return json.loads(db.get(CalculationRecord, rec_id).result_json)["input_state"]["body_option_selections"]


# ── 1 ───────────────────────────────────────────────────────────────────────
def test_reopen_warns_remove_clears_it_and_the_overwrite_then_saves(page: Page, live_server: str, staged) -> None:
    ids = staged
    m = ids["freeze_m"]
    rec = _saved(ids, "freeze", {"SIDES": "EPS"}, "PU")
    admin_session(page, base=live_server)
    _open_calculator(page)
    resp = _calc(page, lambda: page.goto(f"/mes/calculator?stay=1&edit={rec}"), ids["freeze"])
    assert [(b["panel"], b["insulation"]) for b in resp.json()["rule_breaches"]] == [("SIDES", "EPS")]
    expect(_breaches(page)).to_be_visible(timeout=T)
    expect(_breaches(page)).to_contain_text("This quote breaks the rule above (1). It cannot be saved until each is removed:")
    expect(_breaches(page)).to_contain_text("✖ EPS insulation on the SIDES")
    expect(page.locator("#body-rule-note")).to_contain_text(NOTE_F)
    shot(page, "01-reopened-freezer-eps-sides-warning")

    # saving it as it is: refused, with the server's sentence
    overwrite = page.locator("#modal-edit-save button[onclick*=\"editSaveAction('overwrite')\"]")
    page.click("#approve-btn")
    with page.expect_response(lambda r: r.url.endswith("/api/approve") and r.request.method == "POST", timeout=T) as ap:
        overwrite.click()
    assert ap.value.status == 409
    expect(page.locator("#toast-container .toast-error .toast-msg").last).to_contain_text(
        "EPS insulation is not allowed on the SIDES for this body's family. Remove it, then save again.", timeout=T)
    assert _db_selection(rec)[str(m[("SIDES", "EPS")])] is True                 # nothing written

    # Remove: SIDES goes to PU, the thickness carried, no breach left
    sent = _calc(page, lambda: page.click("#body-rule-breaches .rb-remove"), ids["freeze"],
                 lambda req: (req.get("body_option_selections") or {}).get(str(m[("SIDES", "PU")])) is True)
    req = sent.request.post_data_json
    assert req["body_option_selections"][str(m[("SIDES", "EPS")])] is False
    assert (req.get("body_variable_overrides") or {}).get("SIDES PU") == pytest.approx(0.06)
    assert sent.json()["rule_breaches"] == []
    expect(_breaches(page)).to_be_hidden(timeout=T)
    assert _db_selection(rec)[str(m[("SIDES", "EPS")])] is True                 # still not written
    shot(page, "02-after-remove")

    # re-approve: the overwrite saves, and the database reads SIDES PU
    page.click("#approve-btn")
    with page.expect_response(lambda r: r.url.endswith("/api/approve") and r.request.method == "POST", timeout=T) as ap:
        overwrite.click()
    assert ap.value.status == 200, ap.value.text()
    saved = _db_selection(rec)
    assert saved[str(m[("SIDES", "PU")])] is True and saved[str(m[("SIDES", "EPS")])] is False


# ── 2 ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("body,renderer", [("chill_draft", "draft"), ("chill_flat", "flat"), ("chill_tree", "tree")])
def test_pu_is_greyed_in_every_renderer_and_the_foam_picker_hides(page: Page, live_server: str, staged, body,
                                                                   renderer) -> None:
    ids = staged
    m = ids[body + "_m"]
    admin_session(page, base=live_server)
    _open_calculator(page)
    resp = _calc(page, lambda: page.select_option("#trailer-select", str(ids[body])), ids[body])
    assert resp.json()["rule_breaches"] == []
    if renderer == "tree":            # the tree opens its groups collapsed and re-renders ITSELF on expand
        for _ in range(12):
            hdr = page.locator("#body-options-list .bot-grp-hdr", has=page.locator("span", has_text="▶"))
            if hdr.count() == 0:
                break
            hdr.first.click()
            page.wait_for_timeout(150)
    greyed = page.evaluate("""() => [...document.querySelectorAll('#body-options-list .rule-forbidden')]
        .map(e => ({t: e.textContent.trim().slice(0, 30), title: e.title}))""")
    # the flat panel draws a door's insulation only for the quoted door (DRD here): SRD is not drawn at all
    expected_pu = {"draft": ("FRONT", "SIDES"), "flat": ("FRONT", "SIDES", "ROOF", "FLOOR", "DRD"),
                   "tree": PANELS}[renderer]
    for p in expected_pu:
        assert any(f"{p} PU" in g["t"] for g in greyed), (renderer, p, greyed)
    assert all(g["title"] == NOTE_C for g in greyed)
    assert not any(" EPS" in g["t"] and "PU" not in g["t"] for g in greyed)       # EPS stays a live choice
    if renderer != "tree":            # every PU control that IS drawn is disabled — none is left live
        for p in PANELS:
            sel = (f"#body-options-list input[data-draft-flag-mids='{m[(p, 'PU')]}']" if renderer == "draft"
                   else f"#body-options-list input[data-bom-id='{m[(p, 'PU')]}']")
            loc = page.locator(sel)
            for k in range(loc.count()):
                expect(loc.nth(k)).to_be_disabled()
    else:                                                    # the tree selects on a row click: the click does nothing
        before = page.evaluate("() => JSON.stringify(bodyOptionSelections)")
        page.locator(f"#body-options-list .bot-opt-row[data-mid='{m[('FRONT', 'PU')]}']").first.click(force=True)
        page.wait_for_timeout(500)
        assert page.evaluate("() => JSON.stringify(bodyOptionSelections)") == before
    expect(page.locator("#insulation-foam-block")).to_be_hidden(timeout=T)   # greyed PU = not offered
    shot(page, f"03-chiller-pu-greyed-{renderer}")


# ── 3 ───────────────────────────────────────────────────────────────────────
def test_switch_all_insulation_skips_the_forbidden_panels_and_says_so(page: Page, live_server: str, staged) -> None:
    ids = staged
    m = ids["freeze_flat_m"]
    admin_session(page, base=live_server)
    _open_calculator(page)
    _calc(page, lambda: page.select_option("#trailer-select", str(ids["freeze_flat"])), ids["freeze_flat"])
    page.locator(f"#body-options-list input[data-bom-id='{m[('ROOF', 'EPS')]}']").check()
    expect(page.locator("#modal-insulation-switch")).to_be_visible(timeout=T)
    expect(page.locator("#insulation-switch-body")).to_contain_text("FRONT, SIDES, DRD, SRD will be skipped")
    expect(page.locator("#insulation-switch-body")).to_contain_text(NOTE_F)
    page.click("#insulation-switch-yes")
    page.wait_for_timeout(800)
    s = page.evaluate("() => bodyOptionSelections")
    assert s[str(m[("ROOF", "EPS")])] is True and s[str(m[("FLOOR", "EPS")])] is True
    for p in ("FRONT", "SIDES", "DRD"):                    # left on PU, never switched to EPS
        assert s[str(m[(p, "PU")])] is True and not s.get(str(m[(p, "EPS")])), p
    assert not s.get(str(m[("SRD", "EPS")]))               # the unquoted door: its own machinery, never EPS


# ── 4 ───────────────────────────────────────────────────────────────────────
def test_paste_from_excel_refuses_the_pu_row_and_applies_the_rest(page: Page, live_server: str, staged) -> None:
    ids = staged
    m = ids["chill_flat_m"]
    admin_session(page, base=live_server)
    _open_calculator(page)
    _calc(page, lambda: page.select_option("#trailer-select", str(ids["chill_flat"])), ids["chill_flat"])
    page.click("#excel-paste-btn")
    page.fill("#excel-paste-input", "FRONT EPS\tN\t0\nFRONT PU\tY\t0.06\nROOF EPS\tY\t0.08\nROOF PU\tN\t0\n")
    page.dispatch_event("#excel-paste-input", "input")
    row = page.locator("#excel-paste-preview [data-xp-row='refused']")
    expect(row).to_have_count(1, timeout=T)
    expect(row).to_contain_text("FRONT PU")
    expect(row).to_contain_text(f"refused — {NOTE_C}")
    page.locator("#modal-excel-paste .modal").screenshot(path=str(SCREENSHOT_ROOT / JOURNEY / "04-paste-pu-refused.png"))
    page.click("#excel-paste-apply")
    page.wait_for_timeout(800)
    s = page.evaluate("() => bodyOptionSelections")
    assert not s.get(str(m[("FRONT", "PU")])) and s[str(m[("FRONT", "EPS")])] is True
    assert s[str(m[("ROOF", "EPS")])] is True                                    # the other rows applied


# ── 5 + 6 ───────────────────────────────────────────────────────────────────
def test_a_restored_breaching_costing_reopens_with_the_warning(page: Page, live_server: str, staged) -> None:
    ids = staged
    rec = _saved(ids, "freeze", {"FRONT": "EPS"}, "PU", deleted=True)
    admin_session(page, base=live_server)
    _open_calculator(page)
    csrf = page.evaluate("() => document.querySelector('meta[name=csrf-token]')?.content || ''")
    r = page.request.post(f"{live_server}/api/calculations/{rec}/restore",
                          headers={"X-CSRF-Token": csrf, "Origin": live_server})
    assert r.ok, r.text()
    _calc(page, lambda: page.goto(f"/mes/calculator?stay=1&edit={rec}"), ids["freeze"])
    expect(_breaches(page)).to_contain_text("✖ EPS insulation on the FRONT", timeout=T)
    expect(page.locator("#body-rule-breaches .rb-remove")).to_be_visible()


def test_a_forbidden_door_insulation_on_the_unused_door_is_named_as_such(page: Page, live_server: str, staged) -> None:
    """On the Settings-draft panel (which draws only what the draft offers: FRONT / SIDES) a re-opened quote keeps a
    hidden SRD PU tick while DRD is the quoted door: the warning names the panel and says it is not used. (The flat
    panel clears a hidden door's ticks itself when it re-opens a quote, so it never reaches the server there.)"""
    ids = staged
    rec = _saved(ids, "chill_draft", {"SRD": "PU"}, "EPS")             # DRD quoted; SRD PU ticked (hidden, unpriced)
    admin_session(page, base=live_server)
    _open_calculator(page)
    _calc(page, lambda: page.goto(f"/mes/calculator?stay=1&edit={rec}"), ids["chill_draft"])
    expect(_breaches(page)).to_contain_text(
        "✖ PU insulation on the SRD (single rear door) — not used on this quote", timeout=T)
    shot(page, "05-unused-door-named")


# ── 7 ───────────────────────────────────────────────────────────────────────
def test_this_side_port_shows_the_test_server_bar_and_title(page: Page, live_server: str) -> None:
    admin_session(page, base=live_server)
    page.goto("/mes/calculator?stay=1")
    bar = page.locator("#icb-test-banner")
    expect(bar).to_be_visible(timeout=T)
    host = live_server.split("://", 1)[1]
    expect(bar).to_have_text(f"TEST SERVER — {host} — not prod")
    assert page.title().startswith("[TEST] ")
    page.goto("/mes-app/")
    expect(page.locator("#icb-test-banner")).to_be_visible(timeout=T)
    assert page.title().startswith("[TEST] ")

