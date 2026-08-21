"""v1.50 — the R-series gets an ADMIN SURFACE (Michael, 22 Aug).

`quote_counter` has been series-keyed since migration 0042, but
/admin/quote-numbering only ever addressed the body line: every handler called
`get_or_create_counter(db)` with no series. The repair R-series could therefore
only be moved by hand-written SQL — including the one that matters most, setting
prod's starting number BEFORE the first repair is ever saved there.

What these pin:

  * the page renders BOTH blocks, and opening it SEEDS the repair row (that
    seeding is the feature, not a side effect — it is what makes a pre-seed
    possible on a database that has never saved a repair)
  * the API is series-aware and the series ALLOW-LIST holds: an unknown series
    is a 400 and mints no counter row (get_or_create would happily create one)
  * omitting the series is byte-identical to today — same body row, same keys
  * the two series are ISOLATED in BOTH directions: editing either one moves
    neither the other's counter nor its template
  * a counter edit never renumbers a costing that already has a number

Sessions are real UserSession rows via raw Cookie headers (banked pattern).
"""
import uuid

import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:       # triggers startup → seeds permissions
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _make_session(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"v150qna-{uuid.uuid4().hex[:12]}"
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


def _row(series):
    """(next_value, format_template) for one series, read straight from the DB."""
    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter
    with SessionLocal() as db:
        qc = get_or_create_counter(db, series)
        db.commit()
        return int(qc.next_value), qc.format_template


@pytest.fixture()
def restore_counters(app_mod):
    """Both series are GLOBAL rows on a shared database — put them back exactly
    as they were, whatever the test did to them."""
    from app.quote_numbering import SERIES_QUOTE, SERIES_REPAIR_DOC
    before = {s: _row(s) for s in (SERIES_QUOTE, SERIES_REPAIR_DOC)}
    yield before
    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter
    with SessionLocal() as db:
        for series, (nv, tpl) in before.items():
            qc = get_or_create_counter(db, series)
            qc.next_value, qc.format_template = nv, tpl
        db.commit()


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_page_renders_both_series_blocks(client, admin_headers, restore_counters):
    r = client.get("/admin/quote-numbering", headers=admin_headers)
    assert r.status_code == 200, r.text
    html = r.text
    assert 'data-testid="qn-block-quote"' in html
    assert 'data-testid="qn-block-repair_doc"' in html
    assert "Body costing numbers" in html
    assert "Repair document numbers (R-series)" in html
    # Each block is seeded from its OWN row: the repair inputs must carry the
    # repair series' template and next value, not the body series'.
    from app.quote_numbering import SERIES_QUOTE, SERIES_REPAIR_DOC
    import re
    r_nv, r_tpl = _row(SERIES_REPAIR_DOC)
    q_nv, q_tpl = _row(SERIES_QUOTE)
    repair_tpl_input = re.search(r'id="qn-template-repair_doc"[^>]*value="([^"]*)"', html, re.S)
    repair_next_input = re.search(r'id="qn-next-repair_doc"[^>]*value="([^"]*)"', html, re.S)
    assert repair_tpl_input and repair_tpl_input.group(1) == r_tpl
    assert repair_next_input and repair_next_input.group(1) == str(r_nv)
    body_tpl_input = re.search(r'id="qn-template"[^>]*value="([^"]*)"', html, re.S)
    body_next_input = re.search(r'id="qn-next"[^>]*value="([^"]*)"', html, re.S)
    assert body_tpl_input and body_tpl_input.group(1) == q_tpl
    assert body_next_input and body_next_input.group(1) == str(q_nv)


def test_opening_the_page_seeds_the_repair_row(client, admin_headers, restore_counters):
    """The pre-seed path: on a database that has never saved a repair there is no
    repair_doc row at all, so there is nothing to edit. Opening the screen must
    create it — that is what lets prod's starting R-number be set up front."""
    from app.database import SessionLocal, QuoteCounter
    from app.quote_numbering import SERIES_REPAIR_DOC, DEFAULT_TEMPLATES
    with SessionLocal() as db:
        db.query(QuoteCounter).filter_by(series=SERIES_REPAIR_DOC).delete()
        db.commit()
        assert db.query(QuoteCounter).filter_by(series=SERIES_REPAIR_DOC).first() is None

    assert client.get("/admin/quote-numbering", headers=admin_headers).status_code == 200

    with SessionLocal() as db:
        seeded = db.query(QuoteCounter).filter_by(series=SERIES_REPAIR_DOC).first()
    assert seeded is not None, "opening the page did not seed the repair series"
    assert seeded.next_value == 1
    assert seeded.format_template == DEFAULT_TEMPLATES[SERIES_REPAIR_DOC]


# ── the API: default series is byte-compatible ───────────────────────────────

def test_get_without_a_series_is_the_body_series_and_the_same_shape(
        client, admin_headers, restore_counters):
    """Every pre-v1.50 caller sends no series. Same row, same keys, same order."""
    from app.quote_numbering import SERIES_QUOTE
    r = client.get("/api/quote-numbering", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert list(body.keys()) == ["next_value", "format_template", "preview", "placeholders"]
    nv, tpl = _row(SERIES_QUOTE)
    assert body["next_value"] == nv
    assert body["format_template"] == tpl


def test_get_with_the_repair_series_returns_the_repair_row(
        client, admin_headers, restore_counters):
    from app.quote_numbering import SERIES_REPAIR_DOC
    r = client.get("/api/quote-numbering?series=repair_doc", headers=admin_headers)
    assert r.status_code == 200, r.text
    nv, tpl = _row(SERIES_REPAIR_DOC)
    assert r.json()["next_value"] == nv
    assert r.json()["format_template"] == tpl


def test_put_without_a_series_still_edits_the_body_series(
        client, admin_headers, restore_counters):
    from app.quote_numbering import SERIES_QUOTE, SERIES_REPAIR_DOC
    repair_before = _row(SERIES_REPAIR_DOC)
    r = client.put("/api/quote-numbering",
                   json={"next_value": 7777, "format_template": "{counter}/BODY"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    assert list(r.json().keys()) == ["ok", "next_value", "format_template", "preview"]
    assert _row(SERIES_QUOTE) == (7777, "{counter}/BODY")
    assert _row(SERIES_REPAIR_DOC) == repair_before, "a body edit moved the repair series"


# ── the allow-list ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("call", ["get", "put", "preview"])
def test_an_unknown_series_is_a_400_and_mints_no_row(
        client, admin_headers, restore_counters, call):
    """get_or_create_counter would happily CREATE a row for any string handed to
    it, so an unvalidated ?series= is a route to arbitrary counter rows. The
    allow-list has to reject before the lookup, not after."""
    from app.database import SessionLocal, QuoteCounter
    with SessionLocal() as db:
        before = db.query(QuoteCounter).count()

    if call == "get":
        r = client.get("/api/quote-numbering?series=nonsense", headers=admin_headers)
    elif call == "put":
        r = client.put("/api/quote-numbering",
                       json={"series": "nonsense", "next_value": 5}, headers=admin_headers)
    else:
        r = client.post("/api/quote-numbering/preview",
                        json={"series": "nonsense", "format_template": "{counter}"},
                        headers=admin_headers)
    assert r.status_code == 400, r.text
    assert "nonsense" in r.json()["detail"]

    with SessionLocal() as db:
        assert db.query(QuoteCounter).count() == before, \
            "a rejected series still created a counter row"


# ── isolation, BOTH directions ───────────────────────────────────────────────

def test_editing_the_repair_series_moves_neither_body_counter_nor_body_template(
        client, admin_headers, restore_counters):
    from app.quote_numbering import SERIES_QUOTE, SERIES_REPAIR_DOC
    body_before = _row(SERIES_QUOTE)
    r = client.put("/api/quote-numbering",
                   json={"series": "repair_doc", "next_value": 100,
                         "format_template": "R-{counter:04d}"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["preview"] == "R-2547"          # sample counter 2547, 4-padded
    assert _row(SERIES_REPAIR_DOC) == (100, "R-{counter:04d}")
    assert _row(SERIES_QUOTE) == body_before, "editing the R-series moved the body series"


def test_editing_the_body_series_moves_neither_repair_counter_nor_repair_template(
        client, admin_headers, restore_counters):
    from app.quote_numbering import SERIES_QUOTE, SERIES_REPAIR_DOC
    repair_before = _row(SERIES_REPAIR_DOC)
    r = client.put("/api/quote-numbering",
                   json={"series": "quote", "next_value": 4242,
                         "format_template": "{user_initial}{counter}/{year}"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    assert _row(SERIES_QUOTE) == (4242, "{user_initial}{counter}/{year}")
    assert _row(SERIES_REPAIR_DOC) == repair_before, \
        "editing the body series moved the R-series"


# ── validation is the SAME for both series ───────────────────────────────────

@pytest.mark.parametrize("series", ["quote", "repair_doc"])
def test_validation_is_identical_on_both_series(client, admin_headers,
                                                restore_counters, series):
    for bad_next in (0, -1, "abc"):
        r = client.put("/api/quote-numbering",
                       json={"series": series, "next_value": bad_next},
                       headers=admin_headers)
        assert r.status_code == 400, f"next_value={bad_next!r} was accepted on {series}"
    r = client.put("/api/quote-numbering",
                   json={"series": series, "format_template": "{nope}{counter}"},
                   headers=admin_headers)
    assert r.status_code == 400
    assert "nope" in r.json()["detail"]
    # ...and a template with no {counter} at all
    r = client.put("/api/quote-numbering",
                   json={"series": series, "format_template": "FIXED"},
                   headers=admin_headers)
    assert r.status_code == 400


def test_a_repair_template_without_the_R_prefix_still_saves(
        client, admin_headers, restore_counters):
    """Defaults §3: the R- convention is the admin's, so the screen NOTES a
    missing prefix but never blocks it. The server must not sneak a rule in."""
    r = client.put("/api/quote-numbering",
                   json={"series": "repair_doc", "format_template": "REP{counter}"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["preview"] == "REP2547"


@pytest.mark.parametrize("series", ["quote", "repair_doc"])
def test_lowering_the_next_value_is_accepted_server_side(
        client, admin_headers, restore_counters, series):
    """The warning is a UI confirm (defaults §4); the server keeps the body
    series' long-standing permissive behaviour, on both series alike."""
    client.put("/api/quote-numbering", json={"series": series, "next_value": 500},
               headers=admin_headers)
    r = client.put("/api/quote-numbering", json={"series": series, "next_value": 5},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["next_value"] == 5


# ── the invariant ────────────────────────────────────────────────────────────

def test_a_counter_edit_never_renumbers_a_saved_costing(
        client, admin_headers, restore_counters):
    """Numbers are frozen onto the record at issue time (quote_number; and for
    repairs, result_json.repair_document_number). Moving a counter can only
    affect what is issued NEXT."""
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = CalculationRecord(dimensions_json="{}", result_json='{"items": []}',
                                status="pending", quote_number="V150QNA-FROZEN/08/2026")
        db.add(rec)
        db.commit()
        rec_id = rec.id
    try:
        for series, nv in (("quote", 91000), ("repair_doc", 92000)):
            assert client.put("/api/quote-numbering",
                              json={"series": series, "next_value": nv,
                                    "format_template": "{counter}-MOVED"},
                              headers=admin_headers).status_code == 200
        with SessionLocal() as db:
            again = db.get(CalculationRecord, rec_id)
            assert again.quote_number == "V150QNA-FROZEN/08/2026", \
                "a counter edit renumbered an already-saved costing"
    finally:
        with SessionLocal() as db:
            r = db.get(CalculationRecord, rec_id)
            if r:
                db.delete(r)
            db.commit()
