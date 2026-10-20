"""RT7 §3.0 — the G4 proof for a snapshot export, run on the written file (never on the database):

  1. the committed no-people gate (tests/costing_audit/test_mes_snapshot_no_people.py, staged beside this file):
     the known-hit self-test, the table allow-list, no personal-looking column, no email-shaped value;
  2. no phone-shaped value anywhere in the file;
  3. the inventory: every table, its row count and its column NAMES; the free-text columns' shape (distinct counts;
     the bulk-update notes are short system labels and are printed).

    python rt7_inventory.py <all.json> <test_mes_snapshot_no_people.py>      exit 1 on any failure
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

snap, gate_file = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("no_people_gate", gate_file)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate.SNAPSHOT = snap
for name in ("test_the_gates_catch_a_known_hit", "test_snapshot_tables_are_pricing_definitions_only",
             "test_snapshot_has_no_personal_columns", "test_snapshot_has_no_email_addresses"):
    getattr(gate, name)()
    print(f"   gate ok: {name}")

text = snap.read_text(encoding="utf-8")
PHONE = re.compile(r"(?:\+27|\b0)\d{2}[ -]?\d{3}[ -]?\d{4}\b")
assert PHONE.search("call 082 555 1234") and not PHONE.search('"price_per_unit": 1234.5678')   # proves the check
phones = PHONE.findall(text)
print(f"   phone-shaped values: {len(phones)}")
if phones:
    sys.exit("STOP: phone-shaped value(s) in the export")

doc = json.loads(text)
print(f"   generated_at {doc.get('generated_at')}  trailers {doc.get('trailer_ids')}")
print(f"   {'table':<26} {'rows':>5}  columns")
for t, rows in doc["tables"].items():
    cols = sorted({c for r in rows for c in r})
    print(f"   {t:<26} {len(rows):>5}  {', '.join(cols)}")
mats = doc["tables"].get("materials", [])
notes = sorted({str(r.get("last_bulk_update_note")) for r in mats})
print(f"   materials.last_bulk_update_note (system labels): {notes}")
print(f"   materials.supplier: {len({r.get('supplier') for r in mats})} distinct (company names, not printed)")
bom = doc["tables"].get("bill_of_materials", [])
print(f"   bill_of_materials.notes: {sum(1 for r in bom if r.get('notes'))} non-empty of {len(bom)}")
print(f"   total rows {sum(len(r) for r in doc['tables'].values())}  bytes {len(text.encode('utf-8'))}")
