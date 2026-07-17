"""v1.42 — Full Cost Access ('full') can create + sales-sign Pre-Job Cards.

Michael 17 Jul: Nadie (role 'full') was blocked at the Pre-Job Card modal —
prejob.create was seeded to {'sales'} only. The catalogue now grants
prejob.create AND prejob.signoff_sales to 'full' (she is the Sales-Rep signer
on her own cards); prejob.signoff_planner stays planner-only. The startup
bootstrap (_bootstrap_permissions) heals missing role-grant rows from this
catalogue on every boot, so these defaults ARE the deployed behaviour.
"""
from app.database import PERMISSION_CATALOGUE


def _roles(perm_name):
    for name, _desc, _cat, roles in PERMISSION_CATALOGUE:
        if name == perm_name:
            return roles
    raise AssertionError(f"{perm_name} missing from PERMISSION_CATALOGUE")


def test_full_role_can_create_prejob_cards():
    assert "full" in _roles("prejob.create")
    assert "sales" in _roles("prejob.create")


def test_full_role_can_sales_sign_prejob_cards():
    assert "full" in _roles("prejob.signoff_sales")
    assert "sales" in _roles("prejob.signoff_sales")


def test_planner_signoff_stays_planner_only():
    assert _roles("prejob.signoff_planner") == {"planner"}
