"""Generate manifest_a.yaml — the v1.58.1 REAR FRAME inclusion rules (BA dispatch 6 + ruling 6a).

Scope = PROD's (discovery run out-20260929T112139Z, prod/discovery_20260929T112139Z.txt): 14 bodies,
120 REAR FRAME & FLOOR PLATE lines. bom ids and master (option) ids are shared dev <-> prod; the
body NAMES differ for the three icecream bodies, so every entry lists the prod name first and the dev
name second (the tool accepts either; body_id stays exact).

Line identity (section + material name) is read from the DEV database (read-only) and cross-checked
against the committed prod snapshot for the 12 audited bodies — any disagreement aborts.

    python make_manifest_a.py <DEV DATABASE_URL>     (writes manifest_a.yaml beside this file)
"""
import json
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parents[2] / "backend" / "tests" / "costing_audit" / "mes_snapshot" / "all.json"
SECTION = "REAR FRAME & FLOOR PLATE"

# body_id -> (prod name, rule masters as (option, option_id)). From the prod discovery output
# (lines 56-69). CHILLER LARGE uses its DOOR TYPE master (return 6b §3 — pending the BA's word).
PAIR = lambda eps, pu: (("SRD EPS", eps), ("SRD PU", pu))
SCOPE = {
    25: ("CHILLER 2.3 METER", PAIR(3797, 3798)),
    27: ("CHILLER LARGE", (("SRD", 7233),)),
    26: ("CHILLER MEDIUM", PAIR(3296, 3297)),
    37: ("EXPLOSIVE 2.7 TO 4.8", PAIR(6454, 6455)),
    24: ("EXPLOSIVE 4.9 AND UP", PAIR(4057, 4058)),
    34: ("EXPLOSIVE UP TO 2.7", PAIR(5285, 5286)),
    19: ("FREEZER 2.3 METER", PAIR(3677, 3678)),
    21: ("FREEZER LARGE", PAIR(2684, 2685)),
    20: ("FREEZER MEDIUM", PAIR(2536, 2537)),
    18: ("ICECREAM BODY LARGE", PAIR(5427, 5428)),
    17: ("ICECREAM BODY MEDIUM", PAIR(5705, 5706)),
    16: ("ICECREAM BODY SMALL", PAIR(5827, 5828)),
    12: ("MEAT HANGER LARGE", PAIR(5980, 5981)),
    36: ("MEAT HANGER SMALL-MEDIUM", PAIR(6288, 6289)),
}
PROD_LINES = 120


def _canon(text):
    """bom_conditions compared as canonical JSON (the tool's own rule — key order / spacing never matter)."""
    return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))


def main(url):
    url = url.replace("postgresql+psycopg://", "postgresql://")
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["tables"]
    s_bom = {r["id"]: r for r in snap["bill_of_materials"]}
    s_mat = {r["id"]: r["name"] for r in snap["materials"]}
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("""SELECT b.id, b.trailer_type_id, t.name, b.bom_section, m.name, b.bom_conditions
                         FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
                         JOIN materials m ON m.id = b.material_id
                        WHERE b.trailer_type_id = ANY(%s) AND b.bom_section = %s ORDER BY b.trailer_type_id, b.id""",
                    (list(SCOPE), SECTION))
        rows = cur.fetchall()
        cur.execute("""SELECT b.id, b.trailer_type_id, m.name FROM bill_of_materials b
                         JOIN materials m ON m.id = b.material_id WHERE b.id = ANY(%s)""",
                    ([mid for _, ms in SCOPE.values() for _, mid in ms],))
        masters = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    problems = []
    for tid, (_, ms) in SCOPE.items():
        for opt, mid in ms:
            if masters.get(mid) != (tid, opt):
                problems.append(f"master {mid}: expected ({tid}, {opt!r}), dev has {masters.get(mid)}")
    entries = []
    for bid, tid, dev_name, section, line, cond in rows:
        prod_name, ms = SCOPE[tid]
        rule = [{"option": o, "equals": "N", "option_id": i} for o, i in ms]
        # dev may carry NO rule (before the dev apply) or exactly THIS rule (after it) — anything
        # else is a foreign rule somebody saved, and the manifest must not be generated over it
        if cond not in (None, "", "null") and _canon(cond) != _canon(json.dumps(rule)):
            problems.append(f"bom {bid}: dev carries a foreign bom_conditions {cond!r}")
        s = s_bom.get(bid)
        if s is not None and (s["trailer_type_id"], s["bom_section"], s_mat.get(s["material_id"])) != (tid, section, line):
            problems.append(f"bom {bid}: snapshot says {(s['trailer_type_id'], s['bom_section'], s_mat.get(s['material_id']))}")
        names = [prod_name] if dev_name == prod_name else [prod_name, dev_name]
        entries.append({"finding": "R1", "body_id": tid, "body": names, "section": section, "bom_id": bid,
                        "line": line, "field": "bom_conditions", "current": None, "new": rule})
    if len(entries) != PROD_LINES:
        problems.append(f"{len(entries)} lines on dev, prod has {PROD_LINES}")
    if problems:
        raise SystemExit("REFUSED:\n  " + "\n  ".join(problems))
    import yaml
    head = ("# v1.58.1 Manifest A — REAR FRAME & FLOOR PLATE is not costed on a single rear door (SRD).\n"
            "# GENERATED by make_manifest_a.py — do not hand-edit. Runs on: mirror, dev, prod (A before B).\n"
            "# TOOL-WRITTEN RULES: safe to edit in the Trailer Designer on any environment running v1.59.1 or\n"
            "# later (#200: the rule editor keeps conditions from outside the branch). After editing one,\n"
            "# re-run the audit page (MEAT HANGERs: quote one SRD and one DRD — no audit pack covers them).\n"
            "# Prod gets this manifest only after v1.59.1 is accepted there.\n")
    doc = {"note": "v1.58.1 SRD rear frame — REAR FRAME & FLOOR PLATE excluded when SRD is selected (Manifest A)",
           "changes": entries}
    out = HERE / "manifest_a.yaml"
    out.write_text(head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8",
                   newline="\n")
    print(f"wrote {out.name}: {len(entries)} entries on {len({e['body_id'] for e in entries})} bodies")


if __name__ == "__main__":
    main(sys.argv[1])
