"""Generate manifest_b.yaml — RT1 Manifest B: the single-rear-door PU lines that still inherit the global
SRD PU material instead of carrying Burt's F1 shape with their own R4 100.

  5851 MEAT HANGER LARGE         SRD / PU  `1.22*2.44*2` -> the F1 shape, own R4 100  (Burt MEAT BODY!H46)
  6159 MEAT HANGER SMALL-MEDIUM  SRD / PU  `1.22*2.44*2` -> the F1 shape, own R4 100  (Burt SMALL MEAT BODY UP TO 5,2!H46)
  5585 ICECREAM BODY MEDIUM      SRD / PU  F1 shape already -> own R4 100
  2415 FREEZER MEDIUM            SRD / PU  own R4 100 BACK (#197's F1 price, lost on prod 29 Sep)
  3576 FREEZER 2.3 METER         SRD / PU  own R4 100 BACK (#197's F1 price, lost on prod 29 Sep)

Burt's row 46 on both MEAT HANGER sheets: G46 = D46*E46*C13*[1]PU!$C$17/2.98, H46 = G46*F46*I46*2 with
D46 = 1.22, E46 = 2.44, F46 = D46*E46, C13 = the SRD PU thickness, I46 = SRD PU selected — the F1 shape
term for term; [1]PU!C17 (32D PU FOAM) = 4100 in Burt's September PRICE list (read 30 Sep, input cells).

The GUARDS (`current`) come from the RT1 1b PROD snapshot only — "prod as it is now" — never from dev
or from memory. Anything that is not in the expected shape is REFUSED (surfaced, not forced).
RT1 Q-A default (BA): the 29 Sep R4 100 -> R4 095 move on prod was NOT a new Burt price, so 2415 / 3576
get their own R4 100 back. If Michael says it was deliberate, Manifest B STOPS (a new PU price is a
separate job).

    python make_manifest_b.py <1b all.json> <1b meat_hangers.json>     (writes manifest_b.yaml beside this file)
    python make_manifest_b.py --formula-only <1b all.json> <1b meat_hangers.json>
        the Q-A = YES variant for the BA: the MEAT HANGER formula entries only, no own price anywhere
        (writes manifest_b_formula_only.yaml)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
F1 = "(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2"
OLD_MH = "1.22*2.44*2"          # the MEAT HANGER lines' formula on prod (discovery 29 Sep)
PRICE = 4100.0                  # Burt's September PRICE list PU!C17, the price #197's F1 wrote
LINES = {                       # bom id -> (prod body name, why)
    5851: ("MEAT HANGER LARGE", "Burt MEAT BODY!H46"),
    6159: ("MEAT HANGER SMALL-MEDIUM", "Burt SMALL MEAT BODY UP TO 5,2!H46"),
    5585: ("ICECREAM BODY MEDIUM", "F1 line inheriting the global SRD PU material"),
    2415: ("FREEZER MEDIUM", "#197 F1 own price, lost on prod 29 Sep"),
    3576: ("FREEZER 2.3 METER", "#197 F1 own price, lost on prod 29 Sep"),
}


def main(*snaps):
    bom, trailers, materials, gen = {}, {}, {}, []
    for p in snaps:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        gen.append(f"{Path(p).name} {doc.get('generated_at')}")
        t = doc["tables"]
        bom.update({r["id"]: r for r in t["bill_of_materials"]})
        trailers.update({r["id"]: r for r in t["trailer_types"]})
        materials.update({r["id"]: r for r in t["materials"]})
    entries, problems, notes = [], [], []
    for bid, (body, why) in LINES.items():
        r = bom.get(bid)
        if r is None:
            problems.append(f"bom {bid}: not in the snapshots")
            continue
        tname = (trailers.get(r["trailer_type_id"]) or {}).get("name")
        mat = materials.get(r["material_id"]) or {}
        ident = dict(body_id=r["trailer_type_id"], body=[tname], section=r["bom_section"], bom_id=bid, line=mat.get("name"))
        if tname != body or r["bom_section"] != "SRD" or mat.get("name") != "PU":
            problems.append(f"bom {bid}: identity is ({tname!r}, {r['bom_section']!r}, {mat.get('name')!r}), "
                            f"expected ({body!r}, 'SRD', 'PU')")
            continue
        notes.append(f"bom {bid} {body}: material {mat.get('id')} {mat.get('name')} R{mat.get('price_per_unit')}, "
                     f"own price {r['unit_price_override']!r}, formula {r['formula_expression']!r}")
        f = r["formula_expression"]
        # a fresh copy of the identity per entry: a shared list makes yaml.safe_dump emit &id anchors
        if bid in (5851, 6159):
            if f == OLD_MH:
                entries.append({"finding": "B1", **ident, "body": [tname], "field": "formula_expression",
                                "current": f, "new": F1})
            elif f != F1:
                problems.append(f"bom {bid}: formula {f!r} is neither prod's {OLD_MH!r} nor F1 — refused")
        elif f != F1:
            problems.append(f"bom {bid}: formula {f!r} is not the F1 shape — refused")
        if FORMULA_ONLY:
            continue
        p = r["unit_price_override"]
        if p is None:
            entries.append({"finding": "B2", **ident, "body": [tname], "field": "unit_price_override",
                            "current": None, "new": PRICE})
        elif float(p) != PRICE:
            problems.append(f"bom {bid}: own price R{p} is neither null nor R{PRICE:g} — refused")
    for n in notes:
        print("  ", n)
    if problems:
        raise SystemExit("REFUSED:\n  " + "\n  ".join(problems))
    import yaml
    if FORMULA_ONLY:
        head = ("# RT1 Manifest B, FORMULA-ONLY variant (for the BA, if Q-A is YES): the two MEAT HANGER single-rear-door\n"
                "# PU lines to Burt's F1 shape (row 46) and NO own price — they inherit the SRD PU material (R4 095 since\n"
                "# 29 Sep, Burt's 21 Sep 32D price) like every other F1 PU line on prod. No price is set anywhere.\n"
                "# GENERATED by make_manifest_b.py --formula-only from the RT1 1b PROD snapshot — do not hand-edit.\n"
                f"# Guards = prod as it was in: {'; '.join(gen)}\n"
                "# Runs on: mirror, prod (after Manifest A) — only if the BA picks it instead of manifest_b.yaml.\n")
        note = "RT1 Manifest B (formula-only) — MEAT HANGER SRD PU lines to the F1 shape; prices untouched"
        out = HERE / "manifest_b_formula_only.yaml"
    else:
        head = ("# RT1 Manifest B — the single-rear-door PU lines: MEAT HANGER LARGE / SMALL-MEDIUM to Burt's F1 shape\n"
                "# (row 46) with their own R4 100; ICECREAM BODY MEDIUM 5585 and FREEZER MEDIUM 2415 / FREEZER 2.3 3576\n"
                "# their own R4 100 (2415 / 3576: back — #197 wrote it, prod lost it on 29 Sep).\n"
                "# GENERATED by make_manifest_b.py from the RT1 1b PROD snapshot — do not hand-edit.\n"
                f"# Guards = prod as it was in: {'; '.join(gen)}\n"
                "# Runs on: mirror, prod (after Manifest A). Not dev (dev's MEAT HANGER lines differ).\n")
        note = "RT1 Manifest B — MEAT HANGER SRD PU F1 shape + own R4 100; 5585 / 2415 / 3576 own R4 100"
        out = HERE / "manifest_b.yaml"
    doc = {"note": note, "changes": entries}
    out.write_text(head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8",
                   newline="\n")
    print(f"wrote {out.name}: {len(entries)} entries on {len({e['bom_id'] for e in entries})} lines")


FORMULA_ONLY = False

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--formula-only"]
    FORMULA_ONLY = len(args) != len(sys.argv[1:])
    main(*args)
