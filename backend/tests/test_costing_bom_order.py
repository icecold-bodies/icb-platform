"""v1.54 — a saved costing's BOM is shown in the calculator's line order.

Michael (15 Sep): "when the user views the BOM in a costing the items must be in the same
order as in the costings. this order is the same as the body type is on the template."

/api/approve stores result["items"] by section and then MATERIAL NAME A–Z; the calculator
shows each line by its BOM row's sort_order (its default "sheet" view). Every view of a
SAVED costing rendered the stored order, so none of them matched the calculator. The rule now
lives once, in services/bom_order, ported from calculator.js — these tests pin it:

  PARITY    services/bom_order.calculator_order == calculator.js sortedGroupEntries, run
            for real under node on 400 randomised BOMs (ties, missing rows, free-hand
            lines, blank categories). A change to the JS rule turns this red.
  VIEWS     the costing page payload, the legacy results page, the saved-costing exports,
            the quote report and the Plan job drawer all show the calculator order.
  UNTOUCHED the stored result_json keeps its A–Z order (read-time ordering only), and a
            REPAIRS costing (no body type) keeps the order its lines were entered in.

House pattern: live test DB, marker rows (V154BO), real session rows, purge on both sides.
"""
import json
import random
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

_MARK = "V154BO"
TT_NAME = f"{_MARK} BODY"
CALC_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "calculator.js"


# ── parity with the real calculator.js ───────────────────────────────────────

