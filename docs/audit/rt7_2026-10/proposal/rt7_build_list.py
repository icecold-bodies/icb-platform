"""RT7 §3.0 (prototype): from saved prod reports, walk the accepted-list plan one step at a time and reaccept after
each step (H4) — the four prunes, the tapping re-label, the new mes_updated_ahead_of_burt entries, then every entry
pinned at today's amounts. Writes the proposed list and a step log. Offline: no database.

    python rt7_build_list.py <reports-dir> <current prod yaml> <out-dir> [--extra-prunes]
"""
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from tools.costing_audit.accepted import load_accepted
from tools.costing_audit.compare import reapply_accepted, pin_key, cell_net

REP, CUR, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
EXTRA = "--extra-prunes" in sys.argv
OUT.mkdir(parents=True, exist_ok=True)
PACKS = ["chillers", "freezers", "icecream", "explosive", "smoke"]
ALL = PACKS[:4]
reports = {p: json.loads((REP / f"prod_{p}.json").read_text(encoding="utf-8")) for p in PACKS}
log_lines: list[str] = []


def say(s=""):
    print(s)
    log_lines.append(s)


def evaluate(entries: list[dict], label: str) -> dict:
    tmp = OUT / "_tmp.yaml"
    tmp.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    acc = load_accepted(tmp)
    res, tot = {}, Counter()
    for p in PACKS:
        rep = reapply_accepted(reports[p], acc)
        res[p] = rep
        if p in ALL:
            tot.update(rep.counts)
    sm = res["smoke"].counts
    say(f"  {label:<58} All: FLAG {tot.get('FLAG', 0):3}  ACCEPTED {tot.get('ACCEPTED', 0):3}  EXPIRED "
        f"{tot.get('EXPIRED', 0)}  | smoke: FLAG {sm.get('FLAG', 0):2}  ACCEPTED {sm.get('ACCEPTED', 0):2}")
    return res


cur = yaml.safe_load(CUR.read_text(encoding="utf-8"))
say(f"current list: {len(cur)} entries ({CUR.name})")
evaluate(cur, "0. today's list, unchanged")

# ── coverage of each current entry (primary or 'also') ──
res = evaluate(cur, "   (coverage pass)")
cover = Counter()
for p in PACKS:
    for c in res[p].cells:
        if c.status == "ACCEPTED":
            for a in [c.accepted, *(c.accepted.get("also") or [])]:
                cover[(p, json.dumps(a["body"]), json.dumps(a["section"]), json.dumps(a["cause"]))] += 1
say("  coverage per entry (All packs + smoke):")
for i, e in enumerate(cur):
    k = (json.dumps(e["body"]), json.dumps(e["section"]), json.dumps(e.get("cause")))
    n_all = sum(v for (p, *kk), v in cover.items() if tuple(kk) == k and p in ALL)
    n_sm = sum(v for (p, *kk), v in cover.items() if tuple(kk) == k and p == "smoke")
    say(f"    #{i:<2} {str(e['body'])[:40]:<40} {str(e['section'])[:28]:<28} {str(e.get('cause'))[:44]:<44} All {n_all:3}  smoke {n_sm:2}")


def find(entries, pred):
    hits = [i for i, e in enumerate(entries) if pred(e)]
    assert len(hits) == 1, hits
    return hits[0]


steps = [
    ("prune SRD EPS (CHILLER 2.3 / LARGE)", lambda e: e["section"] == "SRD" and e.get("cause") == ["DIFF EPS", "BOTH EPS"]),
    ("prune the icecream ALU BUFFER PLATE", lambda e: e.get("cause") == "ALU BUFFER PLATE"),
    ("prune the EXPLOSIVE 2.7-4.8 plywood", lambda e: e["body"] == "EXPLOSIVE 2.7 TO 4.8"),
    ("prune the CHILLER MEDIUM 2317 DOOR RUBBER", lambda e: e.get("cause") == "2317 DOOR RUBBER"),
]
if EXTRA:
    steps += [
        ("prune SUB FRAME GALV PLATE / MOUNTING CLEATS", lambda e: e.get("cause") == ["GALV PLATE", "MOUNTING CLEATS"]),
        ("prune SRD DOOR FITTINGS (hinges, silplus, ...)", lambda e: e["section"] == "SRD DOOR FITTINGS"),
        ("prune icecream 4.8 DRD PU / hinges", lambda e: e["section"] == ["DRD", "DRD DOOR FITTINGS"]),
        ("prune SRD PLYWOOD / GLUE LINE ruling", lambda e: e.get("cause") == ["PLYWOOD", "GLUE LINE"]),
    ]
work = copy.deepcopy(cur)
say("\nH4 — one prune at a time, reaccept after each:")
for n, (label, pred) in enumerate(steps, 1):
    i = find(work, pred)
    work.pop(i)
    evaluate(work, f"{n}. {label} (entry left the list)")

# ── re-label the tapping entry ──
i = find(work, lambda e: e.get("cause") == "TAPPING BLOCKS")
work[i].update({
    "body": ["icecream up to 3,2", "icecream up to 4.8"],
    "mechanism": "burt_sheet_formula_slip",
    "kind": "tolerated",
    "reason": "[BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: "
              "'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of "
              "TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Burt fix list B-01, B-02.",
    "refs": ["'icecream up to 3,2'!E41", "'icecream up to 4.8'!E45", "B-01", "B-02"],
})
evaluate(work, f"{len(steps) + 1}. re-label tapping = burt_sheet_formula_slip (icecream 3,2 + 4.8)")

