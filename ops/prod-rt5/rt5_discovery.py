"""RT5 §3.0 — can Burt's two insulation rules still be broken on prod? READ ONLY (one read-only session,
psycopg only — runs over any code).

    python rt5_discovery.py <DATABASE_URL> <out-dir>

Burt's rulings (5 Oct): (1) no PU on a CHILLER, any panel; (2) a FREEZER takes EPS on the ROOF and FLOOR only —
never on the FRONT, SIDES or the doors (DRD / SRD). Michael removed those choices from the drafts by hand; the
masters (BOM rows) stay. Writes discovery.json + discovery.txt:

  1. the families: every body in CHILLER / FREEZER / EXPLOSIVE / ICE CREAM (active or not), v2 or not — the note's
     scope — and any body NAMED chiller/freezer outside its family;
  2. per chiller / freezer body: each forbidden master (name, id, thickness, default) — offered by the live draft?
     by a saved draft backup (a restore would bring it back)?
  3. saved costings on those bodies that CARRY a forbidden choice, by three signals: PRICED (a non-excluded PU / EPS
     line with a cost in that panel's section), THICKNESS (the priced body variable > 0), SELECTED (the saved
     selection / flag). Quote number, status and date only;
  4. validated references whose costing is in (3) (reference id + the costing's quote number only);
  5. the freezers' side-door lines (the note's wording: "doors" or "rear doors").

Selects pricing / configuration / identity columns only — never a customer, contact, user or person column:
calculations are read for their id, quote number, status, created date, body and result_json, and only the
insulation keys of result_json are used (nothing else of it is kept or written).
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

PANELS = ("FRONT", "SIDES", "ROOF", "FLOOR", "DRD", "SRD")
RULES = {   # family -> (the insulation it may not carry, the panels where it may not)
    "CHILLER": ("PU", PANELS),
    "FREEZER": ("EPS", ("FRONT", "SIDES", "DRD", "SRD")),
}
FAMILIES_SHOWN = ("CHILLER", "FREEZER", "EXPLOSIVE", "ICE CREAM")
SIDE_DOOR = re.compile(r"SIDE\s*-?\s*DOOR", re.I)


def norm(s) -> str:
    return " ".join(str(s or "").upper().split())


def parse(p) -> dict:
    if isinstance(p, dict):
        return p
    try:
        d = json.loads(p or "{}")
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def rule_of(family: str | None, name: str) -> str | None:
    """The rule a body falls under: its family, else (a body outside the families) its name."""
    f = norm(family)
    if f in RULES:
        return f
    for k in RULES:
        if k in norm(name).split():
            return k
    return None


def forbidden(rule: str) -> list[tuple[str, str]]:
    kind, panels = RULES[rule]
    return [(p, f"{p} {kind}") for p in panels]


def offers(nodes: dict, master_id: int, master_name: str) -> list[str]:
    """The draft nodes that offer a master: a flag bound to it by id (or by name when unbound), or a category keyed
    on its name (which forces it on)."""
    out = []
    for k, n in (nodes or {}).items():
        if not isinstance(n, dict):
            continue
        t, bid = n.get("type"), n.get("flagBindingId")
        hit = False
        if t == "flag":
            if bid not in (None, ""):
                try:
                    hit = int(bid) == int(master_id)
                except (TypeError, ValueError):
                    hit = False
            else:
                hit = norm(n.get("flagBindingName") or n.get("label")) == norm(master_name)
        elif t == "category":
            hit = norm(n.get("sourceCategoryKey")) == norm(master_name)
        if hit:
            out.append(f"{t} '{n.get('label') or n.get('flagBindingName') or n.get('sourceCategoryKey') or k}'")
    return out


def carried(rule: str, res: dict, master_ids: dict[str, int]) -> dict[str, list[str]]:
    """{signal: [panels]} — what a saved costing carries against `rule`. Pure (tests feed it a dict)."""
    kind, panels = RULES[rule]
    out: dict[str, list[str]] = {"priced": [], "thickness": [], "selected": []}
    for it in res.get("items") or []:
        if not isinstance(it, dict):
            continue
        cat, mat = norm(it.get("category")), norm(it.get("material"))
        try:
            cost = float(it.get("line_cost") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        if cat in panels and mat == kind and not it.get("excluded") and cost > 0 and cat not in out["priced"]:
            out["priced"].append(cat)
    bv = res.get("body_variables") or {}
    for p in panels:
        try:
            if float(bv.get(f"{p} {kind}") or 0) > 0:
                out["thickness"].append(p)
        except (TypeError, ValueError):
            pass
    st = res.get("input_state") or {}
    sel = st.get("body_option_selections") or {}
    snap = (st.get("ui_snapshot") or {}).get("body_option_selections") or {}
    flags = st.get("flag_overrides") or {}
    for p in panels:
        name = f"{p} {kind}"
        mid = master_ids.get(name)
        on = (mid is not None and (sel.get(str(mid)) is True or snap.get(str(mid)) is True)) \
            or any(norm(k) == name and v is True for k, v in flags.items())
        if on:
            out["selected"].append(p)
    return out


def main(url: str, out_dir: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    lines: list[str] = []
    say = lines.append
    doc: dict = {}
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()

        def rows(sql, args=None):
            cur.execute(sql, args or ())
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        ro = rows("select current_database() db, current_setting('transaction_read_only') ro")[0]
        if ro["ro"] != "on":
            raise SystemExit(f"the session is not read-only: {ro}")
        say(f"database {ro['db']} · read-only session")
        doc["database"] = ro["db"]

        # ---- 1. families -----------------------------------------------------------------------------------
        bodies = rows("""select t.id, t.name, t.is_active, t.configurator_v2 v2, g.name family
                         from icb_costings.trailer_types t left join icb_costings.trailer_groups g on g.id = t.group_id
                         order by g.name nulls last, t.name""")
        say("\n== 1 · the families (the note's scope): every body, active or not")
        doc["bodies"] = bodies
        for fam in FAMILIES_SHOWN:
            fb = [b for b in bodies if norm(b["family"]) == fam]
            say(f"   {fam}: {len(fb)} bodies — " + "; ".join(
                f"#{b['id']} {b['name']}{'' if b['is_active'] else ' (inactive)'}{'' if b['v2'] else ' NON-v2'}" for b in fb))
        stray = [b for b in bodies if rule_of(None, b["name"]) and norm(b["family"]) != rule_of(None, b["name"])]
        say("   named CHILLER/FREEZER but outside that family: " + ("; ".join(
            f"#{b['id']} {b['name']} (family {b['family'] or '-'})" for b in stray) or "none"))
        doc["stray"] = [b["id"] for b in stray]
        scope = {b["id"]: b for b in bodies if rule_of(b["family"], b["name"])}

        # ---- 2. the forbidden masters, the drafts and their backups -----------------------------------------
        say("\n== 2 · per chiller / freezer body: the forbidden masters (they stay; the drafts stopped offering them)")
        masters = defaultdict(dict)
        for r in rows("""select b.trailer_type_id tid, b.id, m.name, b.variable_value thick, b.body_option_default dflt
                         from icb_costings.bill_of_materials b join icb_costings.materials m on m.id = b.material_id
                         where b.is_body_option and b.trailer_type_id = any(%s)""", (list(scope),)):
            masters[r["tid"]][norm(r["name"])] = r
        drafts = {r["trailer_type_id"]: parse(r["payload"]).get("nodes") or {}
                  for r in rows("select trailer_type_id, payload from icb_costings.configurator_drafts where trailer_type_id = any(%s)",
                                (list(scope),))}
        backups = defaultdict(list)
        for tbl in ("configurator_draft_snapshots", "configurator_snapshots"):
            for r in rows(f"select id, trailer_type_id, created_at, payload from icb_costings.{tbl} where trailer_type_id = any(%s)",
                          (list(scope),)):
                backups[r["trailer_type_id"]].append((tbl, r["id"], r["created_at"], parse(r["payload"]).get("nodes") or {}))
        doc["masters"] = {}
        for tid, b in scope.items():
            rule = rule_of(b["family"], b["name"])
            say(f"   #{tid} {b['name']} ({rule}{'' if b['is_active'] else ', inactive'}{'' if b['v2'] else ', NON-v2: no draft, flat panel'})"
                f" · draft {'present' if tid in drafts else 'NONE'} · backups {len(backups[tid])}")
            recs = []
            for panel, name in forbidden(rule):
                m = masters[tid].get(name)
                if not m:
                    say(f"      {name:<10} no master")
                    continue
                live = offers(drafts.get(tid, {}), m["id"], name)
                bk = [f"{t.split('_')[1]}#{i} {c:%Y-%m-%d}" for t, i, c, nodes in backups[tid] if offers(nodes, m["id"], name)]
                say(f"      {name:<10} master {m['id']} T={m['thick']} default={m['dflt']} · live draft: "
                    f"{', '.join(live) or 'not offered'} · backups offering it: {', '.join(bk) or 'none'}")
                recs.append({"name": name, "id": m["id"], "thickness": m["thick"], "default": m["dflt"],
                             "offered_live": live, "offered_by_backups": bk})
            doc["masters"][str(tid)] = recs

        # ---- 3. saved costings ---------------------------------------------------------------------------
        say("\n== 3 · saved costings on chiller / freezer bodies that carry a forbidden choice (quote numbers only)")
        calcs = rows("""select id, quote_number, status, created_at::date created, trailer_type_id tid,
                               deleted_at is not null deleted, result_json
                        from icb_costings.calculations where trailer_type_id = any(%s) order by id""", (list(scope),))
        per_body = Counter((c["tid"], c["deleted"]) for c in calcs)
        hits = []
        for c in calcs:
            b = scope[c["tid"]]
            rule = rule_of(b["family"], b["name"])
            mid = {n: r["id"] for n, r in masters[c["tid"]].items()}
            res = parse(c.pop("result_json"))
            sig = carried(rule, res, mid)
            if any(sig.values()):
                hits.append({"id": c["id"], "quote_number": c["quote_number"], "status": c["status"],
                             "created": str(c["created"]), "deleted": c["deleted"], "body": c["tid"],
                             "body_name": b["name"], "rule": rule, "legacy": "input_state" not in res, **sig})
        for tid, b in scope.items():
            say(f"   #{tid} {b['name']}: {per_body[(tid, False)]} live costing(s), {per_body[(tid, True)]} soft-deleted")
        for rule in RULES:
            rh = [h for h in hits if h["rule"] == rule and not h["deleted"]]
            say(f"\n   {rule} ({'PU anywhere' if rule == 'CHILLER' else 'EPS on FRONT / SIDES / doors'}): "
                f"{len(rh)} live costing(s) carry it — by status {dict(Counter(h['status'] for h in rh))}")
            for h in rh:
                say(f"      {h['quote_number'] or '(no number) id ' + str(h['id']):<16} {h['status']:<10} {h['created']} "
                    f"#{h['body']} {h['body_name']:<20} priced={','.join(h['priced']) or '-'} "
                    f"thickness={','.join(h['thickness']) or '-'} selected={','.join(h['selected']) or '-'}"
                    f"{' (legacy record: no input_state)' if h['legacy'] else ''}")
            dh = [h for h in hits if h["rule"] == rule and h["deleted"]]
            say(f"      soft-deleted carrying it: {len(dh)} (not listed)")
        doc["costings"] = hits
        doc["costings_per_body"] = {f"{t}:{'deleted' if d else 'live'}": n for (t, d), n in per_body.items()}

        # ---- 4. validated references ------------------------------------------------------------------------
        say("\n== 4 · validated references whose costing carries a forbidden choice (recall re-applies it)")
        hit_ids = {h["id"]: h for h in hits}
        refs = rows("select id, calculation_id, active from icb_costings.validated_references where trailer_type_id = any(%s)",
                    (list(scope),))
        bad = [r for r in refs if r["calculation_id"] in hit_ids]
        say(f"   {len(refs)} reference(s) on these bodies; {len(bad)} point at a costing in §3: " + ("; ".join(
            f"ref {r['id']} ({'active' if r['active'] else 'retired'}) -> {hit_ids[r['calculation_id']]['quote_number'] or r['calculation_id']}"
            for r in bad) or "none"))
        doc["references"] = [{"id": r["id"], "calculation_id": r["calculation_id"], "active": r["active"]} for r in bad]

        # ---- 5. side doors on the freezers --------------------------------------------------------------------
        say("\n== 5 · side-door lines on the freezer bodies (the note's wording)")
        fz = [t for t, b in scope.items() if rule_of(b["family"], b["name"]) == "FREEZER"]
        sd = rows("""select b.trailer_type_id tid, b.id, b.bom_section, m.name from icb_costings.bill_of_materials b
                     join icb_costings.materials m on m.id = b.material_id where b.trailer_type_id = any(%s)""", (fz,))
        sd = [r for r in sd if SIDE_DOOR.search(r["name"] or "") or SIDE_DOOR.search(r["bom_section"] or "")]
        for tid in fz:
            mine = [r for r in sd if r["tid"] == tid]
            say(f"   #{tid} {scope[tid]['name']}: {len(mine)} line(s) — " + "; ".join(
                f"{r['bom_section']}: {r['name']}" for r in mine))
        doc["side_doors"] = sd

    out.mkdir(parents=True, exist_ok=True)
    (out / "discovery.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "discovery.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.splitlines()[2].strip())
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
