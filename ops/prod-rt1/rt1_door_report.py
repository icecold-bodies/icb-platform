"""RT1 1b — rear-door thickness report for the 14 Manifest A bodies. READ ONLY.

For each body: the Body Template's rear-door insulation masters (DRD EPS / DRD PU / SRD EPS / SRD PU,
body_option_group DRD|SRD, subgroup INSULATION — calculator.js `_doorInsulationPair`) and their
thickness (`variable_value`), against the door the calculator OPENS WITH on a fresh browser, derived
from the server draft exactly as calculator.js does on load:

  * radio folders (`DRD DOORS` / `SRD DOORS` / `NO REAR DOORS …` under `DOOR TYPE`): per sibling
    group the folder with folderValue 1 is on, else the FIRST in draft order (init step 8); a door is
    enabled when every radio/tickbox folder above its category is on (`_syncDrdSrdFromDraft`);
  * a category radio (CHILLER LARGE: categories DRD / SRD over the DOOR TYPE masters): the category
    with selectionValue 1, else the one whose master has body_option_default, else the first in draft
    order (init steps 4-5); the checked door selector wins (`_selectedRearDoor`).

The rear-door invariant: the opened door carries the thickness on exactly one of EPS / PU, the other
door is 0 / 0. A template whose thickness sits on the OTHER door was left there by a calculator
door-toggle (it PUTs /api/bom); the next time anyone opens that body in the calculator, the load-time
heal writes it back. Verdicts: OK · WRONG DOOR · BOTH DOORS · NO THICKNESS · UNSEEDED · NO DRAFT.
"Opens with" is a FRESH browser: a browser that already holds per-trailer door state in localStorage
can open with its own last door. "then -> now" compares with the committed snapshot given as argv[2].

Selects pricing/config columns and the draft's `updated_at` only — never `updated_by` or any person,
customer or contact column. A read-only session (default_transaction_read_only).

    python rt1_door_report.py <DATABASE_URL> [committed all.json]   (the 28 Sep snapshot, for a then/now column)
"""
import json
import re
import sys
from pathlib import Path

import psycopg

# The 14 Manifest A bodies (prod ids = dev ids; names are prod's, dev's second where they differ)
BODIES = {
    25: ("CHILLER 2.3 METER",), 26: ("CHILLER MEDIUM",), 27: ("CHILLER LARGE",),
    34: ("EXPLOSIVE UP TO 2.7",), 37: ("EXPLOSIVE 2.7 TO 4.8",), 24: ("EXPLOSIVE 4.9 AND UP",),
    19: ("FREEZER 2.3 METER",), 20: ("FREEZER MEDIUM",), 21: ("FREEZER LARGE",),
    16: ("ICECREAM BODY SMALL", "ICECREAM UP TO 3,2"), 17: ("ICECREAM BODY MEDIUM", "ICECREAM UP TO 4.8"),
    18: ("ICECREAM BODY LARGE", "ICECREAM 4.9 UP"),
    12: ("MEAT HANGER LARGE",), 36: ("MEAT HANGER SMALL-MEDIUM",),
}
DOORS = ("DRD", "SRD")


def norm(v):
    return str(v or "").strip().upper()


def js_order(nodes: dict) -> list:
    """Object.values() order: integer-like keys ascending first, then string keys in insertion order."""
    ints = sorted((k for k in nodes if re.fullmatch(r"0|[1-9][0-9]*", str(k))), key=int)
    rest = [k for k in nodes if k not in set(ints)]
    return [nodes[k] for k in ints + rest if isinstance(nodes[k], dict)]


def door_selector(name):
    """calculator.js _doorFromSelectorName."""
    n = norm(name)
    if "DOUBLE" in n:
        return "DRD"
    if "SINGLE" in n:
        return "SRD"
    return n if n in DOORS else None


