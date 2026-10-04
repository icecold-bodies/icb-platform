"""RT4 §3.0 — the five Manni bodies on the standard section names: prod's facts. READ ONLY (one read-only
session, psycopg only — runs over any code).

    python rt4_discovery.py <DATABASE_URL> <out-dir>

Writes discovery.json + discovery.txt:

  1. every body whose name says MANNI (active, inactive and soft-deleted): v2 or not, family, default size and foam;
  2. per Manni: every section its lines use (by FK id AND by the legacy string), with line counts; id/string drift;
  3. per Manni: its body-option masters by name (group / subgroup / default / thickness) — the door and insulation
     masters the pricing proof toggles;
  4. per Manni: its Trailer Designer draft — every category node's section key (sourceCategoryKey), its label and
     its folder path — plus draft snapshots;
  5. per Manni: saved costings (all / live);
  6. the E3 sweep: EVERY section name the Mannis use against the set the 14 standard bodies use, each non-standard
     one with a proposed standard target (token match, else a fuzzy candidate, else none), and what a move into that
     target would change: multiplier, Optional, archived, the owning master (v2: resolved by name on the body), the
     DRD/SRD name prefix (non-v2) — and each line in it with its own per-line gate (body_option_linked);
  7. every body that uses a non-standard section (so the delete offer is known), and where those sections' owning
     masters live;
  8. deleted id 41: its row, and every table that still holds rows for it (FK sweep + any trailer_type_id column).

Selects pricing / configuration / identity columns only — never a customer, contact, user or person column
(configurator_drafts.updated_by, *_snapshots.created_by, calculations' people columns are never selected;
calculations are COUNTED only).
"""
import difflib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

STANDARD_14 = [12, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 34, 36, 37]   # the door report's Manifest A bodies
DELETED_ID = 41
DOOR_PREFIXES = ("DRD", "SRD")


def norm_tokens(name: str) -> tuple:
    s = (name or "").upper().replace("+", " & ").replace(" AND ", " & ")
    return tuple(sorted(t for t in re.split(r"\s+", s.strip()) if t))


