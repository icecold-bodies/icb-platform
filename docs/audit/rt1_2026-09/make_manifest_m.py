"""Generate manifest_m.yaml — RT1 Manifest M (ruling 1 §1, option c+): the 11 MEAT HANGER PU lines to Burt's F1 shape.

Michael's model (30 Sep, ratified): the shared PU material holds Burt's 32D unit price per m³ (R4 095, Burt's 21 Sep
list); each body's formula works out the volume — Burt's row term for term, with the panel's thickness variable and
/2.98. He converted the freezers and chillers on 29 Sep; the MEAT HANGERs were missed, so their sheet-count formulas
price sheets at the m³ price (MEAT HANGER LARGE PU ≈ R343k instead of ≈ R59k). FORMULA CHANGES ONLY; no own prices.

The new formulas are taken CHARACTER FOR CHARACTER from Michael's own 29 Sep freezer lines in the same 1b prod snapshot
(FREEZER MEDIUM: FRONT 2406, DRD 2441, SRD 2415, SIDES 2463, ROOF 2473, FLOOR 2481), and each is checked against
Burt's MEAT BODY / SMALL MEAT BODY UP TO 5,2 rows (read 30 Sep, formula text):
  FRONT row 32, DRD row 83, SRD row 46:  G = 1.22*2.44*T*PU!C/2.98, H = G*F*I*2
  SIDES row 116 (C116 = (L+0.05)/1.22, section total x2), ROOF row 132, FLOOR row 148:  H = G*F*I*C1xx
(MEAT BODY!G32 alone divides by 2.99 — a sheet inconsistency; the ruling fixes /2.98.) Burt prices FRONT / DRD / SIDES /
ROOF / FLOOR at 4G (PU!C19) and SRD at 32D (PU!C17); MES stays 32D-based, 4G via the quote's foam toggle (Michael's
1 Sep ruling). 6229 (MEAT HANGER SMALL-MEDIUM FLOOR, own R446.02) is OUT (ruling) — reported, not changed.

The GUARDS (`current`) come from the RT1 1b PROD snapshot. Anything not in the expected shape is REFUSED.

    python make_manifest_m.py <1b all.json> <1b meat_hangers.json>     (writes manifest_m.yaml beside this file)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
M_LINES = {  # bom id -> (body id, body, section)
    5842: (12, "MEAT HANGER LARGE", "FRONT"), 5877: (12, "MEAT HANGER LARGE", "DRD"),
    5851: (12, "MEAT HANGER LARGE", "SRD"), 5899: (12, "MEAT HANGER LARGE", "SIDES"),
    5910: (12, "MEAT HANGER LARGE", "ROOF"), 5921: (12, "MEAT HANGER LARGE", "FLOOR"),
    6150: (36, "MEAT HANGER SMALL-MEDIUM", "FRONT"), 6185: (36, "MEAT HANGER SMALL-MEDIUM", "DRD"),
    6159: (36, "MEAT HANGER SMALL-MEDIUM", "SRD"), 6207: (36, "MEAT HANGER SMALL-MEDIUM", "SIDES"),
    6218: (36, "MEAT HANGER SMALL-MEDIUM", "ROOF"),
}
OUT_OF_M = 6229
TEMPLATE = {"FRONT": 2406, "DRD": 2441, "SRD": 2415, "SIDES": 2463, "ROOF": 2473, "FLOOR": 2481}   # FREEZER MEDIUM, 29 Sep
BURT = {  # the expected shape per section (Burt's row term for term, /2.98)
    "FRONT": "(1.22*2.44*{FRONT PU}/2.98)*(1.22*2.44)*2",
    "DRD": "(1.22*2.44*{DRD PU}/2.98)*(1.22*2.44)*2",
    "SRD": "(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2",
    "SIDES": "(1.22*2.44*{SIDES PU}/2.98)*(1.22*2.44)*((length+{Waste})/1.22)",
    "ROOF": "(1.22*2.44*{ROOF PU}/2.98)*(1.22*2.44)*((length+{Waste})/1.22)",
    "FLOOR": "(1.22*2.44*{FLOOR PU}/2.98)*(1.22*2.44)*((length+{Waste})/1.22)",
}
THICKNESS = re.compile(r"\{[^}]*\b(PU|EPS)\s*\}", re.I)
PRICE = 4095.0


def main(*snaps):
    bom, tt, mats, gen = {}, {}, {}, []
    for p in snaps:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        gen.append(f"{Path(p).name} {doc.get('generated_at')}")
        t = doc["tables"]
        bom.update({r["id"]: r for r in t["bill_of_materials"]})
        tt.update({r["id"]: r for r in t["trailer_types"]})
        mats.update({r["id"]: r for r in t["materials"]})
    problems, entries = [], []
    # the target formulas: Michael's own freezer lines, and they must equal Burt's shape
    for sec, bid in TEMPLATE.items():
        f = (bom.get(bid) or {}).get("formula_expression")
        if f != BURT[sec]:
            problems.append(f"template {bid} (FREEZER MEDIUM {sec}) reads {f!r}, not Burt's shape {BURT[sec]!r}")
    for bid, (tid, body, sec) in M_LINES.items():
        r = bom.get(bid)
        if r is None:
            problems.append(f"bom {bid}: not in the snapshots")
            continue
        m = mats.get(r["material_id"]) or {}
        name = (tt.get(r["trailer_type_id"]) or {}).get("name")
        if (r["trailer_type_id"], name, r["bom_section"], m.get("name")) != (tid, body, sec, "PU"):
            problems.append(f"bom {bid}: identity ({r['trailer_type_id']}, {name!r}, {r['bom_section']!r}, {m.get('name')!r}), "
                            f"expected ({tid}, {body!r}, {sec!r}, 'PU')")
            continue
        if r["unit_price_override"] is not None:
            problems.append(f"bom {bid}: carries an own price R{r['unit_price_override']} — refused (formula-only manifest)")
        if float(m.get("price_per_unit") or 0) != PRICE:
            problems.append(f"bom {bid}: material {m.get('id')} is R{m.get('price_per_unit')}, the model needs R{PRICE:g} (32D per m³)")
        f = r["formula_expression"]
        if THICKNESS.search(f or ""):
            problems.append(f"bom {bid}: formula {f!r} already has a thickness term — refused")
        if f"{sec} PU" not in (r["bom_conditions"] or ""):
            problems.append(f"bom {bid}: its rule {r['bom_conditions']!r} does not gate on {sec} PU")
        entries.append({"finding": "M1", "body_id": tid, "body": [body], "section": sec, "bom_id": bid, "line": "PU",
                        "field": "formula_expression", "current": f, "new": BURT[sec]})
    o = bom.get(OUT_OF_M)
    if o is not None:
        print(f"   out of M: {OUT_OF_M} {tt.get(o['trailer_type_id'], {}).get('name')} {o['bom_section']} own R{o['unit_price_override']} "
              f"formula {o['formula_expression']!r} (reported, not changed)")
    if problems:
        raise SystemExit("REFUSED:\n  " + "\n  ".join(problems))
    import yaml
    head = ("# RT1 Manifest M — the 11 MEAT HANGER PU lines to Burt's F1 shape (RT1 ruling 1 §1, option c+). FORMULA ONLY:\n"
            "# the shared PU material keeps Burt's 32D price per m³ (R4 095); the formula works out the volume. The new\n"
            "# formulas are Michael's own 29 Sep freezer formulas, character for character (= Burt's rows, /2.98).\n"
            "# GENERATED by make_manifest_m.py from the RT1 1b PROD snapshot — do not hand-edit.\n"
            f"# Guards = prod as it was in: {'; '.join(gen)}\n"
            "# Runs on: mirror, prod — as its own paste, before or after the code window (no order with A).\n")
    doc = {"note": "RT1 Manifest M — MEAT HANGER PU lines to Burt's F1 shape (formula only)", "changes": entries}
    out = HERE / "manifest_m.yaml"
    out.write_text(head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8",
                   newline="\n")
    print(f"wrote {out.name}: {len(entries)} entries on {len({e['bom_id'] for e in entries})} lines")


if __name__ == "__main__":
    main(*sys.argv[1:])