def opened_door(draft: dict, masters: list) -> tuple:
    """(door or None, how) — the door a fresh calculator load selects for this draft."""
    nodes = draft.get("nodes") or {}
    ordered = js_order(nodes)
    # init step 8: radio / tickbox folder state; one on per radio sibling group, else the first
    fstate = {}
    groups = {}
    for n in ordered:
        if n.get("type") != "folder":
            continue
        mode = n.get("folderMode") or "container"
        if mode in ("radio", "tickbox"):
            fstate[n.get("id")] = str(n.get("folderValue")) == "1"
        if mode == "radio":
            groups.setdefault(str(n.get("parentId") or "root"), []).append(n)
    fallback = set()
    for g in groups.values():
        on = next((i for i, n in enumerate(g) if fstate.get(n.get("id"))), None)
        if on is None:
            on = 0
            fallback.add(g[0].get("id"))
        for i, n in enumerate(g):
            fstate[n.get("id")] = (i == on)

    def reachable(cat):
        pid = cat.get("parentId")
        used_fallback = False
        while pid:
            p = nodes.get(pid)
            if not p:
                break
            if p.get("type") == "folder" and (p.get("folderMode") or "container") in ("radio", "tickbox"):
                if not fstate.get(p.get("id")):
                    return False, False
                used_fallback |= p.get("id") in fallback
            pid = p.get("parentId")
        return True, used_fallback

    enabled, via_fallback = {}, False
    cats = {d: [n for n in ordered if n.get("type") == "category" and norm(n.get("sourceCategoryKey")) == d] for d in DOORS}
    for d in DOORS:
        if not cats[d]:
            continue
        res = [reachable(c) for c in cats[d]]
        enabled[d] = any(r for r, _ in res)
        via_fallback |= any(r and f for r, f in res)
    # the door selectors (masters named DRD / SRD / …DOUBLE… / …SINGLE…): a category radio seeds them
    sel = {}
    radio_groups = {}
    for n in ordered:
        if n.get("type") == "category" and (n.get("selectionMode") or "container") == "radio":
            radio_groups.setdefault(str(n.get("parentId") or "root"), []).append(n)
    for g in radio_groups.values():
        doors_in = [(n, door_selector(n.get("sourceCategoryKey"))) for n in g]
        if not any(d for _, d in doors_in):
            continue
        on = next((i for i, (n, _) in enumerate(doors_in) if str(n.get("selectionValue")) == "1"), None)
        how = "selectionValue 1"
        if on is None:
            for i, (n, d) in enumerate(doors_in):
                if d and any(m["default"] and door_selector(m["name"]) == d and m["grp"] == "DOOR TYPE" for m in masters):
                    on, how = i, "body_option_default"
                    break
        if on is None:
            on, how = 0, "first in draft order"
        d = doors_in[on][1]
        if d:
            sel[d] = how
    if len(sel) == 1 and all(enabled.get(d, True) for d in sel):
        d, how = next(iter(sel.items()))
        return d, f"DOOR TYPE radio ({how})"
    on = [d for d in DOORS if enabled.get(d)]
    if len(on) == 1:
        return on[0], "door folder" + (" (no folder marked: the first in draft order)" if via_fallback else " (folderValue 1)")
    if not on and any(cats.values()):
        return "NONE", "no rear door (another radio folder, e.g. NO REAR DOORS, is on)"
    return None, f"ambiguous (enabled: {on or 'none'})"


