"""RT5 (RT5_RULING_1 Q6) — RT3's six body families on Michael's DEV database, BY NAME (prod's step is by prod id and
refuses dev). Data only; needs alembic 0051+ (trailer_groups.colour / sort_order). psycopg only.

    python dev_families.py                                  dry-run (READ ONLY): every group and body, before -> after,
                                                            each active body's quote template before -> after, and
                                                            the plan's sha256
    python dev_families.py --apply --expect-plan SHA --out-dir DIR     apply exactly the reviewed plan, journaled
    python dev_families.py --revert JOURNAL --out-dir DIR              put every journaled row back

DATABASE_URL comes from the environment, else backend/.env beside this repo. It REFUSES any database but dev's `icb`
(never icb_platform, never icb_prodmirror).

The families (RT3, Michael 2 Oct; prod's colours and order):
    1 EXPLOSIVE #E03131 · 2 CHILLER #168ED9 · 3 FREEZER #4263EB · 4 MEAT #D66A0B · 5 ICE CREAM #D63384 · 6 OTHER #7D858C
A family's group is found by name (case / spaces ignored); MEATHANGER is renamed MEAT when there is no MEAT; a missing
family is created (no quote template). RHINORANGE TRAILER goes to OTHER and keeps its quote through its own override (as
on prod); the RHINORANGE group is deleted once empty. Group quote templates are never changed.

Bodies: each mapped by NAME from prod's RT3 plan. Three dev ice-cream bodies still carry the names prod renamed (same
ids on both): an explicit, visible alias maps them to ICE CREAM. Every other name prod's plan does not know goes to
OTHER (the Manni copies 103, 104 and 3 included). The dry-run lists every body.

The prod template guard does not apply on dev: each active body's resolved quote template is REPORTED before -> after,
not asserted. Dev's drafts are never touched. The apply refuses unless the plan it computes is exactly the reviewed one
(--expect-plan): Michael edits families on dev by hand, and a plan that moved since the dry-run is not applied.
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

S = "icb_costings"
TARGET_DB = "icb"                                   # dev only
NEVER = {"icb_platform", "icb_prodmirror"}
NAME_PREFIX = ""                                    # TESTS ONLY: scope every read and name to marker rows
FAMILIES = [("EXPLOSIVE", "#E03131", 1), ("CHILLER", "#168ED9", 2), ("FREEZER", "#4263EB", 3),
            ("MEAT", "#D66A0B", 4), ("ICE CREAM", "#D63384", 5), ("OTHER", "#7D858C", 6)]
RENAME_FROM = {"MEAT": "MEATHANGER"}                 # an existing group renamed to the family (RT3_RULING_1 Q3)
DELETE_WHEN_EMPTY = {"RHINORANGE": "RHINORANGE TRAILER"}   # group -> its body, moved to OTHER with an override
FALLBACK = "OTHER"
# prod's RT3 plan (ops/prod-rt3/rt3_families.py BODIES), by NAME -> family
BODIES = {
    "CHILLER 2.3 METER": "CHILLER", "CHILLER LARGE": "CHILLER", "CHILLER MEDIUM": "CHILLER",
    "EXPLOSIVE 2.7 TO 4.8": "EXPLOSIVE", "EXPLOSIVE 4.9 AND UP": "EXPLOSIVE", "EXPLOSIVE UP TO 2.7": "EXPLOSIVE",
    "FREEZER 2.3 METER": "FREEZER", "FREEZER LARGE": "FREEZER", "FREEZER MEDIUM": "FREEZER",
    "ICECREAM BODY LARGE": "ICE CREAM", "ICECREAM BODY MEDIUM": "ICE CREAM", "ICECREAM BODY SMALL": "ICE CREAM",
    "Manni RIGIDS CB": "OTHER", "MEAT HANGER LARGE": "MEAT", "MEAT HANGER SMALL-MEDIUM": "MEAT",
    "RHINORANGE TRAILER": "OTHER", "ADVANTICA BODY": "OTHER", "ADV VACUUM PANELS": "OTHER",
    "CHESTER SPEC MEAT BODY": "MEAT", "DRY FREIGHT TRAILER": "OTHER",
    "EXPLOSIVE 2.7 TO 4.8 OLD [deleted-23]": "EXPLOSIVE", "EXPLOSIVE UP TO 2.7 [deleted-22]": "EXPLOSIVE",
    "EXPLOSIVE UP TO 2.7 [deleted-28]": "EXPLOSIVE", "EXPLOSIVE UP TO 2.7 [deleted-29]": "EXPLOSIVE",
    "EXPLOSIVE UP TO 2.7 [deleted-30]": "EXPLOSIVE", "EXPLOSIVE UP TO 2.7 [deleted-31]": "EXPLOSIVE",
    "EXPLOSIVE UP TO 2.7 [deleted-32]": "EXPLOSIVE", "EXPLOSIVE UP TO 2.7 [deleted-33]": "EXPLOSIVE",
    "GRP TRAILERS": "OTHER", "MANNI BAKKI RIGIDS": "OTHER", "MANNI DF": "OTHER", "MANNI RIGIDS CB": "OTHER",
    "MANNI RIGIDS FB": "OTHER", "MANNI TRAILERS": "OTHER", "RIGID DRY FREIGHT": "OTHER",
    "RIGID DRY FREIGHT [deleted-38]": "OTHER", "RIGID DRY FREIGHT [deleted-8]": "OTHER",
    "SMALL MEAT BODY UP TO 5,2 [deleted-11]": "MEAT", "SMALL MEAT BODY UP TO 5,2 [deleted-35]": "MEAT",
    "TAUT LINER RIGID": "OTHER", "TESTING EVERYTHING": "OTHER",
}
# dev name -> the prod name of the SAME body (prod renamed these; ids 18 / 17 / 16 on both)
ALIASES = {"ICECREAM 4.9 UP": "ICECREAM BODY LARGE", "ICECREAM UP TO 4.8": "ICECREAM BODY MEDIUM",
           "ICECREAM UP TO 3,2": "ICECREAM BODY SMALL"}


class Refused(Exception):
    """A guard refused: nothing is written."""


def norm(s) -> str:
    return " ".join(str(s or "").upper().split())


def tool_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        env = Path(__file__).resolve().parents[2] / "backend" / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
    if not url:
        raise SystemExit("REFUSED: no DATABASE_URL (environment or backend/.env)")
    return url.replace("postgresql+psycopg://", "postgresql://")


def connect(read_only: bool):
    kw = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    cx = psycopg.connect(_url(), autocommit=True, **kw)
    db = cx.execute("select current_database()").fetchone()[0]
    if db in NEVER or db != TARGET_DB:
        cx.close()
        raise SystemExit(f"REFUSED: this is {db!r}; the dev families step runs only on dev's {TARGET_DB!r}")
    have = {r[0] for r in cx.execute("select column_name from information_schema.columns where table_schema = %s "
                                     "and table_name = 'trailer_groups'", (S,))}
    if not {"colour", "sort_order"} <= have:
        cx.close()
        raise SystemExit("REFUSED: trailer_groups has no colour / sort_order — upgrade dev to alembic 0051 first")
    return cx, db


def read(cx, lock: bool = False) -> tuple[list[dict], list[dict], dict]:
    fu = " for update" if lock else ""
    like = NAME_PREFIX.replace("%", r"\%") + "%"
    groups = [dict(zip(("id", "name", "colour", "sort_order", "report_template_id", "description"), r)) for r in
              cx.execute(f"select id, name, colour, sort_order, report_template_id, description from {S}.trailer_groups "
                         f"where name like %s order by id{fu}", (like,))]
    bodies = [dict(zip(("id", "name", "is_active", "group_id", "override_report_template_id"), r)) for r in
              cx.execute(f"select id, name, is_active, group_id, override_report_template_id from {S}.trailer_types "
                         f"where name like %s order by name{fu}", (like,))]
    templates = {r[0]: (r[1], r[2]) for r in cx.execute(f"select id, slug, is_active from {S}.report_templates")}
    return groups, bodies, templates


def _p(name: str) -> str:
    return NAME_PREFIX + name


def make_plan(groups: list[dict], bodies: list[dict]) -> dict:
    """Pure: the families' groups (keep / rename / create / colour + order), each body's family, the RHINORANGE
    override, and the groups deleted once empty. Group ids for groups still to create are 'new:<FAMILY>'."""
    by_name = {norm(g["name"]): g for g in groups}
    fam_gid, group_ops = {}, []
    for fam, colour, order in FAMILIES:
        g = by_name.get(norm(_p(fam)))
        rename_from = RENAME_FROM.get(fam)
        if g is None and rename_from and norm(_p(rename_from)) in by_name:
            g = by_name[norm(_p(rename_from))]
        if g is None:
            fam_gid[fam] = f"new:{fam}"
            group_ops.append({"op": "create", "family": fam, "name": _p(fam), "colour": colour, "sort_order": order})
            continue
        fam_gid[fam] = g["id"]
        after = {"name": _p(fam), "colour": colour, "sort_order": order}
        before = {k: g[k] for k in after}
        if before != after:
            group_ops.append({"op": "update", "family": fam, "id": g["id"], "before": before, "after": after})
    body_ops, overrides = [], []
    for b in bodies:
        name = b["name"][len(NAME_PREFIX):] if NAME_PREFIX and b["name"].startswith(NAME_PREFIX) else b["name"]
        via = None
        if name in BODIES:
            fam = BODIES[name]
        elif name in ALIASES:
            fam, via = BODIES[ALIASES[name]], ALIASES[name]
        else:
            fam = FALLBACK
        gid = fam_gid[fam]
        rec = {"id": b["id"], "name": b["name"], "family": fam, "via": via, "known": name in BODIES or via is not None,
               "group_before": b["group_id"], "group_after": gid}
        if b["group_id"] != gid:
            body_ops.append(rec)
        for gname, bname in DELETE_WHEN_EMPTY.items():
            src = by_name.get(norm(_p(gname)))
            if src and name == bname and b["group_id"] == src["id"] and not b["override_report_template_id"] \
                    and src["report_template_id"]:
                overrides.append({"id": b["id"], "name": b["name"], "before": None, "after": src["report_template_id"]})
        rec["listed"] = True
    moving_out = {o["id"] for o in body_ops}
    deletes = []
    for gname in DELETE_WHEN_EMPTY:
        src = by_name.get(norm(_p(gname)))
        if src and src["id"] not in fam_gid.values():
            left = [b for b in bodies if b["group_id"] == src["id"] and b["id"] not in moving_out]
            if not left:
                deletes.append({k: src[k] for k in ("id", "name", "colour", "sort_order", "report_template_id", "description")})
    return {"groups": group_ops, "bodies": body_ops, "overrides": overrides, "deletes": deletes,
            "all_bodies": [{"id": b["id"], "name": b["name"]} for b in bodies]}


def plan_sha(plan: dict) -> str:
    core = {k: plan[k] for k in ("groups", "bodies", "overrides", "deletes")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def resolved(body: dict, groups_by_id: dict, templates: dict, plan: dict | None = None) -> str:
    """The body's quote template, as app/services resolve_report_template: its own override (active), else its
    group's (active), else none. With a plan: AFTER it."""
    ov, gid = body["override_report_template_id"], body["group_id"]
    if plan:
        ov = next((o["after"] for o in plan["overrides"] if o["id"] == body["id"]), ov)
        gid = next((o["group_after"] for o in plan["bodies"] if o["id"] == body["id"]), gid)
    if ov and templates.get(ov, (None, False))[1]:
        return templates[ov][0]
    g = groups_by_id.get(gid)
    t = g and g["report_template_id"]
    return templates[t][0] if t and templates.get(t, (None, False))[1] else "(default document)"


