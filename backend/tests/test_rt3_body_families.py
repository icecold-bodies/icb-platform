"""RT3 — body families in colour (RT3_DISPATCH; RT3_RULING_1 + 1a: the light MES skin only).

A body's family is its trailer group. Migration 0051 gave the group a colour and an order; services/body_family.py
derives ONE text ink on the MES skin's two backgrounds (#FFFFFF inputs, #F5F7FB page) and is the one source every
surface reads. These tests pin:

  1. the contrast rule: the six approved colours clear 3:1 (bars) and their inks 4.6:1 (text); a too-light
     colour warns; the family object is exactly {id, name, colour, ink, sort_order}; the browser fallback grey
     is the server's;
  2. the BODY TYPE optgroups follow the database (names, order, members) on /mes/calculator;
  3. an admin colour / order / family change shows everywhere (bodies API, the calculator, the costings list API);
  4. only an admin changes a family (403 for everyone else) — the API, not the page, enforces it;
  5. a NEW body never lands grey by accident (POST /api/trailers, the Trailer Designer);
  6. the database refuses a malformed colour (ck_trailer_groups_colour);
  7. the committed swatches reference is exactly what the generator writes from the server's rule;
  8. the audit report's body headings carry the family chip when the admin page passes the families.

SYNTHETIC rows only (marker RT3F), in the _test database, removed by primary key.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

MARK = "RT3F"
ROOT = Path(__file__).resolve().parents[2]
APPROVED = {"EXPLOSIVE": "#E03131", "CHILLER": "#168ED9", "FREEZER": "#4263EB", "MEAT": "#D66A0B",
            "ICE CREAM": "#D63384", "OTHER": "#7D858C"}
MES_BACKGROUNDS = ("#ffffff", "#f5f7fb")


# ── 1. the contrast rule ─────────────────────────────────────────────────────

def test_the_six_approved_colours_pass_on_the_mes_skin():
    from app.services import body_family as bf
    for name, colour in APPROVED.items():
        k = bf.colour_check(colour)
        assert k["ok"], (name, k)
        for bg in MES_BACKGROUNDS:
            assert bf.contrast(colour, bg) >= 3.0, (name, bg)
            assert bf.contrast(k["ink"], bg) >= 4.6, (name, bg, k["ink"])


def test_an_ink_is_the_colour_itself_when_it_already_reads_else_a_darker_tint():
    from app.services import body_family as bf
    assert bf.ink("#4263EB") == "#4263EB"                       # FREEZER already clears 4.6:1
    t = bf.ink("#168ED9")
    assert t != "#168ED9" and bf.luminance(t) < bf.luminance("#168ED9")


def test_a_colour_too_light_for_the_mes_skin_warns():
    from app.services import body_family as bf
    k = bf.colour_check("#38bdf8")                              # the bright sky blue: 2:1 on #F5F7FB
    assert k["colour"] == "#38BDF8" and not k["ok"] and k["bar"] < 3.0


def test_malformed_colours_are_refused():
    from app.services import body_family as bf
    for bad in (None, "", "red", "#abc", "#12345G", "168ED9"):
        assert bf.normalise(bad) is None
    with pytest.raises(ValueError):
        bf.colour_check("red")


def test_the_family_object_is_exactly_the_ratified_shape():
    from app.services import body_family as bf
    f = bf.fallback_family()
    assert set(f) == {"id", "name", "colour", "ink", "sort_order"}
    assert (f["id"], f["name"], f["colour"]) == (None, "OTHER", "#7D858C")
    js = (ROOT / "backend" / "app" / "static" / "js" / "body_family.js").read_text(encoding="utf-8")
    m = re.search(r"var FALLBACK = \{[^}]*colour: '(#[0-9A-F]{6})', ink: '(#[0-9A-F]{6})'", js)
    assert m and m.groups() == (f["colour"], f["ink"]), "the browser's fallback grey drifted from the server's"


@pytest.mark.parametrize("name,family", [
    ("STANDARD CHILLER 6.1M", "CHILLER"), ("EXPLOSIVE 9 TON", "EXPLOSIVE"), ("FREEZER XL", "FREEZER"),
    ("MEAT HANGER 7M", "MEAT"), ("ICECREAM BODY XL", "ICE CREAM"), ("ICE CREAM VAN", "ICE CREAM"),
    ("RHINORANGE FREEZER", "OTHER"), ("TAUT LINER", "OTHER"), ("", "OTHER"),
])
def test_a_new_body_name_suggests_its_family(name, family):
    from app.services import body_family as bf
    assert bf.guess_family_name(name) == family


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
    sid = f"rt3f-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def users(app_mod):
    from app.database import SessionLocal, User, UserSession
    made = {}
    with SessionLocal() as db:
        for role in ("sales", "full", "user"):
            uname = f"{MARK.lower()}_{role}_{uuid.uuid4().hex[:6]}"
            db.add(User(username=uname, password_hash="x", role=role))
            made[role] = uname
        db.commit()
    heads = {role: _session(u) for role, u in made.items()}
    heads["admin"] = _session("admin")
    yield heads
    with SessionLocal() as db:
        for h in heads.values():
            db.query(UserSession).filter_by(id=h["Cookie"].split("session_id=")[1]).delete()
        for uname in made.values():
            db.query(User).filter_by(username=uname).delete()
        db.commit()


@pytest.fixture()
def fams(app_mod):
    """Two synthetic families (ordered AFTER every real group) and three bodies: one in each, one in none.
    Every row is removed by primary key, child-first."""
    from app.database import CalculationRecord, SessionLocal, TrailerGroup, TrailerType
    with SessionLocal() as db:
        ga = TrailerGroup(name=f"{MARK} ALPHA", colour="#E03131", sort_order=9001)
        gb = TrailerGroup(name=f"{MARK} BETA", colour="#168ED9", sort_order=9002)
        db.add_all([ga, gb])
        db.flush()
        ta = TrailerType(name=f"{MARK} BODY IN ALPHA", is_active=True, group_id=ga.id)
        tb = TrailerType(name=f"{MARK} BODY IN BETA", is_active=True, group_id=gb.id)
        tn = TrailerType(name=f"{MARK} BODY IN NONE", is_active=True)
        db.add_all([ta, tb, tn])
        db.flush()
        rec = CalculationRecord(trailer_type_id=ta.id, dimensions_json="{}", result_json='{"items": []}',
                                status="pending")
        db.add(rec)
        db.commit()
        ids = {"ga": ga.id, "gb": gb.id, "ta": ta.id, "tb": tb.id, "tn": tn.id, "rec": rec.id, "extra_groups": [],
               "extra_bodies": []}
    yield ids
    with SessionLocal() as db:
        db.query(CalculationRecord).filter_by(id=ids["rec"]).delete()
        db.query(TrailerType).filter(TrailerType.id.in_([ids["ta"], ids["tb"], ids["tn"], *ids["extra_bodies"]])).delete(
            synchronize_session=False)
        db.query(TrailerGroup).filter(TrailerGroup.id.in_([ids["ga"], ids["gb"], *ids["extra_groups"]])).delete(
            synchronize_session=False)
        db.commit()


def _row(client, headers, tid):
    rows = client.get("/api/trailers", headers=headers).json()
    return next(r for r in rows if r["id"] == tid)


def _body_type_select(html: str) -> str:
    i = html.index('id="trailer-select"')
    return html[i:html.index("</select>", i)]


def _optgroups(html: str) -> list[tuple[str, list[str]]]:
    """[(label, [option values])] of the BODY TYPE select, in page order."""
    sel = _body_type_select(html)
    out = []
    for m in re.finditer(r'<optgroup label="([^"]*)"(.*?)</optgroup>', sel, re.S):
        out.append((m.group(1), re.findall(r'<option value="([^"]+)"', m.group(2))))
    return out


def _edit_group(client, headers, gid, **form):
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        g = db.get(TrailerGroup, gid)
        data = {"name": g.name, "description": g.description or "", "report_template_id": g.report_template_id or "",
                "colour": g.colour or "", "sort_order": str(g.sort_order)}
    data.update(form)
    return client.post(f"/admin/quote-templates/groups/{gid}/edit", headers=headers, data=data, follow_redirects=False)


# ── the bodies API carries the family ─────────────────────────────────────────

def test_every_body_row_carries_its_family(client, users, fams):
    from app.services import body_family as bf
    a = _row(client, users["admin"], fams["ta"])["family"]
    assert a == {"id": fams["ga"], "name": f"{MARK} ALPHA", "colour": "#E03131", "ink": bf.ink("#E03131"),
                 "sort_order": 9001}
    assert _row(client, users["sales"], fams["tb"])["family"]["name"] == f"{MARK} BETA"   # read by anyone signed in


def test_a_body_with_no_family_shows_as_other(client, users, fams):
    from app.database import SessionLocal, TrailerGroup
    from sqlalchemy import func
    with SessionLocal() as db:
        other = db.query(TrailerGroup).filter(func.upper(TrailerGroup.name) == "OTHER").first()
        made = None
        if other is None:          # first the fallback grey, then a real OTHER group takes over
            f = _row(client, users["admin"], fams["tn"])["family"]
            assert (f["id"], f["name"], f["colour"]) == (None, "OTHER", "#7D858C")
            made = TrailerGroup(name="OTHER", colour="#7D858C", sort_order=9006)
            db.add(made)
            db.commit()
            fams["extra_groups"].append(made.id)
            other = made
        f = _row(client, users["admin"], fams["tn"])["family"]
        assert (f["id"], f["name"]) == (other.id, other.name)


# ── 2. the BODY TYPE optgroups follow the database ────────────────────────────

def test_the_body_type_optgroups_follow_the_database(client, users, fams):
    page = client.get("/mes/calculator", headers=users["admin"]).text
    groups = _optgroups(page)
    labels = [g for g, _ in groups]
    assert labels[-1] == "──────────" and groups[-1][1] == ["repair"], "REPAIRS must stay its own last group"
    ia, ib = labels.index(f"{MARK} ALPHA"), labels.index(f"{MARK} BETA")
    assert ia < ib, "the families must follow sort_order"
    assert str(fams["ta"]) in groups[ia][1] and str(fams["tb"]) in groups[ib][1]
    sel = _body_type_select(page)
    opt = re.search(rf'<option value="{fams["ta"]}"[^>]*>', sel).group(0)
    assert 'class="fam-ink"' in opt and "--fam:#E03131" in opt and 'data-fam-name="RT3F ALPHA"' in opt
    assert 'class="fam-select-wrap"' in page[:page.index('id="trailer-select"')][-400:], "the closed box needs its bar"

    # the admin moves ALPHA after BETA: the dropdown follows
    assert _edit_group(client, users["admin"], fams["ga"], sort_order="9003").status_code == 303
    labels = [g for g, _ in _optgroups(client.get("/mes/calculator", headers=users["admin"]).text)]
    assert labels.index(f"{MARK} BETA") < labels.index(f"{MARK} ALPHA")


def test_the_enter_chain_still_starts_at_the_body_type_select():
    """The family wrapper must not take the select out of the Enter chain or rename it."""
    js = (ROOT / "backend" / "app" / "static" / "js" / "calculator.js").read_text(encoding="utf-8")
    assert "const ENTER_CHAIN = ['trailer-select', 'f-length', 'f-width', 'f-height', 'f-margin', 'f-ratio'];" in js
    html = (ROOT / "backend" / "app" / "templates" / "calculator.html").read_text(encoding="utf-8")
    assert html.count('<select id="trailer-select" onchange="loadBOM()">') == 1


# ── 3. an admin change shows everywhere ──────────────────────────────────────

def test_an_admin_colour_change_shows_on_the_api_the_calculator_and_the_costings_list(client, users, fams):
    from app.services import body_family as bf
    r = _edit_group(client, users["admin"], fams["ga"], colour="#4263eb")
    assert r.status_code == 303, r.text
    assert _row(client, users["admin"], fams["ta"])["family"]["colour"] == "#4263EB"
    sel = _body_type_select(client.get("/mes/calculator", headers=users["admin"]).text)
    assert "--fam:#4263EB" in re.search(rf'<option value="{fams["ta"]}"[^>]*>', sel).group(0)
    rows = client.get("/api/calculations", params={"limit": 2000}, headers=users["admin"]).json()
    row = next(x for x in rows if x["id"] == fams["rec"])
    assert row["trailer_family"] == {"id": fams["ga"], "name": f"{MARK} ALPHA", "colour": "#4263EB",
                                     "ink": bf.ink("#4263EB"), "sort_order": 9001}


def test_an_admin_moving_a_body_to_another_family_shows_everywhere(client, users, fams):
    r = client.post(f"/admin/quote-templates/trailer/{fams['ta']}/assign", headers=users["admin"],
                    data={"group_id": str(fams["gb"]), "override_report_template_id": ""}, follow_redirects=False)
    assert r.status_code == 303
    assert _row(client, users["admin"], fams["ta"])["family"]["name"] == f"{MARK} BETA"
    groups = dict(_optgroups(client.get("/mes/calculator", headers=users["admin"]).text))
    assert str(fams["ta"]) in groups[f"{MARK} BETA"] and f"{MARK} ALPHA" not in groups   # ALPHA is empty now
    rows = client.get("/api/calculations", params={"limit": 2000}, headers=users["admin"]).json()
    assert next(x for x in rows if x["id"] == fams["rec"])["trailer_family"]["name"] == f"{MARK} BETA"


def test_a_family_rename_and_a_bad_colour(client, users, fams):
    assert _edit_group(client, users["admin"], fams["gb"], name=f"{MARK} GAMMA").status_code == 303
    assert _row(client, users["admin"], fams["tb"])["family"]["name"] == f"{MARK} GAMMA"
    assert _edit_group(client, users["admin"], fams["gb"], colour="blue").status_code == 400
    assert _edit_group(client, users["admin"], fams["gb"], sort_order="first").status_code == 400
    assert _edit_group(client, users["admin"], fams["gb"], name=f"{MARK} ALPHA").status_code == 400   # name clash
    assert _row(client, users["admin"], fams["tb"])["family"]["colour"] == "#168ED9"   # nothing half-saved


def test_the_admin_colour_check_uses_the_server_rule(client, users):
    from app.services import body_family as bf
    k = client.get("/api/admin/body-families/colour-check", params={"colour": "#38BDF8"}, headers=users["admin"]).json()
    assert k == bf.colour_check("#38BDF8") and k["ok"] is False
    assert client.get("/api/admin/body-families/colour-check", params={"colour": "x"},
                      headers=users["admin"]).status_code == 400


# ── 4. only an admin ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["sales", "full", "user"])
def test_a_non_admin_cannot_change_a_family(client, users, fams, role):
    h = users[role]
    form = {"name": f"{MARK} HACK", "description": "", "report_template_id": "", "colour": "#000000", "sort_order": "1"}
    assert client.post(f"/admin/quote-templates/groups/{fams['ga']}/edit", headers=h, data=form,
                       follow_redirects=False).status_code == 403
    assert client.post("/admin/quote-templates/groups/new", headers=h, data=form,
                       follow_redirects=False).status_code == 403
    assert client.post(f"/admin/quote-templates/trailer/{fams['ta']}/assign", headers=h,
                       data={"group_id": str(fams["gb"])}, follow_redirects=False).status_code == 403
    assert client.post(f"/admin/quote-templates/groups/{fams['ga']}/delete", headers=h,
                       follow_redirects=False).status_code == 403
    assert client.get("/api/admin/body-families", headers=h).status_code == 403
    assert client.get("/api/admin/body-families/colour-check", params={"colour": "#000000"}, headers=h).status_code == 403
    assert client.post("/api/trailer-designer/save", headers=h, json={"name": f"{MARK} HACK"}).status_code == 403
    a = _row(client, users["admin"], fams["ta"])["family"]
    assert (a["name"], a["colour"], a["sort_order"]) == (f"{MARK} ALPHA", "#E03131", 9001)


# ── 5. a new body never lands grey by accident ───────────────────────────────

def _cleanup_body(name):
    from app.database import BillOfMaterial, SessionLocal, TrailerType
    with SessionLocal() as db:
        for t in db.query(TrailerType).filter_by(name=name).all():
            db.query(BillOfMaterial).filter_by(trailer_type_id=t.id).delete()
            db.delete(t)
        db.commit()


def test_a_new_body_gets_the_family_its_name_suggests_or_the_one_picked(client, users, fams):
    from app.database import SessionLocal, TrailerGroup, TrailerType
    from sqlalchemy import func
    with SessionLocal() as db:
        chiller = db.query(TrailerGroup).filter(func.upper(TrailerGroup.name) == "CHILLER").first()
        if chiller is None:
            chiller = TrailerGroup(name="CHILLER", colour="#168ED9", sort_order=9007)
            db.add(chiller)
            db.commit()
            fams["extra_groups"].append(chiller.id)
        cid = chiller.id
    names = [f"{MARK} NEW CHILLER A", f"{MARK} NEW CHILLER B", f"{MARK} NEW PICKED", f"{MARK} NEW BAD"]
    try:
        r = client.post("/api/trailers", headers=users["admin"], json={"name": names[0]})
        assert r.status_code == 200 and r.json()["family"]["id"] == cid, r.text
        r = client.post("/api/trailer-designer/save", headers=users["admin"], json={"name": names[1], "zones": {}})
        assert r.status_code == 200, r.text
        r = client.post("/api/trailer-designer/save", headers=users["admin"],
                        json={"name": names[2], "zones": {}, "group_id": fams["gb"]})
        assert r.status_code == 200, r.text
        r = client.post("/api/trailer-designer/save", headers=users["admin"],
                        json={"name": names[3], "zones": {}, "group_id": 99999999})
        assert r.status_code == 400
        with SessionLocal() as db:
            got = {t.name: t.group_id for t in db.query(TrailerType).filter(TrailerType.name.in_(names)).all()}
        assert got == {names[0]: cid, names[1]: cid, names[2]: fams["gb"]}
    finally:
        for n in names:
            _cleanup_body(n)


def test_the_designer_page_offers_a_required_family_select(client, users, fams):
    page = client.get("/admin/trailer-designer", headers=users["admin"]).text
    i = page.index('id="setup-family"')
    tag = page[page.rindex("<select", 0, i):page.index(">", i)]
    assert "required" in tag
    assert f'data-fam-name="{MARK} ALPHA"' in page
    assert re.search(r"const FAMILY_KEYWORDS = \[.*\"CHILLER\".*\];", page)


# ── 6. the database refuses a malformed colour ───────────────────────────────

def test_the_database_refuses_a_malformed_colour(app_mod):
    import sqlalchemy as sa
    from app.database import engine
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as c:
            c.execute(sa.text("INSERT INTO trailer_groups (name, colour, sort_order) VALUES (:n, 'red', 1)"),
                      {"n": f"{MARK} BAD {uuid.uuid4().hex[:6]}"})


# ── 7. the swatches reference = the generator ────────────────────────────────

def test_the_committed_swatches_are_what_the_generator_writes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rt3_swatches", ROOT / "backend" / "tools" / "rt3_swatches.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "rt3" / "body_family_swatches.html").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == mod.render(), "re-run python backend/tools/rt3_swatches.py"
    assert "<script" not in committed, "the reference must render with scripts blocked"
    for colour in APPROVED.values():
        assert colour in committed


# ── 8. the audit report's body headings ──────────────────────────────────────

def test_the_audit_report_carries_family_chips_only_when_given_the_families():
    from tools.costing_audit.report import render_html_doc
    d = {"pack": "t", "cells": [{"scenario_id": "s1", "sheet": "X", "trailer_id": 5, "status": "PASS"}],
         "scenarios": [], "counts": {"PASS": 1}}
    fam = {"id": 1, "name": "CHILLER", "colour": "#168ED9", "ink": "#1272AE", "sort_order": 2}
    with_f = render_html_doc(d, families={5: fam})
    assert "window.__FAMILIES__ = " + json.dumps({"5": fam}) in with_f
    assert "__FAMILIES__ =" not in render_html_doc(d)
