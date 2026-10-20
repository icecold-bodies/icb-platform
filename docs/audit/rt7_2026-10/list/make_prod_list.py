"""RT7 build (RT7_RULING_1 Q2/Q3 + 1A): the prod accepted list, walked one step at a time over ONE reference run
(the mirror loaded from the 19 Oct build paste's snapshot, against the refreshed golden), `reaccept` after each step
(H4). Writes the list WITHOUT amounts; `audit pin --write --snapshot ...` then pins every entry and records the pair.

    python make_prod_list.py <reports-dir> <old prod list> <out list path> <log path>
"""
import copy
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from tools.costing_audit.accepted import load_accepted
from tools.costing_audit.compare import reapply_accepted

REP, OLD, OUT, LOG = (Path(a) for a in sys.argv[1:5])
PACKS = ["chillers", "freezers", "icecream", "explosive", "smoke"]
ALL = PACKS[:4]
REVIEW = "2026-11-30"
reports = {p: json.loads((REP / f"prod_{p}.json").read_text(encoding="utf-8")) for p in PACKS}
lines: list[str] = []


def say(s=""):
    print(s)
    lines.append(s)


def counts(entries: list[dict], label: str) -> tuple[Counter, Counter]:
    tmp = OUT.with_name("_walk_tmp.yaml")                 # not *.prod.yaml: no amounts yet, so the loader is lenient
    tmp.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    acc = load_accepted(tmp)
    tmp.unlink()
    tot, sm = Counter(), Counter()
    for p in PACKS:
        c = reapply_accepted(reports[p], acc).counts
        (tot if p in ALL else sm).update(c)
    say(f"  {label:<66} All: FLAG {tot.get('FLAG', 0):3}  ACCEPTED {tot.get('ACCEPTED', 0):3}  EXPIRED {tot.get('EXPIRED', 0)}"
        f"  | smoke: FLAG {sm.get('FLAG', 0):2}  ACCEPTED {sm.get('ACCEPTED', 0):2}")
    return tot, sm


def find(entries, pred):
    hits = [i for i, e in enumerate(entries) if pred(e)]
    assert len(hits) == 1, hits
    return hits[0]


work = yaml.safe_load(OLD.read_text(encoding="utf-8"))
say(f"the reference run: {REP}; the list before: {OLD.name}, {len(work)} entries")
counts(work, "0. the list before (RT6's), unchanged")
PRUNES = [  # RULING_1 Q2: variant B — the four named stale entries, then the four other zero-cover ones
    ("prune SRD EPS (CHILLER 2.3 / LARGE)", lambda e: e["section"] == "SRD" and e.get("cause") == ["DIFF EPS", "BOTH EPS"]),
    ("prune the icecream ALU BUFFER PLATE", lambda e: e.get("cause") == "ALU BUFFER PLATE"),
    ("prune the EXPLOSIVE 2.7-4.8 plywood", lambda e: e["body"] == "EXPLOSIVE 2.7 TO 4.8"),
    ("prune the CHILLER MEDIUM 2317 DOOR RUBBER", lambda e: e.get("cause") == "2317 DOOR RUBBER"),
    ("prune SUB FRAME GALV PLATE / MOUNTING CLEATS", lambda e: e.get("cause") == ["GALV PLATE", "MOUNTING CLEATS"]),
    ("prune SRD DOOR FITTINGS (hinges, silplus, ...)", lambda e: e["section"] == "SRD DOOR FITTINGS"),
    ("prune icecream 4.8 DRD PU / hinges", lambda e: e["section"] == ["DRD", "DRD DOOR FITTINGS"]),
    ("prune the SRD PLYWOOD / GLUE LINE ruling", lambda e: e.get("cause") == ["PLYWOOD", "GLUE LINE"]),
]
say("\nH4 — one prune at a time, `reaccept` after each:")
for n, (label, pred) in enumerate(PRUNES, 1):
    work.pop(find(work, pred))
    counts(work, f"{n}. {label}")

say("\nthe four that stay — re-labelled, each with what clears it and one review date (Q3):")
SURVIVORS = {
    "TAPPING BLOCKS": dict(body=["icecream up to 3,2", "icecream up to 4.8"], mechanism="burt_sheet_formula_slip",
                           kind="tolerated", refs=["B-01", "B-02", "'icecream up to 3,2'!E41", "'icecream up to 4.8'!E45"],
                           reason="[BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping "
                                  "blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR "
                                  "PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). "
                                  "MES is right. Clears with Burt's fix list B-01, B-02."),
    "12MM PF PLYWOOD": dict(mechanism="probe_limit", refs=["the audit probe: it cannot tick the draft choice 12MM PF "
                                                           "PLYWOOD (bom 5653) on ICECREAM UP TO 4.8"],
                            reason="[PROBE] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when "
                                   "its draft choice is ticked; the audit probe cannot tick a draft choice, so the FLOOR "
                                   "reads it missing. A probe limit, not a template defect (Michael, 28 Sep)."),
    "MOUNTING BRACKET": dict(mechanism="burt_decision_pending", refs=["B-08"],
                             reason="[BURT] SMALL MOUNTING BRACKET on FREEZER MEDIUM: Burt's sheet prices BIG and SMALL "
                                    "at R68.80 (G178 / G179); the MES prices the small bracket on its own (-R125.68). "
                                    "Burt to decide (fix list B-08)."),
    "ALU PLATE": dict(mechanism="burt_decision_pending", refs=["B-10"],
                      reason="[BURT] 0.9 MM ALU PLATE on the EXPLOSIVE UP TO 2.7 single rear door: Burt's sheet prices "
                             "2 full sheets (F44 = F31; H44 = G44 x F44); the MES prices the plate it cuts (-R336.68). "
                             "Burt to decide (fix list B-10)."),
}
for cause, patch in SURVIVORS.items():
    i = find(work, lambda e, c=cause: e.get("cause") == c)
    work[i].update(patch)
    work[i]["review_by"] = REVIEW
    counts(work, f"re-label / refs / review_by {REVIEW}: {work[i]['mechanism']} ({cause})")

say("\nthe three hand edits Michael made on prod 6-7 Oct (RT7_RULING_1 Q1: lamination excluded — it is back at Burt's):")
FM = " UP TO 4.8 MT FREEZER  (2"
NEW = [
    dict(section="FLOOR", cause=["12MM PF PLYWOOD", "PRICE_DIFF EPS"], refs=["E-01", "E-02"],
         what="12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, "
              "6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct)"),
    dict(section="ROOF", cause=["PRICE_DIFF EPS"], refs=["E-02"],
         what="EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct; roof_floor_eps)"),
    dict(section="DRD DOOR FITTINGS", cause=["CSLB HINGES"], refs=["E-03"],
         what="CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73)"),
]
for e in NEW:
    work.append({"body": FM, "section": e["section"], "variant": "*", "cause": e["cause"], "kind": "tolerated",
                 "mechanism": "mes_updated_ahead_of_burt", "refs": e["refs"],
                 "reason": f"[MES AHEAD] FREEZER MEDIUM {e['section']}: Michael changed prod on purpose - {e['what']}; "
                           f"Burt's sheet has not caught up (keep in step: {', '.join(e['refs'])}).",
                 "owner": "BA", "review_by": REVIEW})
    counts(work, f"+ mes_updated_ahead_of_burt: FREEZER MEDIUM {e['section']}")
tot, sm = counts(work, f"the list after: {len(work)} entries (amounts next, by `audit pin`)")
OUT.write_text(yaml.safe_dump(work, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
say(f"\nwrote {OUT} ({len(work)} entries, unpinned)")
LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
