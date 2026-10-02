"""Generate manifest_p.yaml — RT2 Manifest P (RT2_DISPATCH Part 3, ratified in RT2_RULING_1): every ACTIVE PU
foam line that carries its own price is moved onto the shared PU price (Burt's R4 100, 32D) — the own price
removed AND, where the formula counts sheets instead of working out the volume, the formula put into Burt's
shape, TOGETHER (never one without the other: removing an own price from a sheet-counting formula is exactly
how the MEAT HANGERs reached R343k). 4G is the quote's foam toggle (the body's default, R6).

    python make_manifest_p.py <the R8 prod export all.json>        (writes manifest_p.yaml beside this file)

The 57 own-priced lines of RT2_RETURN_1 §4.1, mapped to Burt's rows in his 21 Sep GRP:
  * 18 CHILLER lines — OUT: Burt's chiller rows hard-code 3090 and Burt has ruled no PU on chillers (1 Oct);
    the drafts no longer offer PU there. Listed "unreachable, left as is" (G1's named exceptions).
  * 19 lines whose formula is ALREADY Burt's row term for term — finding P1: the own price goes.
  * 20 lines whose formula counts sheets (or lacks /2.98 x the panel) — finding P2: the formula becomes Burt's
    shape AND the own price goes, in one entry set.
Burt's shape per section (his row term for term, /2.98; the panel is 1.22 x 2.44, RHINORANGE 1.22 x 2.65):
    FRONT / DRD / SRD     (1.22*P*{SEC PU}/2.98)*(1.22*P)*2
    SIDES / ROOF / FLOOR  (1.22*P*{SEC PU}/2.98)*(1.22*P)*((length+{Waste})/1.22)
the spelling of RT1 Manifest M (= Michael's own 29 Sep freezer lines).

The GUARDS (`current`) are prod's exact values from the R8 export. Anything not in the expected shape —
identity, material, price, an existing thickness token on a P2 line, a missing master for the token — is
REFUSED, and so is a manifest that would leave any active PU foam line (other than the 18 chillers) with an
own price or without a thickness term (the G1 rule, checked on the export with P applied in memory).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED_PRICE = 4100.0           # every PU foam material, prod since RT1 (Burt's corrected 32D)
PU_FOAM = ("PU", "PU FOAM")
TOKEN = re.compile(r"\{\s*(FRONT|DRD|SRD|SIDES|ROOF|FLOOR)\s+PU\s*\}", re.I)
DOOR = ("FRONT", "DRD", "SRD")

P1 = {  # bom id -> (body id, body, section): the formula already IS Burt's row — the own price goes
    2560: (21, "FREEZER LARGE", "SRD"), 6345: (37, "EXPLOSIVE 2.7 TO 4.8", "SRD"),
    3948: (24, "EXPLOSIVE 4.9 AND UP", "SRD"), 5184: (34, "EXPLOSIVE UP TO 2.7", "SRD"),
    5577: (17, "ICECREAM BODY MEDIUM", "FRONT"), 5635: (17, "ICECREAM BODY MEDIUM", "SIDES"),
    5644: (17, "ICECREAM BODY MEDIUM", "ROOF"), 5651: (17, "ICECREAM BODY MEDIUM", "FLOOR"),
    5720: (16, "ICECREAM BODY SMALL", "FRONT"), 5751: (16, "ICECREAM BODY SMALL", "DRD"),
    5772: (16, "ICECREAM BODY SMALL", "SIDES"), 5779: (16, "ICECREAM BODY SMALL", "ROOF"),
    5786: (16, "ICECREAM BODY SMALL", "FLOOR"),
    5298: (18, "ICECREAM BODY LARGE", "FRONT"), 5306: (18, "ICECREAM BODY LARGE", "SRD"),
    5333: (18, "ICECREAM BODY LARGE", "DRD"), 5356: (18, "ICECREAM BODY LARGE", "SIDES"),
    5365: (18, "ICECREAM BODY LARGE", "ROOF"), 5372: (18, "ICECREAM BODY LARGE", "FLOOR"),
}
P2 = {  # bom id -> (body id, body, section): Burt's shape AND the own price goes, together
    6337: (37, "EXPLOSIVE 2.7 TO 4.8", "FRONT"), 6371: (37, "EXPLOSIVE 2.7 TO 4.8", "DRD"),
    6393: (37, "EXPLOSIVE 2.7 TO 4.8", "SIDES"), 6402: (37, "EXPLOSIVE 2.7 TO 4.8", "ROOF"),
    5176: (34, "EXPLOSIVE UP TO 2.7", "FRONT"), 5210: (34, "EXPLOSIVE UP TO 2.7", "DRD"),
    5232: (34, "EXPLOSIVE UP TO 2.7", "SIDES"), 5241: (34, "EXPLOSIVE UP TO 2.7", "ROOF"),
    3940: (24, "EXPLOSIVE 4.9 AND UP", "FRONT"), 3974: (24, "EXPLOSIVE 4.9 AND UP", "DRD"),
    3996: (24, "EXPLOSIVE 4.9 AND UP", "SIDES"), 4005: (24, "EXPLOSIVE 4.9 AND UP", "ROOF"),
    3600: (19, "FREEZER 2.3 METER", "DRD"),
    5726: (16, "ICECREAM BODY SMALL", "SRD"),
    6229: (36, "MEAT HANGER SMALL-MEDIUM", "FLOOR"),
    1797: (15, "RHINORANGE TRAILER", "FRONT"), 1808: (15, "RHINORANGE TRAILER", "DRD"),
    1830: (15, "RHINORANGE TRAILER", "SIDES"), 1840: (15, "RHINORANGE TRAILER", "ROOF"),
    1848: (15, "RHINORANGE TRAILER", "FLOOR"),
}
CHILLERS = {  # bom id -> body: out of P — unreachable (no PU on chillers, Burt 1 Oct), left as is
    3692: "CHILLER 2.3 METER", 3699: "CHILLER 2.3 METER", 3723: "CHILLER 2.3 METER", 3743: "CHILLER 2.3 METER",
    3751: "CHILLER 2.3 METER", 3759: "CHILLER 2.3 METER",
    3170: "CHILLER MEDIUM", 3179: "CHILLER MEDIUM", 3205: "CHILLER MEDIUM", 3227: "CHILLER MEDIUM",
    3237: "CHILLER MEDIUM", 3245: "CHILLER MEDIUM",
    3310: "CHILLER LARGE", 3319: "CHILLER LARGE", 3345: "CHILLER LARGE", 3367: "CHILLER LARGE",
    3377: "CHILLER LARGE", 3385: "CHILLER LARGE",
}
PANEL = {15: "2.65"}             # RHINORANGE's sheet is 1.22 x 2.65; every other body 1.22 x 2.44


def burt(section: str, body_id: int) -> str:
    p = PANEL.get(body_id, "2.44")
    head = f"(1.22*{p}*{{{section} PU}}/2.98)*(1.22*{p})"
    return head + ("*2" if section in DOOR else "*((length+{Waste})/1.22)")


def main(export: str) -> None:
    doc = json.loads(Path(export).read_text(encoding="utf-8"))
    t = doc["tables"]
    bom = {r["id"]: r for r in t["bill_of_materials"]}
    tts = {r["id"]: r for r in t["trailer_types"]}
    mats = {r["id"]: r for r in t["materials"]}
    problems, entries = [], []

    def masters(tid):
        return {(mats.get(r["material_id"]) or {}).get("name") for r in bom.values()
                if r["trailer_type_id"] == tid and r["is_body_option"]}

    for kind, lines in (("P1", P1), ("P2", P2)):
        for bid, (tid, body, sec) in sorted(lines.items()):
            r = bom.get(bid)
            if r is None:
                problems.append(f"bom {bid}: not in the export")
                continue
            m = mats.get(r["material_id"]) or {}
            name = (tts.get(r["trailer_type_id"]) or {}).get("name")
            ident = (r["trailer_type_id"], name, r["bom_section"], (m.get("name") or "").strip().upper())
            if ident[:3] != (tid, body, sec) or ident[3] not in PU_FOAM:
                problems.append(f"bom {bid}: identity {ident}, expected ({tid}, {body!r}, {sec!r}, 'PU')")
                continue
            if not (tts.get(tid) or {}).get("is_active") or r["is_body_option"]:
                problems.append(f"bom {bid}: not an active body's cost line")
            if float(m.get("price_per_unit") or 0) != SHARED_PRICE:
                problems.append(f"bom {bid}: material {m.get('id')} is R{m.get('price_per_unit')}, the shared PU price is R{SHARED_PRICE:g}")
            own, f = r["unit_price_override"], r["formula_expression"]
            if own is None:
                problems.append(f"bom {bid}: carries NO own price — not a P line any more")
                continue
            target = burt(sec, tid)
            if f"{sec} PU" not in masters(tid):
                problems.append(f"bom {bid}: the body has no {sec} PU master for the {{{sec} PU}} token")
            if kind == "P1":
                if f != target:
                    problems.append(f"bom {bid}: P1 needs Burt's shape already, found {f!r} (expected {target!r})")
                    continue
            else:
                if f == target:
                    problems.append(f"bom {bid}: P2 but the formula is already Burt's shape — it belongs in P1")
                    continue
                if TOKEN.search(f or "") and bid != 5726:      # 5726 has the token but not the /2.98 x panel
                    problems.append(f"bom {bid}: P2 formula {f!r} already carries a thickness token — check by hand")
                entries.append({"finding": "P2", "body_id": tid, "body": [body], "section": sec, "bom_id": bid,
                                "line": "PU", "field": "formula_expression", "current": f, "new": target})
            entries.append({"finding": kind, "body_id": tid, "body": [body], "section": sec, "bom_id": bid,
                            "line": "PU", "field": "unit_price_override", "current": own, "new": None})

    # the chillers: listed, never touched
    print("   OUT of P — unreachable (no PU on chillers, Burt 1 Oct), left as is:")
    for bid, body in sorted(CHILLERS.items()):
        r = bom.get(bid) or {}
        print(f"      bom {bid:>5} {body:<18} {r.get('bom_section')!s:<6} own R{r.get('unit_price_override')}  `{r.get('formula_expression')}`")

    # G1 on the export WITH P applied in memory: only the 18 chillers may remain
    after = {bid: dict(r) for bid, r in bom.items()}
    for e in entries:
        after[e["bom_id"]][e["field"]] = e["new"]
    viol = []
    for r in after.values():
        m = mats.get(r["material_id"]) or {}
        if (m.get("name") or "").strip().upper() not in PU_FOAM or r["is_body_option"]:
            continue
        if not (tts.get(r["trailer_type_id"]) or {}).get("is_active"):
            continue
        if r["unit_price_override"] is not None or not TOKEN.search(r["formula_expression"] or ""):
            viol.append(r["id"])
    extra = sorted(set(viol) - set(CHILLERS))
    if extra:
        problems.append(f"with P applied, these active PU foam lines would still fail G1: {extra}")
    print(f"   G1 with P applied in memory: violators = {len(viol)} (the {len(CHILLERS)} chillers: "
          f"{'yes' if set(viol) == set(CHILLERS) else 'NO'})")

    if problems:
        raise SystemExit("REFUSED:\n  " + "\n  ".join(problems))
    import yaml
    head = ("# RT2 Manifest P — every active own-priced PU foam line onto the shared PU price (RT2_DISPATCH Part 3,\n"
            "# RT2_RULING_1). P1 (19 lines): the formula already IS Burt's row; the own price goes. P2 (20 lines): the\n"
            "# formula becomes Burt's shape AND the own price goes — one transaction, never one without the other.\n"
            "# The 18 chiller PU lines are OUT (unreachable: no PU on chillers, Burt 1 Oct) and stay as they are.\n"
            "# GENERATED by make_manifest_p.py from the R8 PROD export — do not hand-edit.\n"
            f"# Guards = prod as it was in: {Path(export).name} {doc.get('generated_at')}\n"
            "# Runs on: mirror, prod — over the v1.59.3 code (the 4G bodies need 0050's default foam, R6).\n")
    out_doc = {"note": "RT2 Manifest P — own-priced PU foam lines onto the shared PU price (Burt's shape)",
               "changes": entries}
    out = HERE / "manifest_p.yaml"
    out.write_text(head + yaml.safe_dump(out_doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8",
                   newline="\n")
    n1 = sum(1 for e in entries if e["finding"] == "P1")
    n2 = len({e["bom_id"] for e in entries if e["finding"] == "P2"})
    print(f"wrote {out.name}: {len(entries)} entries on {len({e['bom_id'] for e in entries})} lines "
          f"(P1 {n1} own-price removals; P2 {n2} lines x formula + own price)")


if __name__ == "__main__":
    main(*sys.argv[1:])
