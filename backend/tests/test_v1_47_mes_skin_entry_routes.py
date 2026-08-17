"""v1.47 Lane A — MES calculator-entry routes must carry the light-skin context.

Nadie, 17 Aug: viewing an APPROVED costing and clicking "⧉ Duplicate" opened the
calculator in the legacy DARK skin. Root cause was not the theme — it was the
NAVIGATION layer: results.html hardcoded `/calculator?from={id}`, so the hop out of
the MES-skinned results page (results_mes.html, served at /results/{id}?skin=mes and
iframed by /mes-app/costings/results/:id) landed on the unskinned legacy route.

These tests assert the SKIN MARKER, not pixels:
  * the entry link's target (which route the user is sent to), and
  * `theme-mes.css` in the destination's HTML (base.html loads it only in MES context).

The negative controls matter as much as the positives: the standalone dark app at
/results/{id} and /calculator must stay bit-for-bit unskinned (the WO v4.7 constraint).
A fix that skinned everything would pass the positives and fail here.

Also guards the Lane A removals (the two surface-area displays) against re-entry.

Auth uses the raw-Cookie-header UserSession pattern and a directly-seeded costing row
(test_legacy_frontdoor.py precedent — the /api/approve pipeline needs a full BOM
universe the test DB does not carry). Marker rows ZSKN* purged both sides.
"""
import uuid
from pathlib import Path

import pytest

MARK = "ZSKN"

# Just enough result_json for results.html to render — the template pipes these
# through strict filters (|float) and iterates the dicts.
RESULT_JSON = ('{"items": [], "grand_total": 0, "selling_price": 0, "cost_per_sqm": 0, '
               '"profit_margin": 0, "profit_amount": 0, "ratio_label": "", "ratio_amount": 0, '
               '"geometry": {}, "category_totals": {}, "category_multipliers": {}}')

_STATIC = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
_TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


def _code_only(path: Path) -> str:
    """Source with whole-line `//` comments dropped. The removal comments below
    necessarily NAME the things they removed, so a raw substring search would match
    the explanation instead of the code and never fail when the code came back."""
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("//"))


@pytest.fixture
def admin_cookie():
    from app.database import SessionLocal, User, UserSession
    sid = "zzskn-session-1"
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        assert admin is not None, "seeded admin user missing"
        db.merge(UserSession(id=sid, user_id=admin.id, role=admin.role,
                             csrf_token="zzskn-csrf"))
        db.commit()
    yield {"Cookie": f"session_id={sid}"}
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.id.like("zzskn-%")).delete(
            synchronize_session=False)
        db.commit()


@pytest.fixture
def approved_costing():
    """An ACCEPTED costing — the exact state Nadie reported the bug from."""
    from app.database import CalculationRecord, SessionLocal
    quote = f"{MARK}{uuid.uuid4().hex[:5].upper()}"
    with SessionLocal() as db:
        rec = CalculationRecord(quote_number=quote, dimensions_json="{}",
                                result_json=RESULT_JSON, status="accepted")
        db.add(rec)
        db.commit()
        rec_id = rec.id
    yield {"id": rec_id, "quote": quote}
    with SessionLocal() as db:
        for r in db.query(CalculationRecord).filter(
                CalculationRecord.quote_number.like(f"{MARK}%")).all():
            db.delete(r)
        db.commit()


# ── A2: the reported defect ──────────────────────────────────────────────────

def test_duplicate_on_mes_results_targets_the_skinned_calculator(
        client, admin_cookie, approved_costing):
    """THE BUG. Duplicate from an MES-skinned approved costing must point at the
    /mes/ calculator fork, never the bare legacy /calculator."""
    rid = approved_costing["id"]
    r = client.get(f"/results/{rid}?skin=mes", headers=admin_cookie)
    assert r.status_code == 200
    assert "theme-mes.css" in r.text, "precondition: this page is MES-skinned"
    assert f'href="/mes/calculator?from={rid}"' in r.text
    assert f'href="/calculator?from={rid}"' not in r.text


def test_duplicate_destination_actually_renders_light(client, admin_cookie,
                                                      approved_costing):
    """Following the Duplicate link lands on a page carrying the light-skin marker —
    the end-state assertion, not just the href."""
    rid = approved_costing["id"]
    dest = client.get(f"/mes/calculator?from={rid}", headers=admin_cookie)
    assert dest.status_code == 200
    assert "Cost Calculator" in dest.text
    assert "theme-mes.css" in dest.text


