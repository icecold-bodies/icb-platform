"""v1.44.1 — fleet cleanup script for the rear-door insulation invariant.

collect() must: target ONLY the inactive door group's INSULATION EPS/PU rows
with non-zero thickness; leave the active door and non-door pairs alone; skip
(and report) bodies where neither door group defaults on; and be idempotent
once the zeros are written.
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
    mark = f"V1441U-{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        def mat(name):
            m = Material(name=f"{mark} {name}", unit_of_measure="ea", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        def row(tt, name, grp, sub=None, default=False, var=None):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=mat(name).id,
                               formula_expression="1", waste_percentage=0,
                               is_body_option=True, body_option_group=grp,
                               body_option_subgroup=sub, body_option_default=default,
                               variable_value=var)
            db.add(r)
            db.flush()
            return r

        # Body 1: DRD defaults on; SRD pair DIRTY; FRONT pair must be untouched.
        t1 = TrailerType(name=f"{mark} DIRTY BODY")
        db.add(t1)
        db.flush()
        row(t1, "DRD EPS", "DRD", "INSULATION", default=True, var=0.06)
        row(t1, "DRD PU", "DRD", "INSULATION", var=0.0)
        srd_eps = row(t1, "SRD EPS", "SRD", "INSULATION", var=0.05)
        srd_pu = row(t1, "SRD PU", "SRD", "INSULATION", var=0.02)
        row(t1, "SRD DOOR SET", "SRD", var=0.9)          # not INSULATION → untouched
        front = row(t1, "FRONT EPS", "FRONT", "INSULATION", default=True, var=0.06)

        # Body 2: neither door group defaults on → ambiguous, skipped.
        t2 = TrailerType(name=f"{mark} AMBIGUOUS BODY")
        db.add(t2)
        db.flush()
        row(t2, "DRD EPS", "DRD", "INSULATION", var=0.06)
        row(t2, "SRD EPS", "SRD", "INSULATION", var=0.05)

        db.commit()
        ids = {"mark": mark, "t1": t1.id, "t2": t2.id,
               "srd_eps": srd_eps.id, "srd_pu": srd_pu.id, "front": front.id}
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


def test_collect_targets_only_inactive_door_insulation(staged):
    from app.database import SessionLocal
    from scripts.zero_inactive_door_insulation import collect
    with SessionLocal() as db:
        actions, ambiguous, _clean = collect(db)
        mine = [a for a in actions if a["tt"].id == staged["t1"]]
        assert len(mine) == 1
        a = mine[0]
        assert a["active"] == "DRD"
        got = {row.id: val for row, _n, val in a["rows"]}
        assert got == {staged["srd_eps"]: 0.05, staged["srd_pu"]: 0.02}
        assert any(staged["mark"] in n for n in ambiguous)          # body 2 skipped
        assert not any(x[0].id == staged["front"] for x in a["rows"])


def test_apply_zeroes_and_is_idempotent(staged):
    from app.database import BillOfMaterial, SessionLocal
    from scripts.zero_inactive_door_insulation import collect
    with SessionLocal() as db:
        actions, _amb, _clean = collect(db)
        for a in actions:
            if a["tt"].id != staged["t1"]:
                continue
            for row, _n, _v in a["rows"]:
                row.variable_value = 0
        db.commit()
    with SessionLocal() as db:
        assert float(db.get(BillOfMaterial, staged["srd_eps"]).variable_value or 0) == 0
        assert float(db.get(BillOfMaterial, staged["srd_pu"]).variable_value or 0) == 0
        assert float(db.get(BillOfMaterial, staged["front"]).variable_value or 0) == 0.06
        actions, _amb, _clean = collect(db)
        assert not [a for a in actions if a["tt"].id == staged["t1"]]   # healed → clean
