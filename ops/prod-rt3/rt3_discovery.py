"""RT3 §3.0 — body families: prod's groups, templates, every body, its resolved quote template, and the proposed
family. READ ONLY (one read-only session, psycopg only — runs over any code).

    python rt3_discovery.py <DATABASE_URL> <out-dir>

Writes discovery.json + discovery.txt. Selects body / group / template identity and binding columns only — never a
customer, contact, user or person column (trailer_groups / report_templates / trailer_types carry none).

The resolved template mirrors app/services/__init__.py resolve_report_template exactly:
    the body's override (if set and active)  ->  its group's template (if set and active)  ->  none (the default document)
The PROPOSED family is a name keyword (RT3_DISPATCH: EXPLOSIVE, CHILLER, FREEZER, MEAT, ICE CREAM, OTHER — RHINORANGE,
dry freight, bakery, taut liner and the rest are OTHER) for Michael to confirm. For each body the script prices the
proposal against the template guard: under the proposal (families = trailer_groups; MEAT = the existing MEATHANGER
group, EXPLOSIVE and FREEZER keep theirs, CHILLER / ICE CREAM / OTHER are new groups with no template), does the
resolved template stay the same? Where it would not, it names the override that keeps it.
"""
import json
import re
import sys
from pathlib import Path

import psycopg

RULES = [  # first match wins; RHINORANGE before FREEZER (its own description says Freezer)
    (re.compile(r"ORANGE", re.I), "OTHER"),
    (re.compile(r"EXPLOSIVE", re.I), "EXPLOSIVE"),
    (re.compile(r"CHILL", re.I), "CHILLER"),
    (re.compile(r"FREEZ", re.I), "FREEZER"),
    (re.compile(r"MEAT", re.I), "MEAT"),
    (re.compile(r"ICE ?CREAM", re.I), "ICE CREAM"),
]
# the family -> the existing group that already IS that family on prod (kept, with its template); others are new
EXISTING = {"EXPLOSIVE": "EXPLOSIVE", "FREEZER": "FREEZER", "MEAT": "MEATHANGER"}


def family_of(name: str) -> str:
    for rx, fam in RULES:
        if rx.search(name or ""):
            return fam
    return "OTHER"


def main(url: str, out_dir: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    lines = []
    say = lambda s="": lines.append(s)   # noqa: E731
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("select current_database(), current_setting('default_transaction_read_only')")
        say(f"database / read only: {cur.fetchone()}")
        cur.execute("select id, name, slug, is_active from report_templates order by id")
        tmpl = {r[0]: {"id": r[0], "name": r[1], "slug": r[2], "is_active": r[3]} for r in cur.fetchall()}
        cur.execute("select id, name, description, report_template_id from trailer_groups order by id")
        groups = {r[0]: {"id": r[0], "name": r[1], "description": r[2], "report_template_id": r[3]} for r in cur.fetchall()}
        cur.execute("""select id, name, is_active, group_id, override_report_template_id, configurator_v2
                       from trailer_types order by is_active desc, name""")
        bodies = [{"id": r[0], "name": r[1], "is_active": r[2], "group_id": r[3], "override_id": r[4], "v2": r[5]}
                  for r in cur.fetchall()]
        cur.execute("select trailer_name, group_id, override_report_template_id from orphaned_template_assignments order by trailer_name")
        orphans = [{"trailer_name": r[0], "group_id": r[1], "override_id": r[2]} for r in cur.fetchall()]
        cur.execute("""select trailer_type_id, count(*) from calculations where deleted_at is null group by 1""")
        costings = dict(cur.fetchall())

    def resolve(override_id, group_template_id):
        if override_id and tmpl.get(override_id, {}).get("is_active"):
            return override_id
        if group_template_id and tmpl.get(group_template_id, {}).get("is_active"):
            return group_template_id
        return None

    tname = lambda i: "(none: the default document)" if i is None else f"{tmpl[i]['slug']} #{i}"   # noqa: E731
    by_name = {g["name"]: g for g in groups.values()}
    say("\n== report templates")
    for t in tmpl.values():
        say(f"   #{t['id']:<3} {t['slug']:<22} {t['name']:<32} active={t['is_active']}")
    say("\n== trailer groups (bodies per group, active / all)")
    for g in groups.values():
        n_all = sum(1 for b in bodies if b["group_id"] == g["id"])
        n_act = sum(1 for b in bodies if b["group_id"] == g["id"] and b["is_active"])
        say(f"   #{g['id']:<3} {g['name']:<14} template {tname(g['report_template_id']):<28} bodies {n_act} / {n_all}")
    say(f"   (no group)      bodies {sum(1 for b in bodies if not b['group_id'] and b['is_active'])} / {sum(1 for b in bodies if not b['group_id'])}")

    rows, mismatch = [], []
    for b in bodies:
        g = groups.get(b["group_id"])
        before = resolve(b["override_id"], g["report_template_id"] if g else None)
        fam = family_of(b["name"])
        target = by_name.get(EXISTING.get(fam, ""))           # the existing group that becomes the family, if any
        after_group_tmpl = target["report_template_id"] if target else None   # new families carry no template
        after = resolve(b["override_id"], after_group_tmpl)
        keep = None
        if after != before:
            keep = before                                       # the override that keeps the resolved template
            mismatch.append(b["id"])
        rows.append(dict(b, group=g["name"] if g else None, resolved_before=before, family=fam,
                         family_group=(target["name"] if target else f"{fam} (new)"), resolved_after=after,
                         override_to_keep=keep, saved_costings=costings.get(b["id"], 0)))
    say(f"\n== every body ({len(bodies)}: {sum(1 for b in bodies if b['is_active'])} active) — group today, resolved "
        "template today, PROPOSED family, resolved template under the proposal")
    say(f"   {'id':>3} {'body':<34} {'act':<4} {'group today':<12} {'template today':<28} {'family':<10} {'under the proposal':<28} costings")
    for r in rows:
        flag = "" if r["override_to_keep"] is None else f"  !! keep with override {tname(r['override_to_keep'])}"
        say(f"   {r['id']:>3} {r['name'][:34]:<34} {'Y' if r['is_active'] else 'n':<4} {str(r['group'] or '-'):<12} "
            f"{tname(r['resolved_before']):<28} {r['family']:<10} {tname(r['resolved_after']):<28} {r['saved_costings']:>5}{flag}")
    say(f"\n== the template guard under the proposal: {len(rows) - len(mismatch)} of {len(rows)} bodies keep their resolved "
        f"template as is; {len(mismatch)} need an override to keep it: {mismatch or 'none'}")
    say(f"\n== orphaned template assignments (by body name): {len(orphans)}")
    for o in orphans:
        say(f"   {o['trailer_name']}: group {o['group_id']}, override {o['override_id']}")
    fams = {}
    for r in rows:
        fams.setdefault(r["family"], []).append(r)
    say("\n== the proposed families")
    for f in ("EXPLOSIVE", "CHILLER", "FREEZER", "MEAT", "ICE CREAM", "OTHER"):
        rs = fams.get(f, [])
        say(f"   {f:<10} {sum(1 for r in rs if r['is_active'])} active / {len(rs)}: " + ", ".join(
            f"{r['name']}{'' if r['is_active'] else ' (inactive)'}" for r in rs))
    (out / "discovery.json").write_text(json.dumps({"templates": list(tmpl.values()), "groups": list(groups.values()),
                                                    "bodies": rows, "orphans": orphans}, indent=1, default=str), encoding="utf-8")
    (out / "discovery.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
