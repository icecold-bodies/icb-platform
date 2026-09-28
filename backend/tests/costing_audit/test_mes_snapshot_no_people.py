"""The committed MES snapshot holds pricing definition data only — never people.

v1.57.3 regenerates the snapshot from a dev database restored from prod, so the
snapshot's source now carries real customers, contacts, end users and users.
`mes_snapshot.FORBIDDEN` refuses an FK walk INTO those tables; this test is the
independent gate on the committed file itself, by three mechanisms:

1. an ALLOW-list of tables (a new table in the snapshot is a conscious decision,
   not something an FK walk drags in);
2. no column named like personal data in any snapshot table;
3. no email-shaped value anywhere in the file.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit import MES_SNAPSHOT_DIR                  # noqa: E402

SNAPSHOT = MES_SNAPSHOT_DIR / "all.json"

# Pricing definition tables: trailers + BOM, materials, sections, body options,
# recipe tables (skins / taping / floor plates / cleats), formulas, globals,
# the 4G-factor setting, SAP item codes, and the report templates bodies point at.
PRICING_TABLES = {
    "admin_settings", "bill_of_materials", "body_option_groups", "body_option_subgroups",
    "bom_sections", "floor_plate_items", "floor_plates", "formulas", "global_variables",
    "material_categories", "materials", "mounting_cleat_items", "mounting_cleats",
    "report_templates", "sap_item_codes", "skin_formula_ingredients", "skin_formula_items",
    "skin_formulas", "taping_block_items", "taping_blocks", "trailer_groups", "trailer_types",
}

PERSONAL_COLUMN = re.compile(
    r"e_?mail|phone|telephone|mobile|whatsapp|fax|username|password|first_name|last_name|"
    r"full_name|contact_name|customer|end_user|address|id_number|vat_number", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def _doc():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_tables_are_pricing_definitions_only():
    extra = set(_doc()["tables"]) - PRICING_TABLES
    assert not extra, f"snapshot carries non-pricing table(s) {sorted(extra)} — add to PRICING_TABLES only if it holds no people"


def test_snapshot_has_no_personal_columns():
    hits = sorted({f"{t}.{col}" for t, rows in _doc()["tables"].items() for r in rows for col in r
                   if PERSONAL_COLUMN.search(col)})
    assert not hits, f"personal-looking column(s) in the snapshot: {hits}"


def test_snapshot_has_no_email_addresses():
    found = EMAIL.findall(SNAPSHOT.read_text(encoding="utf-8"))
    assert not found, f"{len(found)} email-shaped value(s) in the committed snapshot"


def test_the_exporter_refuses_people_before_writing():
    import pytest
    from tools.costing_audit.mes_snapshot import check_pricing_only, ALLOWED_TABLES
    assert ALLOWED_TABLES == PRICING_TABLES          # the two guards agree, but are written twice
    check_pricing_only({"materials": [{"id": 1, "name": "3090", "price": 334.5}]})
    with pytest.raises(RuntimeError, match="non-pricing table"):
        check_pricing_only({"customers": [{"id": 1}]})
    with pytest.raises(RuntimeError, match="personal-looking column"):
        check_pricing_only({"trailer_types": [{"id": 1, "contact_email": "x"}]})


def test_ci_pairs_the_prod_snapshot_with_the_prod_accepted_list():
    # The committed snapshot is PROD's pricing (v1.57.3), so CI must judge it with
    # PROD's accepted list — a matched pair. The dev list stays for local runs.
    from tools.costing_audit.cli import _accepted_path
    wf = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "costing-audit.yml"
    runs = [ln for ln in wf.read_text(encoding="utf-8").splitlines() if "tools.costing_audit run" in ln]
    assert runs, "no audit run step in costing-audit.yml"
    assert all("--env prod" in ln for ln in runs), runs
    assert _accepted_path(None, "prod").name == "accepted_differences.prod.yaml"
    assert _accepted_path(None, "prod").is_file()


def test_the_gates_catch_a_known_hit():
    # A check that returns empty proves nothing until it has caught a known hit.
    assert "customers" not in PRICING_TABLES and "users" not in PRICING_TABLES
    assert PERSONAL_COLUMN.search("contact_email") and PERSONAL_COLUMN.search("telephone")
    assert not PERSONAL_COLUMN.search("formula_expression") and not PERSONAL_COLUMN.search("source_cell")
    assert EMAIL.search('{"note": "ask jan.smit@example.co.za"}')
