"""v1.44.2 — read-only insulation-pair gap report.

collect() must bucket: NEEDS-VALUE (both sides 0/NULL), NULL-SIDE (one side
NULL), DOOR-DIRTY (non-default rear-door pair still valued), FLAG-VS-VALUE
(default flag on the zero side) — and stay silent on healthy pairs and on the
quoted door. It never writes.
"""
import uuid

import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


@pytest.fixture()
def staged(app_mod):
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    mark = f"V1442R-{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        def mat(name):
            m = Material(name=f"{mark} {name}", unit_of_measure="ea", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        def row(tt, name, grp, default=False, var=None):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=mat(name).id,
                               formula_expression="1", waste_percentage=0,
                               is_body_option=True, body_option_group=grp,
                               body_option_subgroup="INSULATION",
                               body_option_default=default, variable_value=var)
            db.add(r)
            db.flush()
            return r

        tt = TrailerType(name=f"{mark} REPORT BODY")
        db.add(tt)
        db.flush()
        ids = {"mark": mark, "tt": tt.id}
        # NEEDS-VALUE: ROOF both empty (NULL + 0)
        ids["roof_eps"] = row(tt, "ROOF EPS", "ROOF", default=True, var=None).id
        ids["roof_pu"] = row(tt, "ROOF PU", "ROOF", var=0.0).id
        # NULL-SIDE + FLAG-VS-VALUE: FRONT — flag on EPS which is NULL, PU holds 0.07
        ids["front_eps"] = row(tt, "FRONT EPS", "FRONT", default=True, var=None).id
        ids["front_pu"] = row(tt, "FRONT PU", "FRONT", var=0.07).id
        # Healthy: SIDES — flag side owns the value
        ids["sides_eps"] = row(tt, "SIDES EPS", "SIDES", default=True, var=0.06).id
        ids["sides_pu"] = row(tt, "SIDES PU", "SIDES", var=0.0).id
        # Doors: DRD default (quoted, healthy) — SRD dirty → DOOR-DIRTY
        ids["drd_eps"] = row(tt, "DRD EPS", "DRD", default=True, var=0.06).id
        ids["drd_pu"] = row(tt, "DRD PU", "DRD", var=0.0).id
        ids["srd_eps"] = row(tt, "SRD EPS", "SRD", var=0.05).id
        ids["srd_pu"] = row(tt, "SRD PU", "SRD", var=0.0).id
        db.commit()
    yield ids
    with SessionLocal() as db:
        from sqlalchemy import text
        db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id "
                        "IN (SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"),
                   {"m": f"{mark}%"})
        db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"),
                   {"m": f"{mark}%"})
        db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"),
                   {"m": f"{mark}%"})
        db.commit()


def _mine(bucket, staged):
    return [(tt, e, p) for tt, e, p in bucket if tt.id == staged["tt"]]


def test_report_buckets_and_no_writes(staged):
    from app.database import BillOfMaterial, SessionLocal
    from scripts.report_insulation_pair_gaps import collect
    with SessionLocal() as db:
        acts = collect(db)
        (tt, e, p), = _mine(acts["needs_value"], staged)
        assert {e.id, p.id} == {staged["roof_eps"], staged["roof_pu"]}
        (tt, e, p), = _mine(acts["null_side"], staged)
        assert {e.id, p.id} == {staged["front_eps"], staged["front_pu"]}
        (tt, e, p), = _mine(acts["flag_vs_value"], staged)
        assert {e.id, p.id} == {staged["front_eps"], staged["front_pu"]}
        (tt, e, p), = _mine(acts["door_dirty"], staged)
        assert {e.id, p.id} == {staged["srd_eps"], staged["srd_pu"]}
    # No writes: every staged value unchanged.
    with SessionLocal() as db:
        get = lambda k: db.get(BillOfMaterial, staged[k]).variable_value
        assert get("roof_eps") is None and float(get("roof_pu")) == 0.0
        assert get("front_eps") is None and float(get("front_pu")) == 0.07
        assert float(get("sides_eps")) == 0.06
        assert float(get("srd_eps")) == 0.05