def describe(cx) -> tuple[dict, list[str]]:
    groups, bodies, templates = read(cx)
    plan = make_plan(groups, bodies)
    gby = {g["id"]: g for g in groups}
    lines = [f"plan sha256 {plan_sha(plan)} · tool sha256 {tool_sha()[:16]}…", "", "== groups (families)"]
    fam_of = {}
    for fam, colour, order in FAMILIES:
        op = next((o for o in plan["groups"] if o["family"] == fam), None)
        g = next((g for g in groups if norm(g["name"]) == norm(_p(fam))
                  or norm(g["name"]) == norm(_p(RENAME_FROM.get(fam, "\0")))), None)
        if op is None:
            lines.append(f"   KEEP    #{g['id']} {g['name']} {g['colour']} order {g['sort_order']}")
        elif op["op"] == "create":
            lines.append(f"   CREATE  {op['name']} {colour} order {order} (no quote template)")
        else:
            lines.append(f"   UPDATE  #{op['id']} " + "; ".join(f"{k} {op['before'][k]!r} -> {op['after'][k]!r}"
                                                         for k in op["after"] if op["before"][k] != op["after"][k]))
    for d in plan["deletes"]:
        lines.append(f"   DELETE  #{d['id']} {d['name']} (empty once its body moves; its quote template rides on the body)")
    others = [g for g in groups if g["id"] not in {o.get("id") for o in plan["groups"]} | {d["id"] for d in plan["deletes"]}
              and norm(g["name"]) not in {norm(_p(f)) for f, _, _ in FAMILIES}
              and norm(g["name"]) not in {norm(_p(v)) for v in RENAME_FROM.values()}]
    for g in others:
        lines.append(f"   LEAVE   #{g['id']} {g['name']} (not one of the six families; untouched)")
    lines += ["", "== every body -> its family (MOVE = the group changes)"]
    moving = {o["id"]: o for o in plan["bodies"]}
    for b in bodies:
        o = moving.get(b["id"])
        name = b["name"][len(NAME_PREFIX):] if NAME_PREFIX else b["name"]
        fam = (o or {}).get("family") or (BODIES.get(name) or (BODIES[ALIASES[name]] if name in ALIASES else FALLBACK))
        fam_of[b["id"]] = fam
        tag = "MOVE" if o else "same"
        why = f" (alias of prod's {ALIASES[name]!r})" if name in ALIASES else ("" if name in BODIES else " (not in prod's plan -> OTHER)")
        before = gby.get(b["group_id"], {}).get("name", "none")
        lines.append(f"   {tag:<4}  #{b['id']:<4} {b['name']:<40} {'' if b['is_active'] else '(inactive) '}{before} -> {fam}{why}")
    for o in plan["overrides"]:
        lines.append(f"   OVERRIDE #{o['id']} {o['name']}: its own quote template -> {templates.get(o['after'], ('?',))[0]} "
                     f"(it keeps its quote in OTHER)")
    lines += ["", "== each ACTIVE body's quote template, before -> after (REPORTED: the prod guard does not apply on dev)"]
    changed = 0
    for b in bodies:
        if not b["is_active"]:
            continue
        t0, t1 = resolved(b, gby, templates), resolved(b, gby, templates, plan)
        changed += t0 != t1
        lines.append(f"   {'CHANGES' if t0 != t1 else 'same':<7} #{b['id']:<4} {b['name']:<40} {t0} -> {t1}")
    n = len(plan["groups"]) + len(plan["bodies"]) + len(plan["overrides"]) + len(plan["deletes"])
    lines += ["", f"{n} change(s): {len(plan['groups'])} group(s), {len(plan['bodies'])} body move(s), "
                  f"{len(plan['overrides'])} override(s), {len(plan['deletes'])} delete(s); {changed} active body template(s) change."]
    return plan, lines