def test_breadcrumb_on_mes_results_is_skinned(client, admin_cookie, approved_costing):
    """Same class of hop, same page: the "Calculator" breadcrumb.

    Matched on the FULL breadcrumb anchor, not a bare `href="/mes/calculator"` —
    base.html's sidebar emits that same href in MES context, so the loose form
    passed even with results.html unfixed (caught by the negative control)."""
    crumb = ('<a href="{}" style="color:var(--text-dim);text-decoration:none">'
             'Calculator</a>')
    r = client.get(f"/results/{approved_costing['id']}?skin=mes", headers=admin_cookie)
    assert crumb.format("/mes/calculator") in r.text
    assert crumb.format("/calculator") not in r.text


# ── A2 negative controls: the standalone dark app stays pristine ─────────────

def test_plain_results_keeps_the_legacy_calculator_targets(client, admin_cookie,
                                                           approved_costing):
    """Without ?skin=mes the page is the dark standalone app — its links must NOT
    be rewritten to /mes/. This is what stops an over-broad 'skin everything' fix."""
    rid = approved_costing["id"]
    r = client.get(f"/results/{rid}", headers=admin_cookie)
    assert r.status_code == 200
    assert f'href="/calculator?from={rid}"' in r.text
    assert "/mes/calculator" not in r.text


def test_legacy_calculator_is_still_unskinned(client, admin_cookie):
    r = client.get("/calculator", headers=admin_cookie)
    assert r.status_code == 200
    assert "theme-mes.css" not in r.text


# ── A2 §6 route audit — the other MES calculator/results entries stay light ──

@pytest.mark.parametrize("path", [
    "/mes/calculator",            # New Costing  (LiveCalculator iframe target)
    "/mes/calculator?edit=1",     # Edit pending (dashboard deep-link → same iframe)
    "/mes/calculator2",           # Cost Calculator 2 fork
])
def test_mes_calculator_entry_routes_render_light(client, admin_cookie, path):
    r = client.get(path, headers=admin_cookie)
    assert r.status_code == 200
    assert "theme-mes.css" in r.text


def test_view_full_results_hop_is_skin_preserving():
    """calculator.js "View Full Results" was the one calculator→results hop that
    bypassed _skinnify, so it opened the results page unskinned from /mes/calculator."""
    js = (_STATIC / "calculator.js").read_text(encoding="utf-8")
    assert "window.open(_skinnify(`/results/${lastRecordId}`), '_blank');" in js


# ── A1: the two surface-area displays are gone and stay gone ─────────────────

def test_configuration_panel_has_no_surface_area_strip(client, admin_cookie):
    """The Wall/Roof/Floor/Front-Rear/Total m² footer under Configuration is removed
    (markup-level, so a plain render proves it)."""
    r = client.get("/mes/calculator", headers=admin_cookie)
    assert r.status_code == 200
    assert 'id="geo-summary"' not in r.text


def test_calculator_js_has_no_surface_area_renders():
    """The JS-rendered halves: updateGeo() (the strip) and the two COST SUMMARY
    geometry tiles. Asserted on source because both render client-side, and on CODE
    markers rather than label prose, over COMMENT-STRIPPED source — the removal
    comments name what was removed, so matching raw text would assert on the wrong
    thing (and pass/fail on how the comment is worded)."""
    js = _code_only(_STATIC / "calculator.js")
    assert "function updateGeo" not in js
    assert "updateGeo()" not in js
    assert "geo-summary" not in js
    # The tiles were the only geo-grid/geo-item markup calculator.js ever emitted.
    assert 'class="geo-grid"' not in js
    assert 'class="geo-item"' not in js


def test_geometry_still_reaches_the_client():
    """DISPLAY only was removed. result.geometry still feeds the formulas, and the
    formula-editor context still computes the areas — this fails if a later cleanup
    strips the computation itself."""
    js = (_STATIC / "calculator.js").read_text(encoding="utf-8")
    assert "surface_area: wall_area + roof_area + floor_area + front_rear_area" in js


def test_cache_bust_bumped():
    """A removal the browser never fetches is not a removal (stale-tab class)."""
    html = (_TEMPLATES / "calculator.html").read_text(encoding="utf-8")
    assert "calculator.js?v=157" in html