# ── the new entries: Michael's prod edits, one per body x section ──
SHEET = {}
for p in PACKS:
    for c in reports[p]["cells"]:
        SHEET[c["trailer_name"]] = c["sheet"]
NEW = [
    ("CHILLER 2.3 METER", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("CHILLER MEDIUM", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("CHILLER LARGE", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("FREEZER 2.3 METER", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("ICECREAM BODY SMALL", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("ICECREAM BODY LARGE", "FLOOR", ["2*300 INT LAMINATION"], "2*300 INT LAMINATION R50.154 -> R57.2009 per m"),
    ("FREEZER MEDIUM", "FLOOR", ["12MM PF PLYWOOD", "2*300 INT LAMINATION", "PRICE_DIFF EPS"],
     "12MM PF PLYWOOD R223.15 -> R267.79 per m2 and 2*300 INT LAMINATION R50.154 -> R57.2009 per m; on roof_floor_eps "
     "also EPS R156.56 -> R206.00 per m2"),
    ("FREEZER MEDIUM", "ROOF", ["PRICE_DIFF EPS"], "EPS R156.56 -> R206.00 per m2 (roof_floor_eps)"),
    ("FREEZER MEDIUM", "DRD DOOR FITTINGS", ["CSLB HINGES"], "CSLB HINGES 6 -> 4 per double rear door (-R293.46)"),
    ("ICECREAM BODY MEDIUM", "FLOOR", ["2*300 INT LAMINATION"],
     "2*300 INT LAMINATION R50.154 -> R57.2009 per m (the 12MM PF PLYWOOD in the same cells is the probe-limit entry)"),
]
if "--16oct" in sys.argv:
    # prod 16 Oct 16:40: the INTERNAL LAMINATION recipe is back at R50.154 (the lamination cells PASS); only FREEZER
    # MEDIUM's three hand edits remain
    NEW = [
        ("FREEZER MEDIUM", "FLOOR", ["12MM PF PLYWOOD", "PRICE_DIFF EPS"],
         "12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, "
         "6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct)"),
        ("FREEZER MEDIUM", "ROOF", ["PRICE_DIFF EPS"],
         "EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct; roof_floor_eps)"),
        ("FREEZER MEDIUM", "DRD DOOR FITTINGS", ["CSLB HINGES"],
         "CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73)"),
    ]
for body, sec, cause, what in NEW:
    work.append({"body": SHEET[body], "section": sec, "variant": "*", "cause": cause, "kind": "tolerated",
                 "mechanism": "mes_updated_ahead_of_burt",
                 "reason": f"[MES AHEAD] {body} {sec}: Michael changed prod on purpose between 6 and 15 Oct 2026 - "
                           f"{what}; Burt's sheet has not caught up. Burt fix list: keep in step.",
                 "owner": "BA", "review_by": "2026-11-30"})
res = evaluate(work, f"{len(steps) + 2}. + {len(NEW)} mes_updated_ahead_of_burt entries (no pins yet)")

# ── pin every entry at today's amounts ──
pins: dict[int, dict[str, float]] = defaultdict(dict)
tmp_acc = load_accepted(OUT / "_tmp.yaml")
for p in PACKS:
    for c in res[p].cells:
        if c.status not in ("ACCEPTED", "EXPIRED"):
            continue
        for a in [c.accepted, *(c.accepted.get("also") or [])]:
            idx = next(j for j, e in enumerate(work)
                       if e["body"] == a["body"] and e["section"] == a["section"] and e.get("cause") == a["cause"])
            pins[idx][pin_key(c)] = cell_net(c)
for j, e in enumerate(work):
    e["amounts"] = dict(sorted(pins.get(j, {}).items()))
final = evaluate(work, f"{len(steps) + 3}. every entry pinned at today's amounts")
(OUT / "accepted_differences.prod.proposed.yaml").write_text(
    yaml.safe_dump(work, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
say("\nper entry: cells pinned (All + smoke-only keys), amount range")
for j, e in enumerate(work):
    v = list(e["amounts"].values())
    rng = f"{min(v):+9.2f} .. {max(v):+9.2f}" if v else "(none)"
    say(f"  #{j:<2} {e.get('mechanism') or e.get('kind'):<26} {str(e['body'])[:34]:<34} {str(e['section'])[:20]:<20} "
        f"{len(v):3} pins  {rng}")

# ── negative controls on the pin ──
say("\nNC — move one pin and reaccept:")
j = next(j for j, e in enumerate(work) if e.get("mechanism") == "burt_sheet_formula_slip")
k = sorted(work[j]["amounts"])[0]
for d in (1.00, 0.01, 0.02, -1.00):
    w2 = copy.deepcopy(work)
    w2[j]["amounts"][k] = round(w2[j]["amounts"][k] + d, 2)
    r2 = evaluate(w2, f"pin {k[:52]} moved {d:+.2f}")
    for p in PACKS:
        for c in r2[p].cells:
            if c.reason and c.reason.startswith("ACCEPTED_AMOUNT_CHANGED"):
                say(f"      {p}: {c.status} {pin_key(c)} :: {c.reason}")
w3 = copy.deepcopy(work)
w3[j]["amounts"].pop(k)
r3 = evaluate(w3, "pin removed for that cell")
for p in PACKS:
    for c in r3[p].cells:
        if c.reason and c.reason.startswith("ACCEPTED_AMOUNT_CHANGED"):
            say(f"      {p}: {c.status} {pin_key(c)} :: {c.reason}")
(OUT / "_tmp.yaml").unlink()
(OUT / "steps.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

say("\nfinal per-pack counts:")
for p in PACKS:
    say(f"  {p:<10} {dict(sorted(final[p].counts.items()))}")
