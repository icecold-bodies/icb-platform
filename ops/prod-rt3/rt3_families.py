"""RT3 — the six body families on PROD (RT3_RULING_1 Q3, Q4, Q5, Q7). Data only; over v1.60.0 (alembic 0051).

Michael's families (RT3_DISPATCH; colours approved 2 Oct, RT3_RETURN_1 §5), in his order:

    1 EXPLOSIVE  #E03131   the EXPLOSIVE group (#1, template explosive_quote) — colour + order
    2 CHILLER    #168ED9   NEW, no template (the chillers print the default document, as today)
    3 FREEZER    #4263EB   the FREEZER group (#4, freezer_quote) — colour + order
    4 MEAT       #D66A0B   the MEATHANGER group (#3, meathanger_quote) RENAMED to MEAT — colour + order
    5 ICE CREAM  #D63384   NEW, no template
    6 OTHER      #7D858C   NEW, no template

    RHINORANGE TRAILER (15) -> OTHER, keeping rhinorange_quote through its OWN override (#2); the then-empty
    RHINORANGE group (#2) is deleted. Every one of the 41 bodies (active or not) gets its family.

THE GUARD (RT3_DISPATCH design 2): no ACTIVE body's resolved quote template changes. The resolved template is
app/services resolve_report_template, mirrored here: the body's override (if set and active), else its group's
template (if set and active), else none (the default document). It is checked twice: on the plan before any
write, and again INSIDE the apply's transaction, from the database, after every write and before the commit (a
mismatch rolls everything back). The only bodies allowed to change resolved template are the 10 soft-deleted
copies of RT3_RULING_1 Q5 (default document -> their family's template; 0 saved costings, hidden everywhere).

    DATABASE_URL=...  python rt3_families.py --target prod|mirror                               dry-run
    DATABASE_URL=...  python rt3_families.py --target prod|mirror --apply --out-dir DIR         apply
    DATABASE_URL=...  python rt3_families.py --target prod|mirror --revert J --out-dir DIR      revert

Guards: every row the plan names must hold exactly its before-state, or exactly its after-state (already applied:
a no-op); a body or group the plan does not know refuses (prod moved since the 2 Oct discovery); anything else
refuses with exit 2 and writes nothing (one transaction, rows locked). Revert needs every journaled row to hold
exactly what the journal wrote, and puts each back column for column (the deleted group comes back with its own
id). psycopg only, independent of the app code. Reads no customer, contact, user or person column.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

TARGETS = {"prod": "icb_platform", "mirror": "icb_prodmirror"}
S = "icb_costings"
# TESTS ONLY: restrict every read to bodies / groups whose name starts with this prefix, so a synthetic plan can
# run in the shared _test database. None on prod and the mirror: the plan must account for the WHOLE table.
NAME_PREFIX: str | None = None

# (family, existing group id or None = NEW, its name before, colour, sort_order, template slug or None)
FAMILIES = [
    ("EXPLOSIVE", 1, "EXPLOSIVE", "#E03131", 1, "explosive_quote"),
    ("CHILLER", None, None, "#168ED9", 2, None),
    ("FREEZER", 4, "FREEZER", "#4263EB", 3, "freezer_quote"),
    ("MEAT", 3, "MEATHANGER", "#D66A0B", 4, "meathanger_quote"),
    ("ICE CREAM", None, None, "#D63384", 5, None),
    ("OTHER", None, None, "#7D858C", 6, None),
]
NEW_DESCRIPTION = "{name} bodies (RT3 body family)."
# groups deleted once empty: id -> (name, template slug)
DELETE_GROUPS = {2: ("RHINORANGE", "rhinorange_quote")}
# bodies whose OWN override is set: id -> template slug (it keeps the body's resolved template)
OVERRIDES = {15: "rhinorange_quote"}
# every body on prod (2 Oct discovery, out-20261002-184220): id -> (name, active, group id before, family)
BODIES = {
    25: ("CHILLER 2.3 METER", True, None, "CHILLER"),
    27: ("CHILLER LARGE", True, None, "CHILLER"),
    26: ("CHILLER MEDIUM", True, None, "CHILLER"),
    37: ("EXPLOSIVE 2.7 TO 4.8", True, 1, "EXPLOSIVE"),
    24: ("EXPLOSIVE 4.9 AND UP", True, 1, "EXPLOSIVE"),
    34: ("EXPLOSIVE UP TO 2.7", True, 1, "EXPLOSIVE"),
    19: ("FREEZER 2.3 METER", True, 4, "FREEZER"),
    21: ("FREEZER LARGE", True, 4, "FREEZER"),
    20: ("FREEZER MEDIUM", True, 4, "FREEZER"),
    18: ("ICECREAM BODY LARGE", True, None, "ICE CREAM"),
    17: ("ICECREAM BODY MEDIUM", True, None, "ICE CREAM"),
    16: ("ICECREAM BODY SMALL", True, None, "ICE CREAM"),
    41: ("Manni RIGIDS CB", True, None, "OTHER"),
    12: ("MEAT HANGER LARGE", True, 3, "MEAT"),
    36: ("MEAT HANGER SMALL-MEDIUM", True, 3, "MEAT"),
    15: ("RHINORANGE TRAILER", True, 2, "OTHER"),
    2: ("ADVANTICA BODY", False, None, "OTHER"),
    1: ("ADV VACUUM PANELS", False, None, "OTHER"),
    10: ("CHESTER SPEC MEAT BODY", False, 3, "MEAT"),
    13: ("DRY FREIGHT TRAILER", False, None, "OTHER"),
    23: ("EXPLOSIVE 2.7 TO 4.8 OLD [deleted-23]", False, None, "EXPLOSIVE"),
    22: ("EXPLOSIVE UP TO 2.7 [deleted-22]", False, None, "EXPLOSIVE"),
    28: ("EXPLOSIVE UP TO 2.7 [deleted-28]", False, None, "EXPLOSIVE"),
    29: ("EXPLOSIVE UP TO 2.7 [deleted-29]", False, None, "EXPLOSIVE"),
    30: ("EXPLOSIVE UP TO 2.7 [deleted-30]", False, None, "EXPLOSIVE"),
    31: ("EXPLOSIVE UP TO 2.7 [deleted-31]", False, None, "EXPLOSIVE"),
    32: ("EXPLOSIVE UP TO 2.7 [deleted-32]", False, None, "EXPLOSIVE"),
    33: ("EXPLOSIVE UP TO 2.7 [deleted-33]", False, None, "EXPLOSIVE"),
    14: ("GRP TRAILERS", False, None, "OTHER"),
    4: ("MANNI BAKKI RIGIDS", False, None, "OTHER"),
    7: ("MANNI DF", False, None, "OTHER"),
    3: ("MANNI RIGIDS CB", False, None, "OTHER"),
    5: ("MANNI RIGIDS FB", False, None, "OTHER"),
    6: ("MANNI TRAILERS", False, None, "OTHER"),
    39: ("RIGID DRY FREIGHT", False, None, "OTHER"),
    38: ("RIGID DRY FREIGHT [deleted-38]", False, None, "OTHER"),
    8: ("RIGID DRY FREIGHT [deleted-8]", False, None, "OTHER"),
    11: ("SMALL MEAT BODY UP TO 5,2 [deleted-11]", False, None, "MEAT"),
    35: ("SMALL MEAT BODY UP TO 5,2 [deleted-35]", False, None, "MEAT"),
    9: ("TAUT LINER RIGID", False, None, "OTHER"),
    40: ("TESTING EVERYTHING", False, None, "OTHER"),
}
# RT3_RULING_1 Q5 — the ONLY bodies allowed to change resolved template (soft-deleted copies, 0 costings)
ALLOWED_TEMPLATE_CHANGES = {23, 22, 28, 29, 30, 31, 32, 33, 11, 35}


class Refused(Exception):
    """A guard refused: the rows are not where the plan says. Raised inside the transaction: nothing is written."""


def tool_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def plan_sha() -> str:
    """The plan's own fingerprint (what the window reviews): families, deletes, overrides, bodies, allowances."""
    blob = json.dumps({"families": FAMILIES, "delete": sorted(DELETE_GROUPS.items()), "overrides": sorted(OVERRIDES.items()),
                       "bodies": sorted(BODIES.items()), "allowed": sorted(ALLOWED_TEMPLATE_CHANGES)}, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def connect(target: str, read_only: bool):
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    if not url:
        raise SystemExit("REFUSED: DATABASE_URL is not set")
    kw = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    cx = psycopg.connect(url, autocommit=True, **kw)
    db = cx.execute("select current_database()").fetchone()[0]
    if db != TARGETS[target]:
        cx.close()
        raise SystemExit(f"REFUSED: --target {target} expects database {TARGETS[target]!r}; this is {db!r}")
    return cx, db


# ── reading ─────────────────────────────────────────────────────────────────

def has_columns(cx) -> bool:
    n = cx.execute(f"""select count(*) from information_schema.columns where table_schema = %s
                       and table_name = 'trailer_groups' and column_name in ('colour', 'sort_order')""", (S,)).fetchone()[0]
    return n == 2


def templates(cx) -> dict:
    """slug -> (id, is_active)"""
    return {r[1]: (r[0], r[2]) for r in cx.execute(f"select id, slug, is_active from {S}.report_templates").fetchall()}


GROUP_COLS = "id, name, description, report_template_id, colour, sort_order, created_at"


def _scope() -> tuple[str, tuple]:
    return ("", ()) if NAME_PREFIX is None else (" where name like %s", (NAME_PREFIX.replace("%", r"\%") + "%",))


def groups(cx, lock: bool = False) -> dict:
    w, p = _scope()
    rows = cx.execute(f"select {GROUP_COLS} from {S}.trailer_groups{w} order by id" + (" for update" if lock else ""),
                      p).fetchall()
    return {r[0]: dict(zip(GROUP_COLS.split(", "), r)) for r in rows}


def bodies(cx, lock: bool = False) -> dict:
    w, p = _scope()
    rows = cx.execute(f"""select id, name, is_active, group_id, override_report_template_id from {S}.trailer_types{w}
                          order by id""" + (" for update" if lock else ""), p).fetchall()
    return {r[0]: {"id": r[0], "name": r[1], "is_active": r[2], "group_id": r[3], "override_id": r[4]} for r in rows}


def resolved(body: dict, grps: dict, active_tmpl: set) -> int | None:
    """app/services resolve_report_template, on rows: override (active) -> group's template (active) -> None."""
    o = body["override_id"]
    if o and o in active_tmpl:
        return o
    g = grps.get(body["group_id"])
    t = g["report_template_id"] if g else None
    return t if t and t in active_tmpl else None


# ── the plan against the database ───────────────────────────────────────────

def check(cx) -> dict:
    """Every guard, before any write. Returns {todo, done, after_groups, after_bodies, ...} or raises Refused."""
    if not has_columns(cx):
        raise Refused("trailer_groups has no colour / sort_order: the families go over v1.60.0 (alembic 0051) only")
    tm = templates(cx)
    active_tmpl = {i for i, a in tm.values() if a}
    tid = {}
    for slug in {f[5] for f in FAMILIES if f[5]} | {v[1] for v in DELETE_GROUPS.values()} | set(OVERRIDES.values()):
        if slug not in tm:
            raise Refused(f"no report template {slug!r}")
        tid[slug] = tm[slug][0]
    g, b = groups(cx), bodies(cx)
    todo, done = [], []

    # bodies: exactly the plan's 41, each at its before- or after-state
    unknown = sorted(set(b) - set(BODIES))
    if unknown:
        raise Refused("bodies the plan does not know (prod moved since the discovery): "
                      + ", ".join(f"{i} {b[i]['name']!r}" for i in unknown))
    for i, (name, active, _gb, _fam) in BODIES.items():
        if i not in b:
            raise Refused(f"no body id {i} ({name})")
        if b[i]["name"] != name:
            raise Refused(f"body id {i} is named {b[i]['name']!r}; the plan expects {name!r}")
        if bool(b[i]["is_active"]) != active:
            raise Refused(f"body id {i} {name} is {'active' if b[i]['is_active'] else 'inactive'}; the plan expects "
                          f"{'active' if active else 'inactive'}")

    # existing family groups: their before-state, or their after-state
    fam_gid: dict[str, int | None] = {}
    by_name = {gr["name"]: gr for gr in g.values()}
    for fam, gid, name_before, colour, order, slug in FAMILIES:
        want_t = tid.get(slug) if slug else None
        if gid is not None:
            gr = g.get(gid)
            if gr is None:
                raise Refused(f"no group id {gid} ({name_before})")
            if gr["report_template_id"] != want_t:
                raise Refused(f"group {gid} {gr['name']!r} prints template {gr['report_template_id']!r}; the plan expects {slug}")
            after = (fam, colour, order)
            now = (gr["name"], gr["colour"], gr["sort_order"])
            if now == after:
                done.append(f"group {gid} {fam}")
            elif gr["name"] == name_before and gr["colour"] is None and gr["sort_order"] == 100:
                todo.append(("update_group", gid, fam, colour, order))
            else:
                raise Refused(f"group {gid} holds name/colour/order {now!r}; the plan expects {(name_before, None, 100)!r} "
                              f"or {after!r}")
            clash = by_name.get(fam)
            if clash and clash["id"] != gid:
                raise Refused(f"a second group already carries the name {fam!r} (id {clash['id']})")
            fam_gid[fam] = gid
        else:
            gr = by_name.get(fam)
            if gr is None:
                todo.append(("create_group", fam, colour, order))
                fam_gid[fam] = None                       # created in the apply
            elif (gr["colour"], gr["sort_order"], gr["report_template_id"]) == (colour, order, None):
                done.append(f"group {gr['id']} {fam} (created)")
                fam_gid[fam] = gr["id"]
            else:
                raise Refused(f"a group {fam!r} already exists (id {gr['id']}) and is not the plan's: "
                              f"{(gr['colour'], gr['sort_order'], gr['report_template_id'])!r}")

    # bodies: group before -> family's group; overrides
    for i, (name, _a, gb, fam) in BODIES.items():
        cur = b[i]["group_id"]
        target = fam_gid[fam]
        if target is not None and cur == target:
            if gb != target:
                done.append(f"body {i} -> {fam}")
        elif cur == gb:
            todo.append(("move_body", i, fam))
        else:
            raise Refused(f"body {i} {name} is in group {cur!r}; the plan expects {gb!r} (before) or the {fam} group (after)")
    for i, slug in OVERRIDES.items():
        cur = b[i]["override_id"]
        if cur == tid[slug]:
            done.append(f"override body {i} {slug}")
        elif cur is None:
            todo.append(("set_override", i, slug))
        else:
            raise Refused(f"body {i} has override {cur!r}; the plan expects none (before) or {slug} (after)")
    for i, b_ in b.items():
        if i not in OVERRIDES and b_["override_id"] is not None:
            raise Refused(f"body {i} {b_['name']} has an override ({b_['override_id']}) the plan does not know")

    # groups to delete: present with their name + template (no body but the plan's movers in them), or gone
    orphan_refs = dict(cx.execute(f"""select group_id, count(*) from {S}.orphaned_template_assignments
                                      where group_id is not null group by 1""").fetchall())
    for gid, (name, slug) in DELETE_GROUPS.items():
        gr = g.get(gid)
        if gr is None:
            if name in by_name:
                raise Refused(f"group {name!r} exists with another id ({by_name[name]['id']}); the plan deletes id {gid}")
            done.append(f"delete group {gid} {name}")
            continue
        if gr["name"] != name or gr["report_template_id"] != tid[slug]:
            raise Refused(f"group {gid} is {gr['name']!r} / template {gr['report_template_id']!r}; the plan deletes {name} / {slug}")
        stray = [i for i, b_ in b.items() if b_["group_id"] == gid and BODIES[i][2] != gid]
        movers = [i for i, b_ in b.items() if b_["group_id"] == gid and BODIES[i][2] == gid]
        if stray:
            raise Refused(f"group {gid} {name} holds bodies the plan does not move out of it: {sorted(stray)}")
        if orphan_refs.get(gid):
            raise Refused(f"group {gid} {name} is named by {orphan_refs[gid]} orphaned template assignment(s)")
        todo.append(("delete_group", gid, name, len(movers)))

    unplanned = sorted(set(g) - {f[1] for f in FAMILIES if f[1] is not None} - set(DELETE_GROUPS)
                       - {fam_gid[f[0]] for f in FAMILIES if fam_gid.get(f[0])})
    if unplanned:
        raise Refused("groups the plan does not know: " + ", ".join(f"{i} {g[i]['name']!r}" for i in unplanned))
    return {"todo": todo, "done": done, "tid": tid, "active_tmpl": active_tmpl, "groups": g, "bodies": b,
            "fam_gid": fam_gid, "templates": tm}


def simulate(st: dict) -> tuple[dict, dict]:
    """The plan's after-state as rows (for the dry-run's before -> after and the plan-level guard)."""
    g = {k: dict(v) for k, v in st["groups"].items()}
    b = {k: dict(v) for k, v in st["bodies"].items()}
    fam_gid = dict(st["fam_gid"])
    fake = -1
    for fam, gid, _nb, colour, order, slug in FAMILIES:
        if gid is not None:
            g[gid].update(name=fam, colour=colour, sort_order=order)
        elif fam_gid[fam] is None:
            g[fake] = {"id": fake, "name": fam, "report_template_id": None, "colour": colour, "sort_order": order}
            fam_gid[fam] = fake
            fake -= 1
    for i, (_n, _a, _gb, fam) in BODIES.items():
        b[i]["group_id"] = fam_gid[fam]
    for i, slug in OVERRIDES.items():
        b[i]["override_id"] = st["tid"][slug]
    for gid in DELETE_GROUPS:
        g.pop(gid, None)
    return g, b


def guard(before_g, before_b, after_g, after_b, active_tmpl) -> list[str]:
    """The template guard: [] or the reasons it fails."""
    bad = []
    for i, (name, active, _gb, _fam) in BODIES.items():
        rb = resolved(before_b[i], before_g, active_tmpl)
        ra = resolved(after_b[i], after_g, active_tmpl)
        if rb != ra and (active or i not in ALLOWED_TEMPLATE_CHANGES):
            bad.append(f"body {i} {name} ({'active' if active else 'inactive'}) would print template {ra!r} instead of {rb!r}")
    return bad


def _tname(tm: dict, t) -> str:
    if t is None:
        return "(default document)"
    for slug, (i, _a) in tm.items():
        if i == t:
            return f"{slug} #{t}"
    return f"#{t}"


def print_plan(st: dict, after_g: dict, after_b: dict) -> None:
    tm = st["templates"]
    print(f"   {'id':>3} {'body':<38} {'act':<3} {'family before':<14} {'family after':<10} {'template before':<26} "
          f"{'template after':<26}")
    for i, (name, active, gb, fam) in sorted(BODIES.items(), key=lambda kv: (not kv[1][1], kv[1][3], kv[1][0])):
        bg = st["groups"].get(st["bodies"][i]["group_id"])
        rb = resolved(st["bodies"][i], st["groups"], st["active_tmpl"])
        ra = resolved(after_b[i], after_g, st["active_tmpl"])
        note = "" if rb == ra else ("   (Q5: allowed, a soft-deleted copy)" if i in ALLOWED_TEMPLATE_CHANGES else "   !! CHANGES")
        print(f"   {i:>3} {name[:38]:<38} {'Y' if active else 'n':<3} {(bg['name'] if bg else '-'):<14} {fam:<10} "
              f"{_tname(tm, rb):<26} {_tname(tm, ra):<26}{note}")
    print("   families (dropdown order):")
    for fam, gid, nb, colour, order, slug in FAMILIES:
        n_act = sum(1 for i, v in BODIES.items() if v[3] == fam and v[1])
        n_all = sum(1 for v in BODIES.values() if v[3] == fam)
        src = f"group {gid} ({nb}{' -> ' + fam if nb != fam else ''})" if gid is not None else "NEW group"
        print(f"     {order} {fam:<10} {colour}  {src:<28} template {slug or '(none: the default document)':<20} "
              f"bodies {n_act} active / {n_all}")


def dry_run(cx, db: str, target: str) -> int:
    print(f"database {db} (--target {target}); RT3 body families; plan sha256 {plan_sha()[:16]}…; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        cx.execute("set transaction read only")
        st = check(cx)
        ag, ab = simulate(st)
        print_plan(st, ag, ab)
        bad = guard(st["groups"], st["bodies"], ag, ab, st["active_tmpl"])
        if bad:
            raise Refused("THE TEMPLATE GUARD: " + "; ".join(bad))
        n_act = sum(1 for v in BODIES.values() if v[1])
        changed = sorted(i for i in BODIES if resolved(st["bodies"][i], st["groups"], st["active_tmpl"])
                         != resolved(ab[i], ag, st["active_tmpl"]))
        print(f"TEMPLATE GUARD: {n_act} of {n_act} active bodies keep their resolved template; "
              f"changed: {changed or 'none'} (allowed: the Q5 soft-deleted copies)")
        for t in st["todo"]:
            print("  APPLY " + " ".join(str(x) for x in t))
        print(f"{len(st['todo'])} to apply, {len(st['done'])} already applied.")
        print("nothing to apply." if not st["todo"] else "(DRY RUN — nothing written. Re-run with --apply.)")
    return 0


def write_file(out_dir: Path, stem: str, data: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    part = final.with_name(final.name + ".part")
    with open(part, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return part, final


def _row(gr: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in gr.items()}


def apply(cx, db: str, target: str, out_dir: Path) -> int:
    print(f"database {db} (--target {target}); RT3 body families; plan sha256 {plan_sha()[:16]}…; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        groups(cx, lock=True)
        bodies(cx, lock=True)
        st = check(cx)
        if not st["todo"]:
            print(f"0 to apply, {len(st['done'])} already applied.")
            print("nothing to apply.")
            return 0
        ag, ab = simulate(st)
        bad = guard(st["groups"], st["bodies"], ag, ab, st["active_tmpl"])
        if bad:
            raise Refused("THE TEMPLATE GUARD (plan): " + "; ".join(bad))
        g0, b0 = st["groups"], st["bodies"]
        fam_gid = dict(st["fam_gid"])
        journal = {"tool": "rt3_families", "plan_sha256": plan_sha(), "tool_sha256": tool_sha(), "target": target,
                   "database": db, "groups_updated": [], "groups_created": [], "groups_deleted": [], "bodies": [],
                   "overrides": []}
        for t in st["todo"]:                       # creates and updates first, so every family has its id
            if t[0] == "create_group":
                _, fam, colour, order = t
                gid = cx.execute(f"""insert into {S}.trailer_groups (name, description, report_template_id, colour, sort_order,
                                     created_at) values (%s, %s, null, %s, %s, now() at time zone 'utc') returning id""",
                                 (fam, NEW_DESCRIPTION.format(name=fam), colour, order)).fetchone()[0]
                fam_gid[fam] = gid
                journal["groups_created"].append({"id": gid, "name": fam, "colour": colour, "sort_order": order})
                print(f"  CREATE group {gid} {fam} {colour} order {order}")
            elif t[0] == "update_group":
                _, gid, fam, colour, order = t
                got = cx.execute(f"""update {S}.trailer_groups set name = %s, colour = %s, sort_order = %s
                                     where id = %s and name = %s and colour is null and sort_order = 100 returning id""",
                                 (fam, colour, order, gid, g0[gid]["name"])).fetchall()
                if got != [(gid,)]:
                    raise RuntimeError(f"group {gid}: the update returned {got!r}")
                journal["groups_updated"].append({"before": _row(g0[gid]), "after": {"name": fam, "colour": colour,
                                                                                     "sort_order": order}})
                print(f"  UPDATE group {gid} {g0[gid]['name']!r} -> {fam!r} {colour} order {order}")
        for t in st["todo"]:
            if t[0] == "move_body":
                _, i, fam = t
                gb, ga = b0[i]["group_id"], fam_gid[fam]
                got = cx.execute(f"""update {S}.trailer_types set group_id = %s where id = %s and name = %s
                                     and group_id is not distinct from %s returning id""", (ga, i, BODIES[i][0], gb)).fetchall()
                if got != [(i,)]:
                    raise RuntimeError(f"body {i}: the move returned {got!r}")
                journal["bodies"].append({"id": i, "name": BODIES[i][0], "group_before": gb, "group_after": ga})
            elif t[0] == "set_override":
                _, i, slug = t
                got = cx.execute(f"""update {S}.trailer_types set override_report_template_id = %s where id = %s and name = %s
                                     and override_report_template_id is null returning id""",
                                 (st["tid"][slug], i, BODIES[i][0])).fetchall()
                if got != [(i,)]:
                    raise RuntimeError(f"body {i}: the override returned {got!r}")
                journal["overrides"].append({"id": i, "name": BODIES[i][0], "before": None, "after": st["tid"][slug]})
                print(f"  OVERRIDE body {i} {BODIES[i][0]} -> {slug} #{st['tid'][slug]}")
        moved = len(journal["bodies"])
        print(f"  MOVED {moved} bodies to their family")
        for t in st["todo"]:
            if t[0] == "delete_group":
                _, gid, name, _n = t
                left = cx.execute(f"select count(*) from {S}.trailer_types where group_id = %s", (gid,)).fetchone()[0]
                if left:
                    raise RuntimeError(f"group {gid} {name} still holds {left} bodies after the moves")
                got = cx.execute(f"delete from {S}.trailer_groups where id = %s and name = %s returning id", (gid, name)).fetchall()
                if got != [(gid,)]:
                    raise RuntimeError(f"group {gid}: the delete returned {got!r}")
                journal["groups_deleted"].append(_row(g0[gid]))
                print(f"  DELETE group {gid} {name} (empty)")
        # THE GUARD, from the database, inside the transaction, before the commit
        g1, b1 = groups(cx), bodies(cx)
        bad = guard(g0, b0, g1, b1, st["active_tmpl"])
        if bad:
            raise Refused("THE TEMPLATE GUARD (database, before commit): " + "; ".join(bad))
        journal["applied_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        journal["resolved_before"] = {str(i): resolved(b0[i], g0, st["active_tmpl"]) for i in BODIES}
        part, final = write_file(out_dir, f"rt3_families_journal_{target}", journal)
    part.replace(final)        # the journal gets its final name only once the transaction has committed
    n = len(journal["groups_created"]) + len(journal["groups_updated"]) + len(journal["groups_deleted"]) + moved \
        + len(journal["overrides"])
    print(f"TEMPLATE GUARD: every active body keeps its resolved template (checked in the database before the commit)")
    print(f"APPLIED {n} change(s). Journal: {final}")
    print(f"Undo: python rt3_families.py --target {target} --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, target: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "rt3_families":
        raise SystemExit(f"REFUSED: {jpath} is not an RT3 families journal")
    if j.get("database") != db or j.get("target") != target:
        raise SystemExit(f"REFUSED: the journal was written on {j.get('database')!r} (--target {j.get('target')}); this is {db!r}")
    print(f"database {db} (--target {target}); revert RT3 families from {jpath.name}; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        g, b = groups(cx, lock=True), bodies(cx, lock=True)
        tm = templates(cx)
        active_tmpl = {i for i, a in tm.values() if a}
        created = {c["id"]: c for c in j["groups_created"]}
        # where everything is now: all at the journal's after-state (to revert), or all back (done)
        state = []
        for w in j["bodies"]:
            cur = (b.get(w["id"]) or {}).get("group_id", "missing")
            state.append("after" if cur == w["group_after"] else "before" if cur == w["group_before"] else f"body {w['id']}={cur!r}")
        for w in j["overrides"]:
            cur = (b.get(w["id"]) or {}).get("override_id", "missing")
            state.append("after" if cur == w["after"] else "before" if cur == w["before"] else f"override {w['id']}={cur!r}")
        for w in j["groups_updated"]:
            gr = g.get(w["before"]["id"])
            now = (gr["name"], gr["colour"], gr["sort_order"]) if gr else None
            a, bf = w["after"], w["before"]
            state.append("after" if now == (a["name"], a["colour"], a["sort_order"])
                         else "before" if now == (bf["name"], bf["colour"], bf["sort_order"]) else f"group {bf['id']}={now!r}")
        for c in j["groups_created"]:
            gr = g.get(c["id"])
            state.append("before" if gr is None else "after" if (gr["name"], gr["colour"], gr["sort_order"]) ==
                         (c["name"], c["colour"], c["sort_order"]) else f"group {c['id']}={gr['name']!r}")
        for d in j["groups_deleted"]:
            state.append("after" if d["id"] not in g else "before" if g[d["id"]]["name"] == d["name"] else f"group {d['id']}")
        odd = [s_ for s_ in state if s_ not in ("after", "before")]
        if odd:
            raise Refused("rows moved since the apply: " + "; ".join(odd))
        if set(state) == {"before"}:
            print("  done  every journaled row already holds its before-state")
            print("nothing to revert.")
            return 0
        if "before" in state:
            raise Refused("the families are half there: some rows are at the journal's after-state and some are not")
        for c in created.values():          # no body outside the journal may sit in a group the revert removes
            extra = [i for i, b_ in b.items() if b_["group_id"] == c["id"] and i not in {w["id"] for w in j["bodies"]}]
            if extra:
                raise Refused(f"group {c['id']} {c['name']} now also holds bodies {extra}: move them first")
        for d in j["groups_deleted"]:
            cx.execute(f"""insert into {S}.trailer_groups (id, name, description, report_template_id, colour, sort_order,
                           created_at) values (%s, %s, %s, %s, %s, %s, %s)""",
                       (d["id"], d["name"], d["description"], d["report_template_id"], d["colour"], d["sort_order"],
                        d["created_at"]))
            print(f"  RESTORE group {d['id']} {d['name']}")
        for w in j["bodies"]:
            cx.execute(f"update {S}.trailer_types set group_id = %s where id = %s and group_id = %s",
                       (w["group_before"], w["id"], w["group_after"]))
        for w in j["overrides"]:
            cx.execute(f"update {S}.trailer_types set override_report_template_id = %s where id = %s "
                       f"and override_report_template_id = %s", (w["before"], w["id"], w["after"]))
            print(f"  REVERT override body {w['id']} {w['name']}")
        print(f"  MOVED BACK {len(j['bodies'])} bodies")
        for w in j["groups_updated"]:
            bf = w["before"]
            cx.execute(f"update {S}.trailer_groups set name = %s, colour = %s, sort_order = %s where id = %s",
                       (bf["name"], bf["colour"], bf["sort_order"], bf["id"]))
            print(f"  REVERT group {bf['id']} -> {bf['name']!r}")
        for c in created.values():
            cx.execute(f"delete from {S}.trailer_groups where id = %s", (c["id"],))
            print(f"  REMOVE group {c['id']} {c['name']}")
        g1, b1 = groups(cx), bodies(cx)
        before = j.get("resolved_before") or {}
        bad = [f"body {i}" for i, t in before.items() if int(i) in b1 and resolved(b1[int(i)], g1, active_tmpl) != t]
        if bad:
            raise Refused("after the revert these bodies would not print their pre-apply template: " + ", ".join(bad))
        part, final = write_file(out_dir, f"rt3_families_revert_{target}",
                                 {"tool": "rt3_families", "reverted_journal": jpath.name,
                                  "reverted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    part.replace(final)
    print(f"REVERTED: every journaled row is back; every body prints its pre-apply template. Record: {final}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    gx = ap.add_mutually_exclusive_group()
    gx.add_argument("--apply", action="store_true")
    gx.add_argument("--revert", metavar="JOURNAL")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if (a.apply or a.revert) and not a.out_dir:
        ap.error("--apply / --revert need --out-dir")
    cx, db = connect(a.target, read_only=not (a.apply or a.revert))
    try:
        if a.apply:
            return apply(cx, db, a.target, Path(a.out_dir))
        if a.revert:
            return revert(cx, db, a.target, Path(a.revert), Path(a.out_dir))
        return dry_run(cx, db, a.target)
    except Refused as e:
        print(f"  REFUSED: {e}. The transaction rolled back; nothing written.")
        return 2
    finally:
        cx.close()


if __name__ == "__main__":
    sys.exit(main())
