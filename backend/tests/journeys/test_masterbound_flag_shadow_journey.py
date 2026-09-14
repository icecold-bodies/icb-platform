"""v1.53.1 — master-bound draft flags must never shadow the master body variable.

Michael's report (FREEZER 2.3 METER on :8000): {SIDES PU}/{SIDES EPS} resolve
0.000 in the formula editor (a blue AND a teal chip per name), and insulation
radio flips never move quantities or totals. Mechanism (BA-verified, #181):
_draftFlagVariables() emitted EVERY draft flag name with value-or-explicit-0,
but a master-bound v2 body names its Explorer flags after its master
body-variable rows — so the explicit 0 rode body_variable_overrides and
overlaid the real variable_value server-side (and in the editor resolver) on
every calc, undoing the copy-zero the radio flip had just written.

Fix under test: a shared master-name set (_masterBodyVarNameSet) keeps master
names out of the draft-flag channel at its choke point, the thickness suffix
and the Excel-paste draft fallback; midsForFlag heals a STALE flagBindingId by
name so such a flag keeps its bound affordances.

Clients jump ?v=178 → ?v=180 and receive #184's server defaults + tombstones
together with this guard, so the masterless body proves that combined delta on
the wire (request payload, not just the response).

Assertions ride the real /api/calculate wire (request post_data_json + response)
— CSP forbids page-JS evaluation in journeys. JXMB markers; purge at setup AND
teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "masterbound_flag_shadow"
MARK = "JXMB"

EPS = f"{MARK} SIDES EPS"
PU = f"{MARK} SIDES PU"
ROOF = f"{MARK} ROOF THK"
DECK = f"{MARK} DECK THK"
FLOOR = f"{MARK} FLOOR PU"          # its master's material name carries a TRAILING SPACE


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    for sql in (
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}",
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}",
        "DELETE FROM icb_costings.materials WHERE name LIKE :m",
        "DELETE FROM icb_costings.trailer_types WHERE name LIKE :m",
    ):
        db.execute(text(sql), {"m": f"{MARK}%"})
    db.commit()


def _flag(nid, label, parent, mode, value, bind_name="", bind_id=None, **extra) -> dict:
    return {"id": nid, "type": "flag", "label": label, "parentId": parent, "childIds": [],
            "flagMode": mode, "flagValue": value, "flagBindingName": bind_name,
            "flagBindingId": bind_id, **extra}


def _cat(nid, label, children) -> dict:
    return {"id": nid, "type": "category", "label": label, "sourceCategoryKey": None,
            "parentId": None, "childIds": children}


# Template thicknesses each test starts from (a radio flip PUTs variable_value
# onto the shared template, so _reset_masters re-seeds before every test).
BOUND_START = {"eps": 0.0, "pu": 0.062}     # PU is the quoted side
STALE_START = {"eps": 0.062, "pu": 0.0}     # EPS quoted; the HEALED PU flag is the one clicked


@pytest.fixture(scope="module")
def staged():
    from app.database import (
        BillOfMaterial, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)

        def mat(name, uom="m3", price=0.0):
            m = Material(name=f"{MARK} {name}", unit_of_measure=uom, price_per_unit=price)
            db.add(m)
            db.flush()
            return m

        # Master vocabulary (pair members are the ONLY names containing EPS/PU —
        # _insulationPairFor identifies the pair structurally by name).
        m_eps, m_pu = mat("SIDES EPS", "each"), mat("SIDES PU", "each")
        m_epsb, m_foam = mat("POLY BOARD", price=2.0), mat("FOAM BOARD", price=5.0)
        m_skin, m_roof, m_deck, m_side2 = (mat("SKIN", price=1.0), mat("ROOF BOARD", price=1.0),
                                           mat("DECK BOARD", price=1.0), mat("SIDE LINER", price=1.0))

        def master(tt, m, default, value):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression="1",
                               is_body_option=True, body_option_group=f"{MARK} SIDES",
                               body_option_subgroup="INSULATION", body_option_default=default,
                               variable_value=value, bom_section="BODY OPTIONS")
            db.add(r)
            db.flush()
            return r

        def item(tt, m, formula, section):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=m.id,
                               formula_expression=formula, bom_section=section)
            db.add(r)
            db.flush()
            return r.id

        def sides_items(tt):
            sec = f"{MARK} SIDES"
            return {
                "eps_board": item(tt, m_epsb, f"width*height*{{{EPS}}}*10", sec),
                "pu_board": item(tt, m_foam, f"width*height*{{{PU}}}*10", sec),
                # the pair-deduction shape: BOTH sides deducted, one carries a value
                "skin": item(tt, m_skin, f"width*(2.6-{{{EPS}}}-{{{PU}}})", sec),
            }

        def v2_body(name):
            tt = TrailerType(name=f"{MARK} {name}", is_active=True, configurator_v2=True,
                             default_length=4.0, default_width=2.0, default_height=2.0)
            db.add(tt)
            db.flush()
            return tt

        ids = {}

        # (1) MASTER-BOUND body — the FREEZER 2.3 METER shape: flags bound by id
        #     AND named after the masters, plus a NAME-ONLY wired control flag.
        tb = v2_body("BOUND BODY")
        b_eps = master(tb, m_eps, False, BOUND_START["eps"])
        b_pu = master(tb, m_pu, True, BOUND_START["pu"])
        # Whitespace-drift master: the BOM material is "JXMB FLOOR PU " while the
        # Explorer stores the stripped name — midsForFlag's untrimmed name lookup
        # misses, so the flag renders UNBOUND (the only way flagVarSpan's master
        # guard is reachable), yet the engine (strip().upper()) resolves the token.
        m_floor_pu, m_floor = mat("FLOOR PU ", "each"), mat("FLOOR BOARD", price=1.0)
        b_floor = BillOfMaterial(trailer_type_id=tb.id, material_id=m_floor_pu.id, formula_expression="1",
                                 is_body_option=True, body_option_group=f"{MARK} FLOOR",
                                 variable_value=0.07, bom_section="BODY OPTIONS")
        db.add(b_floor)
        db.flush()
        ids["bound"] = {"tt": tb.id, "eps_m": b_eps.id, "pu_m": b_pu.id, **sides_items(tb),
                        "roof": item(tb, m_roof, f"width*{{{ROOF}}}*5", f"{MARK} ROOF"),
                        "floor": item(tb, m_floor, f"width*{{{FLOOR}}}*10", f"{MARK} ROOF")}
        db.add(ConfiguratorDraft(trailer_type_id=tb.id, payload=json.dumps({
            "nextId": 7, "rootIds": ["1", "4"], "itemRules": {}, "nodes": {
                "1": _cat("1", f"{MARK} SIDES", ["2", "3"]),
                "2": _flag("2", EPS, "1", "radio", 0, EPS, b_eps.id),
                "3": _flag("3", PU, "1", "radio", 1, PU, b_pu.id),
                "4": _cat("4", f"{MARK} ROOF", ["5", "6"]),
                "5": _flag("5", ROOF, "4", "tickbox", 1, flagVarDefault=0.04),
                "6": _flag("6", FLOOR, "4", "tickbox", 1),
            }})))

        # (2) STALE-BINDING body — the PU flag's flagBindingId points at a row
        #     that no longer exists (deleted/re-imported; ids are never reused).
        ts = v2_body("STALE BODY")
        ghost = master(ts, m_pu, False, 0.0)
        ghost_id = ghost.id
        db.delete(ghost)
        db.flush()
        s_eps = master(ts, m_eps, True, STALE_START["eps"])
        s_pu = master(ts, m_pu, False, STALE_START["pu"])
        ids["stale"] = {"tt": ts.id, "eps_m": s_eps.id, "pu_m": s_pu.id, "ghost_id": ghost_id,
                        **sides_items(ts)}
        db.add(ConfiguratorDraft(trailer_type_id=ts.id, payload=json.dumps({
            "nextId": 4, "rootIds": ["1"], "itemRules": {}, "nodes": {
                "1": _cat("1", f"{MARK} SIDES", ["2", "3"]),
                "2": _flag("2", EPS, "1", "radio", 1, EPS, s_eps.id),
                "3": _flag("3", PU, "1", "radio", 0, PU, ghost_id),
            }})))

        # (3) MASTERLESS body (Manni RIGIDS CB class) — name-only flags with
        #     server defaults. One flag deliberately COLLIDES with the bound
        #     body's master name: the guard is per-body, so here it must be sent.
        tn = v2_body("NAMEONLY BODY")
        ids["nameonly"] = {
            "tt": tn.id,
            "deck": item(tn, m_deck, f"width*{{{DECK}}}*5", f"{MARK} DECK"),
            "liner": item(tn, m_side2, f"width*{{{PU}}}*10", f"{MARK} DECK"),
        }
        db.add(ConfiguratorDraft(trailer_type_id=tn.id, payload=json.dumps({
            "nextId": 4, "rootIds": ["1"], "itemRules": {}, "nodes": {
                "1": _cat("1", f"{MARK} DECK", ["2", "3"]),
                "2": _flag("2", DECK, "1", "tickbox", 1, flagVarDefault=0.04),
                "3": _flag("3", PU, "1", "tickbox", 1, flagVarDefault=0.05),
            }})))
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


@pytest.fixture(autouse=True)
def _reset_masters(staged):
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        for body, start in (("bound", BOUND_START), ("stale", STALE_START)):
            db.get(BillOfMaterial, staged[body]["eps_m"]).variable_value = start["eps"]
            db.get(BillOfMaterial, staged[body]["pu_m"]).variable_value = start["pu"]
        db.commit()


# ── helpers ─────────────────────────────────────────────────────────────────

def _calc_where(pred):
    """expect_response predicate on the REQUEST payload — defeats the
    level-vs-edge trap (a debounced calc for the previous state landing
    inside the `with` block)."""
    def _match(resp) -> bool:
        if resp.request.method != "POST" or not resp.url.split("?")[0].endswith("/api/calculate"):
            return False
        try:
            return bool(pred(resp.request.post_data_json or {}))
        except Exception:
            return False
    return _match


def _bvo(req: dict) -> dict:
    return req.get("body_variable_overrides") or {}


def _item(res: dict, bom_id: int) -> dict:
    it = next((i for i in res.get("items") or [] if i.get("bom_id") == bom_id), None)
    assert it is not None, f"bom_id {bom_id} not in calc items"
    return it


def _qty(res: dict, bom_id: int) -> float:
    return float(_item(res, bom_id).get("quantity") or 0)


def _open(page: Page, base: str, tt: int) -> None:
    admin_session(page, base=base)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(tt))


def _open_formula_editor(page: Page, section: str, bom_id: int, formula: str) -> None:
    hdr = page.locator(f"tr.calc-grp-hdr[data-cat-name='{section}']").first
    row = page.locator(f"tr.calc-grp-row[data-bom-id='{bom_id}']").first
    expect(hdr).to_be_visible(timeout=T)
    if not row.is_visible():
        hdr.click()
    expect(row).to_be_visible(timeout=T)
    row.click(button="right")
    expect(page.locator("#bom-ctx-menu")).to_be_visible(timeout=T)
    page.locator("#ctx-edit-formula-item").click()
    expect(page.locator("#modal-formula-edit")).to_be_visible(timeout=T)
    expect(page.locator("#formula-edit-input")).to_have_value(formula)


def _close_formula_editor(page: Page) -> None:
    page.locator("#modal-formula-edit .modal-footer button.btn-outline").click()
    expect(page.locator("#modal-formula-edit")).to_be_hidden(timeout=T)


def _chip(page: Page, kind: str, name: str):
    """kind: 'body variable' (blue) | 'explorer flag thickness' (teal)."""
    return (page.locator(f"#formula-edit-bv-chips button[title*='{kind}']")
            .filter(has_text="{" + name + "}"))


def _db_pair(eps_id: int, pu_id: int, want_eps: float, want_pu: float) -> tuple[float, float]:
    """Poll the template until the async copy-zero PUTs land."""
    from app.database import BillOfMaterial, SessionLocal
    e = p = None
    for _ in range(40):
        with SessionLocal() as db:
            e = float(db.get(BillOfMaterial, eps_id).variable_value or 0)
            p = float(db.get(BillOfMaterial, pu_id).variable_value or 0)
        if abs(e - want_eps) < 1e-9 and abs(p - want_pu) < 1e-9:
            break
        time.sleep(0.5)
    return e, p


# ── 1. master-bound body: no shadow — editor, payload, radio flip ───────────

def test_masterbound_flags_do_not_shadow_master_values(page: Page, live_server: str, staged) -> None:
    b = staged["bound"]
    _open(page, live_server, b["tt"])
    pu_in = page.locator(f"input[data-draft-flag-mids='{b['pu_m']}'][data-draft-flag-name='{PU}']")
    eps_in = page.locator(f"input[data-draft-flag-mids='{b['eps_m']}'][data-draft-flag-name='{EPS}']")
    expect(pu_in).to_be_checked(timeout=30_000)
    expect(page.locator(f"span.bv-edit[data-bom-id='{b['pu_m']}']")).to_have_text("(0.062 m)")
    # a master-named flag never grows the draft-thickness suffix
    expect(page.locator(f".flag-var-edit[data-flag-var='{PU}']")).to_have_count(0)
    expect(page.locator(f".flag-var-edit[data-flag-var='{EPS}']")).to_have_count(0)
    # the name-only wired control on the SAME body keeps its (inherited) suffix
    expect(page.locator(f".flag-var-edit[data-flag-var='{ROOF}']")).to_have_text("(0.040 m)", timeout=T)
    # whitespace-drift master: UNBOUND render, but its name IS a master body
    # variable → flagVarSpan's guard suppresses the suffix (pre-fix: "(set thickness)")
    expect(page.locator(f"input[data-draft-flag='{FLOOR}']")).to_be_attached()
    expect(page.locator(f".flag-var-edit[data-flag-var='{FLOOR}']")).to_have_count(0)

    # Engine truth for the settled state.
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == b["tt"]
            and (p.get("body_option_selections") or {}).get(str(b["pu_m"])) is True), timeout=T) as r1:
        page.locator("#f-margin").fill("0")
    req1, res1 = r1.value.request.post_data_json, r1.value.json()
    assert PU not in _bvo(req1) and EPS not in _bvo(req1), _bvo(req1)   # THE shadow
    assert _bvo(req1).get(ROOF) == 0.04                                    # name-only still sent
    bv1 = res1.get("body_variables") or {}
    assert bv1.get(PU) == 0.062 and bv1.get(EPS) == 0.0, bv1
    assert abs(_qty(res1, b["pu_board"]) - 2.48) < 1e-6        # 2*2*0.062*10
    assert _qty(res1, b["eps_board"]) == 0
    assert abs(_qty(res1, b["skin"]) - 5.076) < 1e-6           # 2*(2.6-0-0.062); shadow = 5.2
    assert not _item(res1, b["pu_board"]).get("formula_error")
    assert FLOOR not in _bvo(req1), _bvo(req1)                  # trimmed-name guard
    assert bv1.get(FLOOR + " ") == 0.07, bv1
    assert abs(_qty(res1, b["floor"]) - 1.4) < 1e-6             # 2*0.07*10; shadow = 0

    # Formula editor: ONE blue chip per master name with the real value, the
    # resolver reads 0.062, no teal duplicates — the teal control survives.
    _open_formula_editor(page, f"{MARK} SIDES", b["pu_board"], f"width*height*{{{PU}}}*10")
    expect(page.locator("#formula-edit-bv-chips button").filter(has_text="{" + PU + "}")).to_have_count(1)
    expect(_chip(page, "body variable", PU)).to_have_count(1)
    expect(_chip(page, "body variable", PU)).to_contain_text("0.062")
    expect(_chip(page, "explorer flag thickness", PU)).to_have_count(0)
    expect(_chip(page, "explorer flag thickness", EPS)).to_have_count(0)
    expect(_chip(page, "explorer flag thickness", ROOF)).to_have_count(1)
    resolved = page.locator("#formula-edit-resolved-list")
    expect(resolved).to_contain_text("{" + PU + "} = 0.062 m")
    expect(resolved.locator("span[style*='#58a6ff']").filter(has_text="{" + PU + "}")).to_have_count(1)
    expect(resolved.locator("span[style*='#56b08a']")).to_have_count(0)
    expect(page.locator("#formula-edit-result")).to_have_text("= 2.4800")
    shot(page, "01-editor-single-blue-chip-real-value", journey=JOURNEY)
    _close_formula_editor(page)

    # Radio flip PU → EPS: copy-zero writes the template AND the totals move.
    with page.expect_response(_calc_where(
            lambda p: (p.get("body_option_selections") or {}).get(str(b["eps_m"])) is True), timeout=T) as r2:
        eps_in.check()
    req2, res2 = r2.value.request.post_data_json, r2.value.json()
    assert PU not in _bvo(req2) and EPS not in _bvo(req2), _bvo(req2)
    bv2 = res2.get("body_variables") or {}
    assert bv2.get(EPS) == 0.062 and bv2.get(PU) == 0.0, bv2
    assert abs(_qty(res2, b["eps_board"]) - 2.48) < 1e-6
    assert _qty(res2, b["pu_board"]) == 0
    assert abs(_qty(res2, b["skin"]) - 5.076) < 1e-6            # pair sum invariant
    # FOAM (5.0) → POLY (2.0) on 2.48 units: the total must fall by 7.44
    assert abs((res1["grand_total"] - res2["grand_total"]) - 7.44) < 0.01, (res1["grand_total"], res2["grand_total"])
    expect(page.locator(f"span.bv-edit[data-bom-id='{b['eps_m']}']")).to_have_text("(0.062 m)", timeout=T)
    expect(page.locator(f"span.bv-edit[data-bom-id='{b['pu_m']}']")).to_have_text("(0.000 m)")
    e, p = _db_pair(b["eps_m"], b["pu_m"], 0.062, 0.0)
    assert abs(e - 0.062) < 1e-9 and p == 0, (e, p)
    shot(page, "02-radio-flip-moves-quantities-and-total", journey=JOURNEY)

    # Excel paste: a squash-drift label misses the exact master match and lands
    # in the draft fallback — a master-named flag must NOT park the thickness.
    page.locator("#excel-paste-btn").click()
    expect(page.locator("#modal-excel-paste")).to_be_visible(timeout=T)
    page.locator("#excel-paste-input").fill(f"{MARK} SIDESPU\t\t0.05\tY")
    preview = page.locator("#excel-paste-preview")
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} SIDESPU thickness']")).to_contain_text(
        "master-bound", timeout=T)
    expect(preview.locator(f"[data-xp-row='draftvar'][data-xp-label='{MARK} SIDESPU thickness']")).to_have_count(0)
    shot(page, "03-paste-master-bound-thickness-skipped", journey=JOURNEY)


# ── 2. stale flagBindingId: heal by name → bound affordances, flip works ────

def test_stale_binding_falls_back_by_name(page: Page, live_server: str, staged) -> None:
    s = staged["stale"]
    _open(page, live_server, s["tt"])
    healed = page.locator(f"input[data-draft-flag-mids='{s['pu_m']}'][data-draft-flag-name='{PU}']")
    live_eps = page.locator(f"input[data-draft-flag-mids='{s['eps_m']}'][data-draft-flag-name='{EPS}']")
    expect(live_eps).to_be_checked(timeout=30_000)
    expect(healed).to_be_attached(timeout=T)
    expect(healed).not_to_be_checked()
    # the BOUND affordance renders (blue bv-edit on the healed row) …
    expect(page.locator(f"span.bv-edit[data-bom-id='{s['pu_m']}']")).to_have_text("(0.000 m)")
    expect(page.locator(f"span.bv-edit[data-bom-id='{s['eps_m']}']")).to_have_text("(0.062 m)")
    # … and nothing of the unbound fallback remains
    expect(page.locator(f"input[data-draft-flag='{PU}']")).to_have_count(0)
    expect(page.locator(f".flag-var-edit[data-flag-var='{PU}']")).to_have_count(0)
    shot(page, "04-stale-binding-healed-bound", journey=JOURNEY)

    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == s["tt"]
            and (p.get("body_option_selections") or {}).get(str(s["eps_m"])) is True), timeout=T) as r1:
        page.locator("#f-margin").fill("0")
    req1, res1 = r1.value.request.post_data_json, r1.value.json()
    assert not (req1.get("body_option_selections") or {}).get(str(s["ghost_id"]))
    assert PU not in _bvo(req1) and EPS not in _bvo(req1), _bvo(req1)
    assert abs(_qty(res1, s["eps_board"]) - 2.48) < 1e-6
    assert _qty(res1, s["pu_board"]) == 0

    # Click the HEALED flag: it drives the master pair by the healed id.
    with page.expect_response(_calc_where(
            lambda p: (p.get("body_option_selections") or {}).get(str(s["pu_m"])) is True), timeout=T) as r2:
        healed.check()
    req2, res2 = r2.value.request.post_data_json, r2.value.json()
    assert PU not in _bvo(req2) and EPS not in _bvo(req2), _bvo(req2)
    bv2 = res2.get("body_variables") or {}
    assert bv2.get(PU) == 0.062 and bv2.get(EPS) == 0.0, bv2
    assert abs(_qty(res2, s["pu_board"]) - 2.48) < 1e-6
    assert _qty(res2, s["eps_board"]) == 0
    assert not _item(res2, s["pu_board"]).get("formula_error")
    assert abs((res2["grand_total"] - res1["grand_total"]) - 7.44) < 0.01, (res1["grand_total"], res2["grand_total"])
    expect(page.locator(f"span.bv-edit[data-bom-id='{s['pu_m']}']")).to_have_text("(0.062 m)", timeout=T)
    e, p = _db_pair(s["eps_m"], s["pu_m"], 0.0, 0.062)
    assert e == 0 and abs(p - 0.062) < 1e-9, (e, p)
    shot(page, "05-healed-flag-flip-moves-total", journey=JOURNEY)


# ── 3. masterless combined delta (#184 defaults + tombstone + this guard) ───

def test_masterless_defaults_tombstone_and_editor_on_the_wire(page: Page, live_server: str, staged) -> None:
    n = staged["nameonly"]
    _open(page, live_server, n["tt"])
    deck = page.locator(f".flag-var-edit[data-flag-var='{DECK}']")
    # fresh browser inherits flagVarDefault — including the name that is a
    # MASTER name on another body (the guard is per-body, never global)
    expect(deck).to_have_text("(0.040 m)", timeout=30_000)
    expect(page.locator(f".flag-var-edit[data-flag-var='{PU}']")).to_have_text("(0.050 m)")

    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == n["tt"] and DECK in _bvo(p)), timeout=T) as r0:
        page.locator("#f-margin").fill("0")
    req0, res0 = r0.value.request.post_data_json, r0.value.json()
    assert _bvo(req0).get(DECK) == 0.04 and _bvo(req0).get(PU) == 0.05, _bvo(req0)
    assert abs(_qty(res0, n["deck"]) - 0.4) < 1e-9          # 2*0.04*5
    assert abs(_qty(res0, n["liner"]) - 1.0) < 1e-9         # 2*0.05*10
    assert not _item(res0, n["deck"]).get("formula_error")

    # Editor: the name-only flag stays TEAL with its value (never blue, never ⚠).
    _open_formula_editor(page, f"{MARK} DECK", n["deck"], f"width*{{{DECK}}}*5")
    expect(_chip(page, "explorer flag thickness", DECK)).to_have_count(1)
    expect(_chip(page, "body variable", DECK)).to_have_count(0)
    resolved = page.locator("#formula-edit-resolved-list")
    expect(resolved).to_contain_text("{" + DECK + "} = 0.040 m")
    expect(resolved.locator("span[style*='#56b08a']").filter(has_text="{" + DECK + "}")).to_have_count(1)
    expect(page.locator("#formula-edit-result")).to_have_text("= 0.4000")
    shot(page, "06-masterless-teal-chip-default", journey=JOURNEY)
    _close_formula_editor(page)

    # Explicit 0 → tombstone on the wire …
    deck.click()
    expect(page.locator("#modal-prompt")).to_be_visible(timeout=T)
    page.locator("#prompt-input").fill("0")
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == n["tt"] and _bvo(p).get(DECK) == 0), timeout=T) as r1:
        page.locator("#modal-prompt button.btn-primary").click()
    expect(page.locator(f".flag-var-edit[data-flag-var='{DECK}']")).to_have_text("(set thickness)", timeout=T)
    assert _qty(r1.value.json(), n["deck"]) == 0

    # … and it SURVIVES a reload on the wire: 0 is sent, not the 0.04 default.
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == n["tt"] and DECK in _bvo(p)), timeout=30_000) as r2:
        page.goto("/calculator")
        expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
        page.select_option("#trailer-select", str(n["tt"]))
    req2, res2 = r2.value.request.post_data_json, r2.value.json()
    assert _bvo(req2).get(DECK) == 0, _bvo(req2)
    assert _bvo(req2).get(PU) == 0.05, _bvo(req2)
    it = _item(res2, n["deck"])
    assert float(it.get("quantity") or 0) == 0 and not it.get("formula_error") and not it.get("formula_unknown_vars")
    expect(page.locator(f".flag-var-edit[data-flag-var='{DECK}']")).to_have_text("(set thickness)", timeout=T)
    shot(page, "07-tombstone-survives-reload-on-wire", journey=JOURNEY)


# ── 4. same page, colliding names across bodies: the guard is per-body ──────

def test_body_switch_guard_follows_the_current_body(page: Page, live_server: str, staged) -> None:
    b, n = staged["bound"], staged["nameonly"]
    _open(page, live_server, b["tt"])
    expect(page.locator(f"input[data-draft-flag-mids='{b['pu_m']}']")).to_be_checked(timeout=30_000)
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == b["tt"]
            and (p.get("body_option_selections") or {}).get(str(b["pu_m"])) is True), timeout=T) as r1:
        page.locator("#f-margin").fill("0")
    assert PU not in _bvo(r1.value.request.post_data_json), _bvo(r1.value.request.post_data_json)
    assert (r1.value.json().get("body_variables") or {}).get(PU) == 0.062

    # → masterless body: the SAME name is now a name-only flag and IS sent.
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == n["tt"] and DECK in _bvo(p)), timeout=30_000) as r2:
        page.select_option("#trailer-select", str(n["tt"]))
    assert _bvo(r2.value.request.post_data_json).get(PU) == 0.05, _bvo(r2.value.request.post_data_json)
    assert abs(_qty(r2.value.json(), n["liner"]) - 1.0) < 1e-9

    # → back to the bound body: the master value wins again, nothing carried over.
    with page.expect_response(_calc_where(
            lambda p: p.get("trailer_type_id") == b["tt"]
            and (p.get("body_option_selections") or {}).get(str(b["pu_m"])) is True
            and ROOF in _bvo(p)), timeout=30_000) as r3:
        page.select_option("#trailer-select", str(b["tt"]))
    req3, res3 = r3.value.request.post_data_json, r3.value.json()
    assert PU not in _bvo(req3) and EPS not in _bvo(req3), _bvo(req3)
    assert (res3.get("body_variables") or {}).get(PU) == 0.062
    assert abs(_qty(res3, b["pu_board"]) - 2.48) < 1e-6
    shot(page, "08-body-switch-master-value-restored", journey=JOURNEY)