def main(url, snap_path=None):
    url = url.replace("postgresql+psycopg://", "postgresql://")
    then = {}
    if snap_path and Path(snap_path).is_file():
        snap = json.loads(Path(snap_path).read_text(encoding="utf-8"))
        then = {r["id"]: r.get("variable_value") for r in snap["tables"]["bill_of_materials"]}
        print(f"then = committed snapshot {Path(snap_path).name} generated {snap.get('generated_at')}")
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("show default_transaction_read_only")
        print("read_only session:", cur.fetchone()[0])
        cur.execute("SELECT id, name, configurator_v2, is_active FROM trailer_types WHERE id = ANY(%s)", (list(BODIES),))
        tt = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute("""SELECT b.trailer_type_id, b.id, m.name, coalesce(g.name, b.body_option_group),
                              b.body_option_subgroup, b.variable_value, b.body_option_default
                         FROM bill_of_materials b JOIN materials m ON m.id = b.material_id
                         LEFT JOIN body_option_groups g ON g.id = b.body_option_group_id
                        WHERE b.is_body_option AND b.trailer_type_id = ANY(%s) ORDER BY b.id""", (list(BODIES),))
        masters = {}
        for tid, mid, name, grp, sub, var, dflt in cur.fetchall():
            masters.setdefault(tid, []).append({"id": mid, "name": (name or "").strip(), "grp": norm(grp),
                                                "sub": norm(sub), "T": var, "default": bool(dflt)})
        # updated_at only — configurator_drafts.updated_by is a person column and is never selected
        cur.execute("SELECT trailer_type_id, payload, updated_at FROM configurator_drafts WHERE trailer_type_id = ANY(%s)",
                    (list(BODIES),))
        drafts = {t: (json.loads(p) if isinstance(p, str) else p, u) for t, p, u in cur.fetchall()}

    problems, summary = [], []
    print("\nbody | draft saved | opens with | template door | DRD EPS / DRD PU / SRD EPS / SRD PU (then -> now) | verdict")
    for tid in sorted(BODIES, key=lambda t: BODIES[t][0]):
        names = BODIES[tid]
        row = tt.get(tid)
        if row is None or row[0] not in names:
            problems.append(f"body {tid}: prod has {row and row[0]!r}, expected {names}")
            continue
        ms = masters.get(tid, [])
        pair = {}
        for d in DOORS:
            sibs = [m for m in ms if m["grp"] == d and m["sub"] == "INSULATION" and re.search("EPS|PU", m["name"], re.I)]
            eps = next((m for m in sibs if "EPS" in m["name"].upper()), None)
            pu = next((m for m in sibs if "PU" in m["name"].upper() and "EPS" not in m["name"].upper()), None)
            pair[d] = (eps, pu)
        cells = []
        for d in DOORS:
            for m in pair[d]:
                if m is None:
                    cells.append("-")
                    continue
                now = m["T"]
                if m["id"] in then and then[m["id"]] != now:
                    cells.append(f"{m['id']}:{then[m['id']]}->{now}")
                else:                      # unchanged since the snapshot, or not in it (the MEAT HANGERs)
                    cells.append(f"{m['id']}:{now}")
        carry = {d: [m for m in pair[d] if m and (m["T"] or 0) > 0] for d in DOORS}
        seeded = any(m and m["T"] is not None for d in DOORS for m in pair[d])
        tdoor = "+".join(d for d in DOORS if carry[d]) or ("none" if seeded else "unseeded")
        d = drafts.get(tid)
        if d:
            opens, how = opened_door(d[0], ms)
            saved = f"{d[1]:%Y-%m-%d %H:%M}" if d[1] else "?"
        else:
            opens, how, saved = None, "no server draft", "-"
        if not d:
            verdict = "NO DRAFT"
        elif not seeded:
            verdict = "UNSEEDED"
        elif tdoor == "none":
            verdict = "NO THICKNESS (the next open writes 0.06 on the opened door)"
        elif "+" in tdoor:
            verdict = "!! BOTH DOORS carry a thickness"
        elif opens is None:
            verdict = f"?? cannot tell the opened door ({how})"
        elif opens == "NONE":
            verdict = f"NO REAR DOOR on open — the thickness stays on {tdoor} (no heal runs)"
        elif tdoor == opens:
            verdict = "OK"
        else:
            verdict = f"!! WRONG DOOR — thickness on {tdoor}, the calculator opens with {opens}"
        door_masters = [f"{m['id']}:{m['name']}{'*' if m['default'] else ''}" for m in ms if m["grp"] == "DOOR TYPE"]
        print(f"{tid:>3} {names[0]:<26} | {saved} | {opens or '?'} [{how}] | {tdoor} | {' / '.join(cells)} | {verdict}"
              + (f"  (DOOR TYPE masters {door_masters})" if door_masters else ""))
        summary.append((tid, names[0], verdict))
    print("\nSUMMARY:", sum(1 for *_, v in summary if v == "OK"), "OK;",
          "; ".join(f"{t} {n}: {v}" for t, n, v in summary if v != "OK") or "no exceptions")
    if problems:
        print("!! IDENTITY:", "; ".join(problems))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
