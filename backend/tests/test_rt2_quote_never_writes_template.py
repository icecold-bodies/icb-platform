"""RT2 Part 1 + 1c — a quote never writes the Body Template; a new costing opens on its
BODY's default foam grade (RT2_DISPATCH Part 1, RT2_RULING_1 R2 / R3 / R6).

What these server/unit tests hold (the browser side is in
tests/journeys/test_rt2_quote_state_journey.py):

  1. NO CALCULATOR WRITES A THICKNESS. calculator.js and calculator2.js carry no
     `PUT /api/bom` whose body holds `variable_value` (the eight + four writers of
     RT2_RETURN_1 §1.2), and nothing reads the old per-browser foam memory.
  2. THE PRICE FOLLOWS THE QUOTE. A thickness sent as body_variable_overrides — the
     channel the quote's overlay now rides — reaches the formula, while the template
     row the server reads stays as it was.
  3. R2 — BOTH SIDES. A variable_value-only PUT is refused for every non-admin with the
     ruled message, and the template is unchanged; an admin's Body Templates save (a
     full body) and an admin's thickness-only PUT still work. (test_preview_formats.py
     holds the sales/full/admin matrix on its own fixture.)
  4. R6 — THE PER-BODY DEFAULT FOAM (migration 0050). The list endpoint exposes it ('32D'
     unless set); only an admin sets it, to exactly '32D' or '4G'; a duplicate keeps it;
     the database refuses anything else.

Marker RT2Q; every row it creates is purged by marker at setup AND teardown.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
MARK = "RT2Q"
REFUSAL = "Template thickness is set in Body Templates by an administrator."


# ── 1. the calculators, by source ─────────────────────────────────────────────

def _bom_puts(src: str) -> list[str]:
    """Every `api('PUT', `/api/bom/${…}`, { … })` call, as written."""
    return re.findall(r"api\('PUT',\s*`/api/bom/\$\{[^}]+\}`\s*,\s*\{[^}]*\}", src)


@pytest.mark.parametrize("name", ["calculator.js", "calculator2.js"])
def test_no_calculator_puts_a_thickness(name):
    src = (JS / name).read_text(encoding="utf-8")
    puts = _bom_puts(src)
    assert puts, f"{name}: the PUT /api/bom matcher found nothing — has the call shape changed?"
    thickness = [p for p in puts if "variable_value" in p]
    assert not thickness, f"{name} still writes a template thickness: {thickness}"
    # what is left is the explicit, permission-gated price / formula saves (RT2 R4 keeps them)
    assert all(("unit_price_override" in p) or ("formula_expression" in p) for p in puts), puts


def test_the_old_per_browser_foam_memory_is_gone():
    """R6.2 — the browser's remembered grade (ins_foam_<tid>) no longer decides where a
    new costing starts; a fresh costing opens on the body's default."""
    src = (JS / "calculator.js").read_text(encoding="utf-8")
    assert "`ins_foam_${" not in src and "_insFoamKey" not in src     # no key is built, so none is read or written
    assert "insulationFoam = _bodyDefaultFoam(tid);" in src
    assert "(body default)" in src


def test_the_template_updated_warning_is_gone():
    """R3 — a typed thickness changes this quote only; nothing claims a template write."""
    for name in ("calculator.js", "calculator2.js"):
        src = (JS / name).read_text(encoding="utf-8")
        assert "TEMPLATE UPDATED" not in src, name
        assert "Body Template updated" not in src, name


# ── 2. the price follows the quote's own thickness ────────────────────────────

def test_a_quotes_own_thickness_reaches_the_formula():
    from app.formula_engine import evaluate_formula
    from app.routers.calculator import _apply_body_variable_overrides, _build_body_variables
    master = lambda name, v: SimpleNamespace(is_body_option=True, variable_value=v,  # noqa: E731
                                            material=SimpleNamespace(name=name))
    template = [master("FRONT EPS", 0.06), master("FRONT PU", 0.0)]
    formula = "(1.22*2.44*{FRONT PU}/2.98)*(1.22*2.44)*2"     # Burt's PU row, term for term

    body_vars = _build_body_variables(template)
    assert evaluate_formula(formula, {}, body_vars) == 0.0     # the template alone: no PU
    # the quote switched FRONT to PU: the overlay carries the thickness across (copy-on-switch)
    _apply_body_variable_overrides(body_vars, {"FRONT PU": 0.06, "FRONT EPS": 0.0})
    qty = evaluate_formula(formula, {}, body_vars)
    assert qty == pytest.approx((1.22 * 2.44 * 0.06 / 2.98) * (1.22 * 2.44) * 2)
    assert body_vars["FRONT EPS"] == 0.0
    # …and the template rows themselves were never touched
    assert [r.variable_value for r in template] == [0.06, 0.0]


# ── DB fixtures (real UserSession rows via raw Cookie headers — the banked pattern) ──