def write_file(out_dir: Path, stem: str, doc: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    final.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return final


def apply(cx, db: str, expect: str, out_dir: Path) -> int:
    try:
        with cx.transaction():
            groups, bodies, templates = read(cx, lock=True)
            plan = make_plan(groups, bodies)
            if plan_sha(plan) != expect:
                raise Refused(f"the plan is {plan_sha(plan)[:16]}…, the reviewed dry-run was {expect[:16]}… — dev moved "
                              "since the dry-run (run the dry-run again and review it)")
            created = {}
            for op in plan["groups"]:
                if op["op"] == "create":
                    gid = cx.execute(f"insert into {S}.trailer_groups (name, description, colour, sort_order, created_at) "
                                     "values (%s, %s, %s, %s, now()) returning id",
                                     (op["name"], f"{op['family']} bodies (RT3 body family).", op["colour"],
                                      op["sort_order"])).fetchone()[0]
                    created[op["family"]] = gid
                    op["id"] = gid
                else:
                    a = op["after"]
                    cx.execute(f"update {S}.trailer_groups set name = %s, colour = %s, sort_order = %s where id = %s",
                               (a["name"], a["colour"], a["sort_order"], op["id"]))
            for o in plan["bodies"]:
                if isinstance(o["group_after"], str):
                    o["group_after"] = created[o["group_after"].split(":", 1)[1]]
                cx.execute(f"update {S}.trailer_types set group_id = %s where id = %s", (o["group_after"], o["id"]))
            for o in plan["overrides"]:
                cx.execute(f"update {S}.trailer_types set override_report_template_id = %s where id = %s", (o["after"], o["id"]))
            for d in plan["deletes"]:
                left = cx.execute(f"select count(*) from {S}.trailer_types where group_id = %s", (d["id"],)).fetchone()[0]
                if left:
                    raise Refused(f"group #{d['id']} {d['name']} still holds {left} body(ies)")
                cx.execute(f"delete from {S}.trailer_groups where id = %s", (d["id"],))
            journal = {"tool": "dev_families", "database": db, "plan_sha256": expect, "tool_sha256": tool_sha(),
                       "applied_at": datetime.now(timezone.utc).isoformat(), "created": created, **plan}
            final = write_file(out_dir, "dev_families_journal", journal)
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    print(f"APPLIED: {len(plan['groups'])} group change(s) ({len(created)} created), {len(plan['bodies'])} body move(s), "
          f"{len(plan['overrides'])} override(s), {len(plan['deletes'])} delete(s)")
    print(f"journal {final}  sha256 {hashlib.sha256(final.read_bytes()).hexdigest()}")
    print(f"Undo: python dev_families.py --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "dev_families" or j.get("database") != db:
        raise SystemExit(f"REFUSED: {jpath.name} is not a dev_families journal of {db!r}")
    try:
        with cx.transaction():
            for d in j["deletes"]:
                cx.execute(f"insert into {S}.trailer_groups (id, name, colour, sort_order, report_template_id, description, "
                           "created_at) values (%s, %s, %s, %s, %s, %s, now())",
                           (d["id"], d["name"], d["colour"], d["sort_order"], d["report_template_id"], d["description"]))
            for o in j["overrides"]:
                cur = cx.execute(f"select override_report_template_id from {S}.trailer_types where id = %s for update",
                                 (o["id"],)).fetchone()
                if not cur or cur[0] != o["after"]:
                    raise Refused(f"body #{o['id']}'s override moved since")
                cx.execute(f"update {S}.trailer_types set override_report_template_id = %s where id = %s", (o["before"], o["id"]))
            for o in j["bodies"]:
                cur = cx.execute(f"select group_id from {S}.trailer_types where id = %s for update", (o["id"],)).fetchone()
                if not cur or cur[0] != o["group_after"]:
                    raise Refused(f"body #{o['id']} {o['name']} moved since (group {cur and cur[0]}, journal {o['group_after']})")
                cx.execute(f"update {S}.trailer_types set group_id = %s where id = %s", (o["group_before"], o["id"]))
            for op in j["groups"]:
                if op["op"] == "update":
                    cur = cx.execute(f"select name, colour, sort_order from {S}.trailer_groups where id = %s for update",
                                     (op["id"],)).fetchone()
                    if not cur or list(cur) != [op["after"][k] for k in ("name", "colour", "sort_order")]:
                        raise Refused(f"group #{op['id']} moved since")
                    b = op["before"]
                    cx.execute(f"update {S}.trailer_groups set name = %s, colour = %s, sort_order = %s where id = %s",
                               (b["name"], b["colour"], b["sort_order"], op["id"]))
                else:
                    left = cx.execute(f"select count(*) from {S}.trailer_types where group_id = %s", (op["id"],)).fetchone()[0]
                    if left:
                        raise Refused(f"created group #{op['id']} {op['name']} holds {left} body(ies) the journal did not move")
                    cx.execute(f"delete from {S}.trailer_groups where id = %s", (op["id"],))
            final = write_file(out_dir, "dev_families_revert", {"tool": "dev_families", "reverted": jpath.name,
                                                                 "database": db, "at": datetime.now(timezone.utc).isoformat()})
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    print(f"REVERTED {jpath.name}; record {final}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    gx = ap.add_mutually_exclusive_group()
    gx.add_argument("--apply", action="store_true")
    gx.add_argument("--revert", metavar="JOURNAL")
    ap.add_argument("--expect-plan", default=None, help="the plan sha256 the reviewed dry-run printed")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if (a.apply or a.revert) and not a.out_dir:
        ap.error("--apply / --revert need --out-dir")
    if a.apply and not a.expect_plan:
        ap.error("--apply needs --expect-plan (the sha256 the dry-run printed)")
    cx, db = connect(read_only=not (a.apply or a.revert))
    try:
        if a.apply:
            return apply(cx, db, a.expect_plan, Path(a.out_dir))
        if a.revert:
            return revert(cx, db, Path(a.revert), Path(a.out_dir))
        print(f"database {db}; RT5 dev families (by name); READ ONLY")
        _, lines = describe(cx)
        print("\n".join(lines))
        return 0
    finally:
        cx.close()


if __name__ == "__main__":
    sys.exit(main())
