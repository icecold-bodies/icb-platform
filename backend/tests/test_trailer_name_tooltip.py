"""v1.44 — Body Type dropdown: original (pre-rename) template name as tooltip.

Nadie renamed imported templates to friendlier names (e.g. "UP TO 5.5 CHILLER
AND 2.3 WIDE" → "CHILLER MEDIUM"); staff cross-referencing the old Excel
sheets still need the old name. The Excel importers stamp
TrailerType.description with "Imported from …{original sheet name}" — the same
string Admin / Trailer Templates shows as each template's subtitle — so the
calculators' server-rendered Body Type <option>s now carry
title="Previously: {original}" when that original differs from the current
name. Never-renamed, hand-described and description-less templates get no
title attribute (no noise), and the visible option text stays the plain name.

Covers:
  1. original_template_name() extraction — all three importer prefix variants,
     identical-name suppression (case-insensitive), hand-written / empty
     descriptions.
  2. Rendered /calculator + /calculator2 pages: a renamed template's option
     carries the tooltip, an un-renamed one does not, and originals containing
     & / quotes / angle brackets are HTML-escaped inside the attribute.

Sessions are real UserSession rows sent via a raw Cookie header — the page
routes use the inline get_current_user chokepoint, which dependency_overrides
never reach (banked pattern).
"""
import re
import uuid

import pytest

from app.templates_config import original_template_name


# ── 1. extraction helper ──────────────────────────────────────────────────────
@pytest.mark.parametrize("name,description,expected", [
    # the three importer prefix variants (excel_importer.py / import_excel.py)
    ("CHILLER MEDIUM", "Imported from UP TO 5.5 CHILLER AND 2.3 WIDE",
     "UP TO 5.5 CHILLER AND 2.3 WIDE"),
    ("CHILLER MEDIUM", "Imported from sheet: UP TO 5.5 CHILLER AND 2.3 WIDE",
     "UP TO 5.5 CHILLER AND 2.3 WIDE"),
    ("GRP BODY", "Imported from GRP sheet: OLD GRP SHEET", "OLD GRP SHEET"),
    # identical current name → suppressed (case-insensitive, whitespace-insensitive)
    ("SAME NAME", "Imported from SAME NAME", None),
    ("Same Name", "Imported from sheet: SAME NAME", None),
    ("SAME NAME", "Imported from   SAME NAME  ", None),
    # not an import stamp → no tooltip
    ("X", "Hand-written description", None),
    ("X", "", None),
    ("X", None, None),
    # degenerate stamp with no sheet name → no tooltip
    ("X", "Imported from", None),
    ("X", "Imported from sheet:", None),
    # prefix match is case-insensitive but the original keeps its own casing
    ("NEW", "imported from Old Friendly Name", "Old Friendly Name"),
])
def test_original_template_name(name, description, expected):
    assert original_template_name(name, description) == expected


# ── 2. rendered dropdowns ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:   # triggers startup → seeds admin + permissions
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    """Real UserSession + raw Cookie header."""
    from app.database import SessionLocal, User, UserSession
    sid = f"v144tt-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin").first()
        assert u, "admin user missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role,
                             expires_at=None, csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}"}


@pytest.fixture(scope="module")
def seeded(app_mod):
    """Three throwaway trailers: renamed, never-renamed, renamed-with-specials."""
    from app.database import SessionLocal, TrailerType
    sfx = uuid.uuid4().hex[:6].upper()
    rows = {
        "renamed":  (f"V144TT CHILLER {sfx}",
                     f"Imported from V144TT ORIGINAL LONG NAME {sfx}"),
        "plain":    (f"V144TT PLAIN {sfx}",
                     f"Imported from V144TT PLAIN {sfx}"),   # identical → no tooltip
        "specials": (f"V144TT SPECIALS {sfx}",
                     f'Imported from R&D "COLD" <WIDE> {sfx}'),
    }
    ids = {}
    with SessionLocal() as db:
        for key, (name, desc) in rows.items():
            tt = TrailerType(name=name, description=desc)
            db.add(tt)
            db.flush()
            ids[key] = tt.id
        db.commit()
    yield {"ids": ids, "sfx": sfx}
    with SessionLocal() as db:
        db.query(TrailerType).filter(
            TrailerType.id.in_(list(ids.values()))).delete(synchronize_session=False)
        db.commit()


def _option_tag(html: str, tt_id: int) -> str:
    m = re.search(rf'<option value="{tt_id}"[^>]*>', html)
    assert m, f"option for trailer {tt_id} not rendered"
    return m.group(0)


@pytest.mark.parametrize("page", ["/calculator", "/calculator2"])
def test_dropdown_tooltip_rendering(client, admin_headers, seeded, page):
    r = client.get(page, headers=admin_headers)
    assert r.status_code == 200, r.text[:300]
    html, ids, sfx = r.text, seeded["ids"], seeded["sfx"]

    # Renamed template → title carries the original; visible text stays the name.
    renamed = _option_tag(html, ids["renamed"])
    assert f'title="Previously: V144TT ORIGINAL LONG NAME {sfx}"' in renamed
    assert f'>V144TT CHILLER {sfx}</option>' in html

    # Never-renamed (description == name) → no title attribute at all.
    assert "title=" not in _option_tag(html, ids["plain"])

    # Specials are escaped inside the attribute (markupsafe: & " < >).
    specials = _option_tag(html, ids["specials"])
    assert (f'title="Previously: R&amp;D &#34;COLD&#34; &lt;WIDE&gt; {sfx}"'
            in specials)


def test_dropdown_requires_login(client, seeded):
    """Unauthenticated /calculator redirects to /login — the tooltip change
    must not alter the page's auth gate."""
    r = client.get("/calculator", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/login" in r.headers.get("location", "")
