"""RT3 — the startup bootstrap leaves the body families alone (RT3_RULING_1 Q3, G1; Q4).

On every start, app.database._bootstrap_report_templates seeds the developer-built quote templates and their groups
and binds unassigned bodies to them by a name keyword. Before RT3 it found each seed's group BY NAME and created it
when missing — so renaming MEATHANGER to MEAT, or deleting the empty RHINORANGE group, would have quietly brought
the old group back on the next restart (a seventh family). The fix: find the group by its name OR by the seed's
template, and create it only together with the template (a fresh database).

The ruling's tests, over SYNTHETIC seeds (REPORT_TEMPLATE_SEEDS is pointed at two RT3B seeds; marker rows only):
  * a fresh database still seeds the templates and the groups, and binds a matching unassigned body;
  * a rename survives a restart, and a new unassigned body binds to the renamed group (binding by template);
  * an admin-deleted group stays deleted, and its keyword binds nothing;
  * a body already in a family (any group) is never re-bound, whatever its name says;
  * NEGATIVE CONTROL: the pre-RT3 bootstrap (kept verbatim below) fails the restart tests.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

SEEDS = [
    ("rt3b_alpha_quote", "RT3B ALPHA Quotation", "RT3B alpha quote.", "RT3B ALPHA", "RT3B alpha bodies.", "RT3BKWALPHA"),
    ("rt3b_beta_quote", "RT3B BETA Quotation", "RT3B beta quote.", "RT3B BETA", "RT3B beta bodies.", "RT3BKWBETA"),
]


def _purge():
    from app.database import engine
    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM trailer_types WHERE name LIKE 'RT3BKW%' OR name LIKE 'RT3B %'"))
        c.execute(sa.text("DELETE FROM trailer_groups WHERE report_template_id IN "
                          "(SELECT id FROM report_templates WHERE slug LIKE 'rt3b_%') OR name LIKE 'RT3B %'"))
        c.execute(sa.text("DELETE FROM report_templates WHERE slug LIKE 'rt3b_%'"))


@pytest.fixture
def seeds(monkeypatch):
    import app.database as dbm
    _purge()
    monkeypatch.setattr(dbm, "REPORT_TEMPLATE_SEEDS", SEEDS)
    yield dbm
    _purge()


def _body(name, group_id=None):
    from app.database import SessionLocal, TrailerType
    with SessionLocal() as db:
        t = TrailerType(name=name, is_active=True, group_id=group_id)
        db.add(t)
        db.commit()
        return t.id


def _groups() -> dict:
    from app.database import engine
    with engine.connect() as c:
        rows = c.execute(sa.text("""SELECT g.id, g.name, t.slug FROM trailer_groups g
                                    LEFT JOIN report_templates t ON t.id = g.report_template_id
                                    WHERE g.name LIKE 'RT3B %' OR t.slug LIKE 'rt3b_%' ORDER BY g.id""")).all()
    return {r[1]: (r[0], r[2]) for r in rows}


def _group_of(tid):
    from app.database import engine
    with engine.connect() as c:
        return c.execute(sa.text("SELECT group_id FROM trailer_types WHERE id = :i"), {"i": tid}).scalar()


def _sql(stmt, **kw):
    from app.database import engine
    with engine.begin() as c:
        c.execute(sa.text(stmt), kw)


def test_a_fresh_database_seeds_the_templates_and_the_groups(seeds):
    b = _body("RT3BKWALPHA ONE")
    seeds._bootstrap_report_templates()
    g = _groups()
    assert set(g) == {"RT3B ALPHA", "RT3B BETA"}
    assert g["RT3B ALPHA"][1] == "rt3b_alpha_quote" and g["RT3B BETA"][1] == "rt3b_beta_quote"
    assert _group_of(b) == g["RT3B ALPHA"][0]
    seeds._bootstrap_report_templates()                  # idempotent
    assert _groups() == g


def test_a_rename_survives_a_restart_and_binding_follows_the_template(seeds):
    seeds._bootstrap_report_templates()
    gid = _groups()["RT3B ALPHA"][0]
    _sql("UPDATE trailer_groups SET name = 'RT3B RENAMED' WHERE id = :g", g=gid)     # MEATHANGER -> MEAT
    b = _body("RT3BKWALPHA NEW BODY")
    seeds._bootstrap_report_templates()                  # the restart
    g = _groups()
    assert "RT3B ALPHA" not in g, "the restart re-created the renamed group (a seventh family)"
    assert g["RT3B RENAMED"] == (gid, "rt3b_alpha_quote")
    assert _group_of(b) == gid, "a new unassigned body must bind to the group that holds the seed's template"


def test_an_admin_deleted_group_stays_deleted(seeds):
    seeds._bootstrap_report_templates()
    gid = _groups()["RT3B BETA"][0]
    _sql("DELETE FROM trailer_groups WHERE id = :g", g=gid)                          # the empty RHINORANGE group
    b = _body("RT3BKWBETA NEW BODY")
    seeds._bootstrap_report_templates()                  # the restart
    assert "RT3B BETA" not in _groups(), "the restart re-created a group an admin deleted"
    assert _group_of(b) is None, "a deleted family's keyword must bind nothing"


def test_a_body_already_in_a_family_is_never_rebound(seeds):
    seeds._bootstrap_report_templates()
    g = _groups()
    b = _body("RT3BKWALPHA IN BETA", group_id=g["RT3B BETA"][0])    # RHINORANGE in OTHER: its name says otherwise
    seeds._bootstrap_report_templates()
    assert _group_of(b) == g["RT3B BETA"][0]


# ── NEGATIVE CONTROL: the pre-RT3 bootstrap, verbatim (database.py before RT3) ─────────────────────────

def _old_bootstrap(seeds_list):
    from app.database import ReportTemplate, SessionLocal, TrailerGroup, TrailerType
    db = SessionLocal()
    try:
        from sqlalchemy import func as _fn
        for slug, tname, tdesc, gname, gdesc, match in seeds_list:
            tmpl = db.query(ReportTemplate).filter_by(slug=slug).first()
            if not tmpl:
                tmpl = ReportTemplate(name=tname, slug=slug, description=tdesc, is_active=True)
                db.add(tmpl); db.flush()
            grp = db.query(TrailerGroup).filter_by(name=gname).first()
            if not grp:
                grp = TrailerGroup(name=gname, description=gdesc, report_template_id=tmpl.id)
                db.add(grp); db.flush()
            elif grp.report_template_id is None:
                grp.report_template_id = tmpl.id
            unassigned = db.query(TrailerType).filter(
                TrailerType.is_active == True,  # noqa: E712
                TrailerType.group_id.is_(None),
                _fn.upper(TrailerType.name).like(f"%{match}%"),
            ).all()
            for tt in unassigned:
                tt.group_id = grp.id
        db.commit()
    finally:
        db.close()


def test_negative_control_the_old_bootstrap_brings_both_groups_back(seeds):
    seeds._bootstrap_report_templates()
    g = _groups()
    _sql("UPDATE trailer_groups SET name = 'RT3B RENAMED' WHERE id = :g", g=g["RT3B ALPHA"][0])
    _sql("DELETE FROM trailer_groups WHERE id = :g", g=g["RT3B BETA"][0])
    _old_bootstrap(SEEDS)
    after = _groups()
    assert "RT3B ALPHA" in after and "RT3B BETA" in after, (
        "the negative control no longer reproduces the defect — the restart tests above would prove nothing")