def main(url: str, out_dir: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    lines: list[str] = []
    say = lambda s="": lines.append(s)   # noqa: E731
    doc: dict = {}
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()

        def rows(sql, args=None):
            cur.execute(sql, args or ())
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute("select current_database(), current_setting('default_transaction_read_only'), current_schema()")
        db, ro, schema = cur.fetchone()
        say(f"database / read only / schema: {db} / {ro} / {schema}")
        if ro != "on":
            raise SystemExit("the session is not read-only")
        doc["session"] = {"database": db, "read_only": ro, "schema": schema}

        # ---- 1. the bodies -------------------------------------------------------------------------------------
        # tests only: RT4_DISCOVERY_TEST_IDS="15,..." treats those bodies as the Mannis (the mirror has no Manni
        # lines); rt4_discovery.sh refuses to run with it set
        test_ids = [int(x) for x in os.environ.get("RT4_DISCOVERY_TEST_IDS", "").split(",") if x.strip()]
        bodies = rows("""select t.id, t.name, t.is_active, t.configurator_v2, t.default_length, t.default_width,
                                t.default_height, t.default_insulation_foam, g.name as family
                           from trailer_types t left join trailer_groups g on g.id = t.group_id
                          where (upper(t.name) like '%%MANNI%%' and %s = 0) or t.id = any(%s) or t.id = %s
                          order by t.id""", (len(test_ids), test_ids, DELETED_ID))
        manni = [b for b in bodies if b["id"] != DELETED_ID and "[deleted-" not in b["name"]]
        manni_ids = [b["id"] for b in manni]
        doc["bodies"] = bodies
        std = rows("select id, name, is_active from trailer_types where id = any(%s) order by id", (STANDARD_14,))
        doc["standard_bodies"] = std
        say(); say("== 1 · bodies named MANNI (and id 41)")
        for b in bodies:
            say(f"   #{b['id']:<3} {b['name']:<34} active={b['is_active']!s:<5} v2={b['configurator_v2']!s:<5} "
                f"family={b['family'] or '-':<10} size={b['default_length']}x{b['default_width']}x{b['default_height']} "
                f"foam={b['default_insulation_foam']}")
        say(f"   standard 14: {len(std)} found, active {sum(1 for s in std if s['is_active'])}: "
            + ", ".join(f"{s['id']} {s['name']}" for s in std))

        sections = {s["id"]: s for s in rows(
            """select s.id, s.name, s.multiplier, s.is_optional, (s.archived_at is not null) as archived, s.sort_order,
                      s.body_option_master_id as owner_id, m.trailer_type_id as owner_body, mt.name as owner_master
                 from bom_sections s left join bill_of_materials m on m.id = s.body_option_master_id
                 left join materials mt on mt.id = m.material_id order by s.id""")}
        by_name = {s["name"]: s for s in sections.values()}
        doc["sections"] = list(sections.values())

        # every BOM line: section by id and by string (no money, no formulas — identity + gating columns)
        all_lines = rows("""select b.id, b.trailer_type_id, b.bom_section_id, b.bom_section, b.is_body_option,
                                   b.body_option_group, b.body_option_subgroup, b.body_option_default,
                                   b.body_option_linked, b.body_option_linked_id, b.variable_value,
                                   (b.bom_conditions is not null and b.bom_conditions <> '' and b.bom_conditions <> '[]')
                                      as has_conditions, m.name as material
                              from bill_of_materials b left join materials m on m.id = b.material_id""")
        linked_names = {r["id"]: r["name"] for r in rows("select id, name from materials where id = any(%s)",
                                                           ([l["body_option_linked_id"] for l in all_lines
                                                             if l["body_option_linked_id"]],))}

        def sec_name_of(l):        # what the line's FK says, else its string
            s = sections.get(l["bom_section_id"])
            return s["name"] if s else (l["bom_section"] or "")

        # ---- 2/3. per Manni: sections, drift, masters -------------------------------------------------------------
        doc["manni"] = {}
        say(); say("== 2 · per Manni: sections (line counts; id = FK section, str = legacy string)")
        for b in bodies:
            ls = [l for l in all_lines if l["trailer_type_id"] == b["id"]]
            per = Counter()
            drift = []
            for l in ls:
                sid, sstr = l["bom_section_id"], l["bom_section"]
                sname = sections[sid]["name"] if sid in sections else None
                per[(sid, sname, sstr)] += 1
                if sname != sstr:
                    drift.append({"bom_id": l["id"], "id": sid, "id_name": sname, "string": sstr})
            masters = [{"bom_id": l["id"], "material": l["material"], "group": l["body_option_group"],
                        "subgroup": l["body_option_subgroup"], "default": l["body_option_default"],
                        "thickness": l["variable_value"], "section": sec_name_of(l)} for l in ls if l["is_body_option"]]
            doc["manni"][b["id"]] = {"lines": len(ls), "sections": [
                {"section_id": k[0], "id_name": k[1], "string": k[2], "lines": n} for k, n in sorted(per.items(), key=lambda kv: (kv[0][1] or kv[0][2] or ""))],
                "drift": drift, "masters": masters}
            say(f"   #{b['id']} {b['name']} — {len(ls)} lines, {len(per)} section keys, drift {len(drift)}")
            for k, n in sorted(per.items(), key=lambda kv: (kv[0][1] or kv[0][2] or "")):
                flag = "" if k[1] == k[2] else "   ⚠ id/string differ"
                say(f"      {n:>4}  id {k[0]!s:<5} {k[1] or '(no id)':<34} str {k[2] or '(none)'}{flag}")
            say(f"      masters ({len(masters)}):")
            for m in masters:
                say(f"         bom {m['bom_id']:>6} {m['material']:<30} group={m['group'] or '-':<12} sub={m['subgroup'] or '-':<12} "
                    f"default={m['default']!s:<5} thick={m['thickness']}")

        # ---- 4. drafts ----------------------------------------------------------------------------------------------
        say(); say("== 4 · Trailer Designer drafts (category nodes: section key · label · folder path)")
        drafts = {r["trailer_type_id"]: r for r in rows(
            "select trailer_type_id, payload, updated_at from configurator_drafts where trailer_type_id = any(%s)",
            ([b["id"] for b in bodies],))}
        dsnaps = {r["trailer_type_id"]: r["n"] for r in rows(
            "select trailer_type_id, count(*) as n from configurator_draft_snapshots where trailer_type_id = any(%s) group by 1",
            ([b["id"] for b in bodies],))}
        all_draft_keys = defaultdict(set)   # section key -> bodies whose draft names it (every draft on prod)
        for r in rows("select trailer_type_id, payload from configurator_drafts"):
            try:
                p = json.loads(r["payload"] or "{}")
            except (ValueError, TypeError):
                continue
            for n in (p.get("nodes") or {}).values():
                if isinstance(n, dict) and n.get("type") == "category" and n.get("sourceCategoryKey"):
                    all_draft_keys[n["sourceCategoryKey"].strip().upper()].add(r["trailer_type_id"])
        for b in bodies:
            d = drafts.get(b["id"])
            entry = {"has_draft": bool(d), "snapshots": dsnaps.get(b["id"], 0), "categories": [], "parse_error": None}
            if d:
                entry["updated_at"] = str(d["updated_at"])
                try:
                    p = json.loads(d["payload"] or "{}")
                    nodes = p.get("nodes") or {}

                    def path(n, seen=None):
                        out, cur_id, guard = [], n.get("parentId"), 0
                        while cur_id and cur_id in nodes and guard < 50:
                            out.append(f"{nodes[cur_id].get('type')}:{nodes[cur_id].get('label')}")
                            cur_id = nodes[cur_id].get("parentId"); guard += 1
                        return " / ".join(reversed(out))
                    for nid, n in nodes.items():
                        if isinstance(n, dict) and n.get("type") == "category":
                            entry["categories"].append({"node": nid, "key": n.get("sourceCategoryKey"),
                                                        "label": n.get("label"), "path": path(n)})
                    entry["node_types"] = dict(Counter(n.get("type") for n in nodes.values() if isinstance(n, dict)))
                except (ValueError, TypeError) as e:
                    entry["parse_error"] = str(e)
            doc["manni"].setdefault(b["id"], {})["draft"] = entry
            say(f"   #{b['id']} {b['name']}: draft={'yes' if d else 'no'} snapshots={entry['snapshots']}"
                + (f" nodes={entry.get('node_types')}" if d else ""))
            for c in sorted(entry["categories"], key=lambda c: (c["path"], c["key"] or "")):
                say(f"      key {c['key']!s:<34} label {c['label']!s:<30} under {c['path'] or '(root)'}")

        # ---- 5. costings (counted only) --------------------------------------------------------------------------
        say(); say("== 5 · saved costings per body (counts only)")
        calc = {r["trailer_type_id"]: r for r in rows(
            """select trailer_type_id, count(*) as all_, count(*) filter (where deleted_at is null) as live
                 from calculations where trailer_type_id = any(%s) group by 1""", ([b["id"] for b in bodies],))}
        for b in bodies:
            c = calc.get(b["id"], {"all_": 0, "live": 0})
            doc["manni"].setdefault(b["id"], {})["costings"] = {"all": c["all_"], "live": c["live"]}
            say(f"   #{b['id']:<3} {b['name']:<34} costings all={c['all_']} live={c['live']}")

        # ---- 6. E3 sweep: Manni section names vs the 14 standard bodies -------------------------------------------
        say(); say("== 6 · E3 sweep — every section name the five Mannis use vs the 14 standard bodies")
        std_names = Counter()
        for l in all_lines:
            if l["trailer_type_id"] in STANDARD_14:
                std_names[sec_name_of(l)] += 1
        std_set = set(std_names)
        by_tokens = defaultdict(list)
        for n in std_set:
            by_tokens[norm_tokens(n)].append(n)
        manni_names = Counter()
        for l in all_lines:
            if l["trailer_type_id"] in manni_ids:
                manni_names[sec_name_of(l)] += 1
        sweep = []
        for name, n in sorted(manni_names.items()):
            item = {"name": name, "manni_lines": n, "standard": name in std_set}
            if not item["standard"]:
                tok = by_tokens.get(norm_tokens(name))
                if tok and len(tok) == 1:
                    item["proposal"], item["how"] = tok[0], "token match"
                else:
                    # a fuzzy hit is only a CANDIDATE for the CA to verify, never a proposal on its own
                    best = difflib.get_close_matches(name.upper(), [s.upper() for s in std_set], n=2, cutoff=0.75)
                    item["proposal"] = next((s for s in std_set if best and s.upper() == best[0]), None)
                    item["how"] = (f"candidate — verify (fuzzy {difflib.SequenceMatcher(None, name.upper(), best[0]).ratio():.2f})"
                                   if best else "none")
                old, new = by_name.get(name), by_name.get(item.get("proposal") or "")
                if old and new:
                    diffs = {k: (old[k], new[k]) for k in ("multiplier", "is_optional", "archived") if old[k] != new[k]}
                    item["property_diffs"] = {k: list(v) for k, v in diffs.items()}
                    item["old"] = {k: old[k] for k in ("id", "owner_id", "owner_body", "owner_master")}
                    item["new"] = {k: new[k] for k in ("id", "owner_id", "owner_body", "owner_master")}
                    up_old = name.upper()
                    up_new = new["name"].upper()
                    item["prefix_gate"] = {"old": next((p for p in DOOR_PREFIXES if up_old.startswith(p)), None),
                                           "new": next((p for p in DOOR_PREFIXES if up_new.startswith(p)), None)}
                    # per Manni: the lines that would move, with their own gate; a v2 owner-by-name check
                    per_body = {}
                    for b in manni:
                        ls = [l for l in all_lines if l["trailer_type_id"] == b["id"] and sec_name_of(l) == name]
                        if not ls:
                            continue
                        local_master = None
                        if new["owner_master"]:
                            local_master = next((l["id"] for l in all_lines if l["trailer_type_id"] == b["id"]
                                                 and l["is_body_option"] and l["material"] == new["owner_master"]), None)
                        per_body[b["id"]] = {
                            "v2": b["configurator_v2"],
                            "v2_owner_gate_after": (f"master {new['owner_master']!r} -> local bom {local_master}"
                                                    if new["owner_master"] and local_master else
                                                    "none (no same-named master on this body)" if new["owner_master"]
                                                    else "none (target has no owner)"),
                            "lines": [{"bom_id": l["id"], "material": l["material"], "is_master": l["is_body_option"],
                                       "by": "id" if l["bom_section_id"] else "string",
                                       "linked": linked_names.get(l["body_option_linked_id"]) or l["body_option_linked"],
                                       "has_conditions": l["has_conditions"]} for l in ls]}
                    item["per_body"] = per_body
            sweep.append(item)
        doc["sweep"] = sweep
        say(f"   the 14 standard bodies use {len(std_set)} section names; the five Mannis use {len(manni_names)}")
        for it in sweep:
            if it["standard"]:
                say(f"   ok   {it['name']:<34} ({it['manni_lines']} Manni lines) — a standard name")
        for it in sweep:
            if it["standard"]:
                continue
            say(f"   NON  {it['name']:<34} ({it['manni_lines']} Manni lines) -> {it.get('proposal') or '?'}  [{it['how']}]")
            if it.get("property_diffs"):
                say(f"        ⚠ section properties differ: {it['property_diffs']}")
            if it.get("prefix_gate") and it["prefix_gate"]["old"] != it["prefix_gate"]["new"]:
                say(f"        ⚠ non-v2 name-prefix gate: {it['prefix_gate']['old']} -> {it['prefix_gate']['new']}")
            if it.get("new"):
                say(f"        target owner: {it['new']['owner_master'] or 'none'} (master {it['new']['owner_id']}, body {it['new']['owner_body']})"
                    f" · old owner: {it['old']['owner_master'] or 'none'}")
            for bid, pb in (it.get("per_body") or {}).items():
                say(f"        #{bid} v2={pb['v2']} owner gate after: {pb['v2_owner_gate_after']}")
                for l in pb["lines"]:
                    say(f"           bom {l['bom_id']:>6} {l['material'] or '?':<34} by {l['by']:<6} master={l['is_master']!s:<5}"
                        f" linked={l['linked'] or '-'}{' +conditions' if l['has_conditions'] else ''}")

        # ---- 7. who else uses the non-standard sections (the delete offer) -----------------------------------------
        say(); say("== 7 · every body using a non-standard Manni section (by id or by string), and draft keys naming it")
        names_by_id = {b["id"]: b["name"] for b in rows("select id, name from trailer_types")}
        doc["usage"] = {}
        for it in sweep:
            if it["standard"]:
                continue
            nm = it["name"]
            sid = by_name[nm]["id"] if nm in by_name else None
            use = Counter(l["trailer_type_id"] for l in all_lines
                          if (sid is not None and l["bom_section_id"] == sid) or l["bom_section"] == nm)
            keyed = sorted(all_draft_keys.get(nm.strip().upper(), set()))
            doc["usage"][nm] = {"section_id": sid, "bodies": {str(k): v for k, v in use.items()},
                                "draft_bodies": keyed}
            say(f"   {nm} (section {sid}): " + (", ".join(f"#{k} {names_by_id.get(k)} ×{v}" for k, v in sorted(use.items())) or "no lines")
                + (f" · drafts naming it: {', '.join('#%s' % k for k in keyed)}" if keyed else " · no draft names it"))
        # the targets' draft usage too (Part A item 4: does a draft already have a node for the new name?)
        for it in sweep:
            p = it.get("proposal")
            if p:
                keyed = sorted(all_draft_keys.get(p.strip().upper(), set()))
                say(f"   target {p}: drafts naming it: {', '.join('#%s' % k for k in keyed) or 'none'}")

        # ---- 8. deleted id 41 ------------------------------------------------------------------------------------
        say(); say(f"== 8 · deleted id {DELETED_ID}: what is left")
        b41 = next((b for b in bodies if b["id"] == DELETED_ID), None)
        say(f"   row: {b41['name'] if b41 else 'ABSENT'} · active={b41 and b41['is_active']} · v2={b41 and b41['configurator_v2']}")
        refs = rows("""select distinct cl.relname as tbl, a.attname as col
                         from pg_constraint c join pg_class cl on cl.oid = c.conrelid
                         join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
                        where c.contype = 'f' and c.confrelid = 'trailer_types'::regclass
                       union
                       select table_name, column_name from information_schema.columns
                        where table_schema = current_schema() and column_name in ('trailer_type_id', 'trailer_id')
                        order by 1, 2""")
        left = {}
        for r in refs:
            cur.execute(f'select count(*) from "{r["tbl"]}" where "{r["col"]}" = %s', (DELETED_ID,))
            n = cur.fetchone()[0]
            if n:
                left[f"{r['tbl']}.{r['col']}"] = n
        sec41 = [s for s in sections.values() if s["owner_body"] == DELETED_ID]
        orphan = rows("select trailer_name, group_id, override_report_template_id from orphaned_template_assignments "
                      "where upper(trailer_name) like '%%MANNI%%'")
        doc["deleted_41"] = {"row": b41, "rows_left": left, "sections_owned_by_its_masters": sec41,
                             "orphaned_template_assignments": orphan,
                             "costings": doc["manni"].get(DELETED_ID, {}).get("costings"),
                             "draft": doc["manni"].get(DELETED_ID, {}).get("draft", {}).get("has_draft")}
        say(f"   rows left (every FK / trailer_type_id column): {left or 'none'}")
        say(f"   sections whose owning master is on #41: {[(s['id'], s['name'], s['owner_master']) for s in sec41] or 'none'}")
        say(f"   orphaned template assignments naming a Manni: {orphan or 'none'}")

    (out / "discovery.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (out / "discovery.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