def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


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
    sid = f"rt2q-{uuid.uuid4().hex[:12]}"
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
        for role in ("sales", "full"):
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
def body(app_mod):
    """One body: a FRONT EPS / PU pair (EPS carries 0.06) and a PU foam line."""
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0,
                         default_width=2.4, default_height=2.4)
        db.add(tt)
        db.flush()
        eps_m = Material(name=f"{MARK} FRONT EPS", unit_of_measure="each", price_per_unit=0.0)
        pu_m = Material(name=f"{MARK} FRONT PU", unit_of_measure="each", price_per_unit=0.0)
        db.add_all([eps_m, pu_m])
        db.flush()
        eps = BillOfMaterial(trailer_type_id=tt.id, material_id=eps_m.id, is_body_option=True,
                             body_option_group="FRONT", body_option_subgroup="INSULATION",
                             body_option_default=True, variable_value=0.06)
        pu = BillOfMaterial(trailer_type_id=tt.id, material_id=pu_m.id, is_body_option=True,
                            body_option_group="FRONT", body_option_subgroup="INSULATION",
                            body_option_default=False, variable_value=0.0)
        db.add_all([eps, pu])
        db.commit()
        ids = {"tt": tt.id, "eps": eps.id, "pu": pu.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _vv(bom_id: int):
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return db.get(BillOfMaterial, bom_id).variable_value


# ── 3. R2, both sides ─────────────────────────────────────────────────────────

def test_a_refused_thickness_leaves_the_template_as_it_was(client, users, body):
    for role in ("sales", "full"):
        r = client.put(f"/api/bom/{body['eps']}", headers=users[role], json={"variable_value": 0.0})
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == REFUSAL
        r = client.put(f"/api/bom/{body['pu']}", headers=users[role], json={"variable_value": 0.06})
        assert r.status_code == 403, r.text
    assert (_vv(body["eps"]), _vv(body["pu"])) == (0.06, 0.0)


def test_body_templates_full_body_save_still_works_for_an_admin(client, users, body):
    """admin_templates.js saves a BOM row with the WHOLE body (thickness + skin / taping /
    floor / cleat fields) — the admin branch, untouched by R2."""
    full = {"formula_expression": "", "waste_percentage": 0, "notes": "", "variable_value": 0.08,
            "skin_formula_id": None, "skin_formula_region": "standard", "taping_block_id": None,
            "floor_plate_id": None, "mounting_cleat_id": None}
    r = client.put(f"/api/bom/{body['eps']}", headers=users["admin"], json=full)
    assert r.status_code == 200, r.text
    assert _vv(body["eps"]) == 0.08
    r = client.put(f"/api/bom/{body['eps']}", headers=users["full"], json=full)
    assert r.status_code == 403 and r.json()["detail"] == "Admin access required"


def test_an_admin_may_still_set_a_template_thickness(client, users, body):
    r = client.put(f"/api/bom/{body['pu']}", headers=users["admin"], json={"variable_value": 0.05})
    assert r.status_code == 200, r.text
    assert _vv(body["pu"]) == 0.05


# ── 4. R6 — the per-body default foam (migration 0050) ────────────────────────

def _listed(client, headers, tid):
    rows = client.get("/api/trailers", headers=headers).json()
    return next(t for t in rows if t["id"] == tid)


def test_every_body_defaults_to_32d_and_the_list_says_so(client, users, body):
    t = _listed(client, users["sales"], body["tt"])
    assert t["default_insulation_foam"] == "32D"
    assert client.get(f"/api/trailers/{body['tt']}", headers=users["sales"]).json()[
        "default_insulation_foam"] == "32D"


def test_only_an_admin_sets_the_default_and_only_to_a_known_grade(client, users, body):
    from app.database import SessionLocal, TrailerType
    r = client.put(f"/api/trailers/{body['tt']}", headers=users["full"], json={"default_insulation_foam": "4G"})
    assert r.status_code == 403
    for bad in ("4g foam", "50D", "", None):
        r = client.put(f"/api/trailers/{body['tt']}", headers=users["admin"], json={"default_insulation_foam": bad})
        assert r.status_code == 400, (bad, r.text)
    r = client.put(f"/api/trailers/{body['tt']}", headers=users["admin"], json={"default_insulation_foam": " 4g "})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(TrailerType, body["tt"]).default_insulation_foam == "4G"     # canonical spelling
    assert _listed(client, users["sales"], body["tt"])["default_insulation_foam"] == "4G"


def test_a_duplicate_keeps_the_default(client, users, body):
    from app.database import SessionLocal, TrailerType
    client.put(f"/api/trailers/{body['tt']}", headers=users["admin"], json={"default_insulation_foam": "4G"})
    r = client.post(f"/api/trailers/{body['tt']}/duplicate", headers=users["admin"],
                    json={"name": f"{MARK} BODY COPY"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        copy = db.query(TrailerType).filter_by(name=f"{MARK} BODY COPY").one()
        assert copy.default_insulation_foam == "4G"


def test_the_database_refuses_an_unknown_grade(app_mod, body):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.database import SessionLocal
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE icb_costings.trailer_types SET default_insulation_foam = '50D' WHERE id = :i"),
                       {"i": body["tt"]})
            db.flush()
        db.rollback()