def _js_function(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth = 0
    for j in range(src.index("{", start), len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def test_the_port_still_matches_the_lines_it_was_ported_from():
    """The node harness below re-creates renderBOMWithCosts' grouping loop around the REAL
    sortedGroupEntries. If the calculator changes how it keys or groups lines, that loop
    is stale — so the lines it copies are pinned here."""
    src = CALC_JS.read_text(encoding="utf-8")
    body = _js_function(src, "renderBOMWithCosts")
    for line in (
        "const cat = it.category || 'Uncategorised';",
        "it.__sortOrder = ref && ref.sort_order != null ? ref.sort_order : i;",
        "if (!groups[cat]) { groups[cat] = []; firstIdx[cat] = it.__sortOrder; }",
        "else if (it.__sortOrder < firstIdx[cat]) firstIdx[cat] = it.__sortOrder;",
        "const sortedEntries = sortedGroupEntries(groups, firstIdx, 'material');",
    ):
        assert line in body, f"calculator.js renderBOMWithCosts no longer contains: {line}"
    assert "return localStorage.getItem(BOM_SORT_KEY) || 'sheet';" in src, \
        "the calculator's default BOM view is no longer 'sheet'"


_HARNESS = r"""
const getBomSortMode = () => 'sheet';
%s
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(({items, bomRef}) => {
  const groups = {};
  const firstIdx = {};
  items.forEach((it, i) => {
    const cat = it.category || 'Uncategorised';
    const ref = it.bom_id != null
      ? (bomRef || []).find(b => String(b.id) === String(it.bom_id))
      : null;
    it.__sortOrder = ref && ref.sort_order != null ? ref.sort_order : i;
    if (!groups[cat]) { groups[cat] = []; firstIdx[cat] = it.__sortOrder; }
    else if (it.__sortOrder < firstIdx[cat]) firstIdx[cat] = it.__sortOrder;
    groups[cat].push(it);
  });
  return sortedGroupEntries(groups, firstIdx, 'material').flatMap(([, its]) => its.map(it => it.key));
});
process.stdout.write(JSON.stringify(out));
"""


def _random_case(rng: random.Random) -> dict:
    cats = ["FRONT", "SRD", "SRD DOOR FITTINGS", "DRD", "SIDES", "FLOOR", ""]
    bom_ref, items = [], []
    for n in range(rng.randint(0, 40)):
        bom_id = 1000 + n
        if rng.random() < 0.85:     # most lines have a BOM row; some rows lack sort_order
            bom_ref.append({"id": bom_id,
                            "sort_order": rng.choice([None] + list(range(0, 25)))})
        kind = rng.random()
        items.append({
            "key": n,
            "category": rng.choice(cats),
            "material": f"M{rng.randint(0, 9)}",
            # a free-hand/repair line has no bom_id; a deleted row has an id with no ref;
            # ids sometimes arrive as strings, as JSON from the client can deliver them
            "bom_id": (None if kind < 0.15 else
                       str(bom_id) if kind < 0.25 else bom_id),
        })
    return {"items": items, "bomRef": bom_ref}


def test_calculator_order_is_the_calculator_js_order():
    from app.services.bom_order import calculator_order
    node = shutil.which("node")
    assert node, "node is needed for the calculator.js parity check (CI sets it up)"
    rng = random.Random(154)
    cases = [_random_case(rng) for _ in range(400)]
    fn = _js_function(CALC_JS.read_text(encoding="utf-8"), "sortedGroupEntries")
    run = subprocess.run([node, "-e", _HARNESS % fn], input=json.dumps(cases),
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:2000]
    js_orders = json.loads(run.stdout)
    for case, js in zip(cases, js_orders):
        so = {b["id"]: b["sort_order"] for b in case["bomRef"] if b["sort_order"] is not None}
        py = [it["key"] for it in calculator_order(case["items"], so)]
        assert py == js, json.dumps(case)[:1500]


def test_template_row_order_beats_the_alphabet():
    from app.services.bom_order import calculator_order
    items = [  # as /api/approve stores them: section, then material A–Z
        {"bom_id": 12, "category": "FRONT", "material": "ALPHA PANEL"},
        {"bom_id": 11, "category": "FRONT", "material": "ZETA PANEL"},
        {"bom_id": 14, "category": "SIDES", "material": "ALPHA SHEET"},
        {"bom_id": 13, "category": "SIDES", "material": "ZULU SHEET"},
    ]
    got = calculator_order(items, {11: 1, 12: 2, 13: 3, 14: 4})
    assert [it["material"] for it in got] == ["ZETA PANEL", "ALPHA PANEL", "ZULU SHEET", "ALPHA SHEET"]


def test_sections_follow_their_first_template_row_not_the_stored_sequence():
    from app.services.bom_order import calculator_order
    items = [{"bom_id": 1, "category": "DRD"}, {"bom_id": 2, "category": "SRD"}]
    assert [it["category"] for it in calculator_order(items, {1: 50, 2: 10})] == ["SRD", "DRD"]


def test_tied_sections_stay_whole_and_in_first_seen_order():
    """Two sections whose smallest key is equal must not interleave (the preview's old
    inline copy of this rule had exactly that flaw: one composite key, no tie-break)."""
    from app.services.bom_order import calculator_order
    items = [{"bom_id": 1, "category": "A"}, {"bom_id": 2, "category": "B"},
             {"bom_id": 3, "category": "A"}, {"bom_id": 4, "category": "B"}]
    got = [it["category"] for it in calculator_order(items, {1: 5, 2: 5, 3: 9, 4: 7})]
    assert got == ["A", "A", "B", "B"]


def test_non_dict_and_empty_results_come_back_untouched():
    from app.services.bom_order import order_result_items
    assert order_result_items(None, [1, 2], 5) == [1, 2]
    assert order_result_items(None, {"items": []}, 5) == {"items": []}
    same = {"items": [{"bom_id": 1}]}
    assert order_result_items(None, same, None) is same     # a REPAIRS costing: no body type


# ── the views, against a real saved costing ──────────────────────────────────

def _purge(db) -> None:
    owned = ("SELECT cal.id FROM icb_costings.calculations cal "
             "JOIN icb_costings.customers c ON c.id = cal.customer_id WHERE c.name LIKE :m")
    db.execute(text(f"DELETE FROM icb_mes.production_jobs WHERE calculation_record_id IN ({owned})"),
               {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
                    "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    from app.database import SessionLocal, User, UserSession
    sid = f"v154-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        db.merge(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None,
                             csrf_token=f"csrf-{sid}"))
        db.commit()
    yield {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()


# The template order vs the order /api/approve stores:
#   template   FRONT: ZETA PANEL(1), ALPHA PANEL(2)   SIDES: ZULU SHEET(3), ALPHA SHEET(4)
#   stored     SIDES first (its GLOBAL section sort is lower), each section A–Z
EXPECTED = [f"{_MARK} ZETA PANEL", f"{_MARK} ALPHA PANEL", f"{_MARK} ZULU SHEET", f"{_MARK} ALPHA SHEET"]


@pytest.fixture(scope="module")
def body(app_mod):
    from app.database import (SessionLocal, TrailerType, BillOfMaterial, BOMSection,
                              Material, Customer)
    with SessionLocal() as db:
        _purge(db)
        sides = BOMSection(name=f"{_MARK} SIDES", sort_order=1, is_optional=False)
        front = BOMSection(name=f"{_MARK} FRONT", sort_order=2, is_optional=False)
        tt = TrailerType(name=TT_NAME, is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
        mats = {n: Material(name=f"{_MARK} {n}", unit_of_measure="each", price_per_unit=10.0,
                            is_active=True)
                for n in ("ZETA PANEL", "ALPHA PANEL", "ZULU SHEET", "ALPHA SHEET")}
        db.add_all([sides, front, tt, cust, *mats.values()])
        db.flush()
        rows = []
        for n, sec, so in (("ZETA PANEL", front, 1), ("ALPHA PANEL", front, 2),
                           ("ZULU SHEET", sides, 3), ("ALPHA SHEET", sides, 4)):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=mats[n].id,
                               formula_expression="1", waste_percentage=0,
                               bom_section=sec.name, bom_section_id=sec.id, sort_order=so)
            db.add(r)
            rows.append(r)
        db.commit()
        ids = {"tt": tt.id, "customer": cust.id, "rows": [r.id for r in rows],
               "mats": [m.id for m in mats.values()], "sections": [sides.id, front.id]}
    yield ids
    with SessionLocal() as db:
        _purge(db)
        db.query(BillOfMaterial).filter(BillOfMaterial.trailer_type_id == ids["tt"]).delete()
        db.query(TrailerType).filter_by(id=ids["tt"]).delete()
        db.query(Customer).filter_by(id=ids["customer"]).delete()
        db.query(Material).filter(Material.id.in_(ids["mats"])).delete(synchronize_session=False)
        db.query(BOMSection).filter(BOMSection.id.in_(ids["sections"])).delete(synchronize_session=False)
        db.commit()


@pytest.fixture(scope="module")
def saved(client, admin_headers, body):
    r = client.post("/api/approve", headers=admin_headers, json={
        "trailer_type_id": body["tt"], "customer_id": body["customer"],
        "dimensions": {"length": 6.0, "width": 2.5, "height": 2.4}, "profit_margin": 0})
    assert r.status_code == 200, r.text[:500]
    return r.json()["record_id"]


def _names(items) -> list[str]:
    return [it["material"] for it in items if not it.get("excluded")]


def test_the_stored_costing_is_left_exactly_as_saved(saved):
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        stored = json.loads(db.get(CalculationRecord, saved).result_json)["items"]
    assert _names(stored) == [f"{_MARK} ALPHA SHEET", f"{_MARK} ZULU SHEET",
                              f"{_MARK} ALPHA PANEL", f"{_MARK} ZETA PANEL"], \
        "the premise changed: /api/approve no longer stores A–Z (update this module's docstring)"


def test_the_costing_page_payload_is_in_calculator_order(client, admin_headers, saved):
    d = client.get(f"/api/calculations/{saved}", headers=admin_headers).json()
    assert _names(d["saved_result"]["items"]) == EXPECTED


def test_the_legacy_results_page_is_in_calculator_order(client, admin_headers, saved):
    html = client.get(f"/results/{saved}", headers=admin_headers).text
    positions = [html.find(name) for name in EXPECTED]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), positions


def test_saved_costing_exports_are_in_calculator_order(saved):
    from app.database import CalculationRecord, SessionLocal
    from app.routers.exports import _doc_ctx_for_record
    with SessionLocal() as db:
        ctx, _stem = _doc_ctx_for_record(db.get(CalculationRecord, saved), db,
                                         detail="items", ratios_raw=None)
    assert _names(ctx["items"]) == EXPECTED


def test_the_live_preview_uses_the_same_rule_and_keeps_its_alpha_mode(saved, client, admin_headers):
    from app.database import CalculationRecord, SessionLocal
    from app.routers.exports import _doc_ctx_for_preview
    with SessionLocal() as db:
        rec = db.get(CalculationRecord, saved)
        live = json.loads(rec.result_json)
        body = {"result": live, "trailer_type_id": rec.trailer_type_id, "detail": "items"}
        sheet, _ = _doc_ctx_for_preview(dict(body), db)
        alpha, _ = _doc_ctx_for_preview(dict(body, bom_sort_mode="alpha"), db)
    assert _names(sheet["items"]) == EXPECTED
    assert _names(alpha["items"]) == [f"{_MARK} ALPHA PANEL", f"{_MARK} ZETA PANEL",
                                      f"{_MARK} ALPHA SHEET", f"{_MARK} ZULU SHEET"]


def test_the_quote_report_is_in_calculator_order(client, admin_headers, saved, monkeypatch):
    from types import SimpleNamespace
    import app.routers.exports as exports
    import app.report_engine as report_engine
    seen = {}

    def fake_render(**kw):
        seen["items"] = kw["result"]["items"]
        return b"%PDF-1.4 stub"
    monkeypatch.setattr(exports, "resolve_report_template", lambda tt: SimpleNamespace(slug="stub"))
    monkeypatch.setattr(report_engine, "render_by_slug", fake_render)
    r = client.get(f"/results/{saved}/report", headers=admin_headers)
    assert r.status_code == 200, r.text[:300]
    assert _names(seen["items"]) == EXPECTED


def test_the_plan_job_drawer_is_in_calculator_order(client, admin_headers, saved):
    from app.database import Branch, SessionLocal
    from app.models.mes import ProductionJob
    job_number = f"{_MARK}{uuid.uuid4().hex[:4]}".upper()
    with SessionLocal() as db:
        branch = db.query(Branch).order_by(Branch.id).first()
        db.add(ProductionJob(calculation_record_id=saved, branch_id=branch.id, source="quote",
                             status="accepted", job_number=job_number))
        db.commit()
    d = client.get(f"/api/plan/job-card/{job_number}", headers=admin_headers).json()
    shown = [it["material"] for cat in d["bom"]["categories"] for it in cat["items"]]
    assert shown == EXPECTED


def test_a_repair_keeps_the_order_its_lines_were_entered_in(client, admin_headers, body):
    lines = [{"kind": "free_hand", "key": f"k{i}", "description": d, "qty": 1, "unit": "each",
              "unit_price": 10} for i, d in enumerate(["Zebra seal", "Alpha rivets", "Middle glue"])]
    r = client.post("/api/approve", headers=admin_headers, json={
        "is_repair": True, "trailer_type_id": None, "customer_id": body["customer"],
        "repair_type": "Order check", "repair_lines": lines, "profit_margin": 0, "dimensions": {}})
    assert r.status_code == 200, r.text[:300]
    d = client.get(f"/api/calculations/{r.json()['record_id']}", headers=admin_headers).json()
    assert [it["material"].lower() for it in d["saved_result"]["items"]][:3] == \
        ["zebra seal", "alpha rivets", "middle glue"]


def test_a_line_whose_template_row_was_deleted_still_shows(client, admin_headers, saved, body):
    """The row a line pointed at can be removed from the template after the save. The line
    keys on its stored position instead — it is still listed, and nothing errors."""
    from app.database import SessionLocal
    from app.services.bom_order import calculator_order, sort_orders_for_trailer
    with SessionLocal() as db:
        orders = sort_orders_for_trailer(db, body["tt"])
    orders.pop(body["rows"][0], None)             # as if ZETA PANEL's row were deleted
    d = client.get(f"/api/calculations/{saved}", headers=admin_headers).json()
    got = calculator_order(d["saved_result"]["items"], orders)
    assert sorted(_names(got)) == sorted(EXPECTED)
