"""RT6 §3.0 — Burt's rules as data: what the check would see on prod today. READ ONLY (one read-only session,
psycopg only; runs over any code). The classifier is the staged copy of backend/app/services/insulation_rules.py,
the file the RT6 guards will call, so the classification reported here is the guards' own.

    python rt6_discovery.py <DATABASE_URL> <out-dir>

Writes discovery.txt + discovery.json:
  1. CLASSIFICATION: every insulation master on every CHILLER and FREEZER body (master names only), as panel x
     insulation, with how each was derived; the unclassified ones; the same tally for every other family; and the
     freezers' side-door options — do they carry an insulation master?
  2. TODAY'S BREACHES under Burt's two rules (CHILLER: PU nowhere; FREEZER: EPS on ROOF and FLOOR only): each live
     costing on those bodies, by MECHANISM (a ticked master, a draft-flag alias), with its PRICED and THICKNESS
     signals beside it; a costing with no selection snapshot is judged by its priced lines. Quote numbers only.
  3. validated references that point at a breaching costing (recall re-applies it);
  4. the live drafts and their backups that would OFFER a forbidden choice (the restore / save warning's input).

Selects pricing / configuration / identity columns only — never a customer, contact, user or person column. Of
result_json only the insulation keys are used; nothing else of it is kept or written.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import insulation_rules as ir  # noqa: E402  (the staged copy of backend/app/services/insulation_rules.py)

# Burt's two rules, as the RT6 data step would store them (RT6 dispatch, default 2)
RULES = {
    "CHILLER": {"allowed": {p: ["EPS"] for p in ir.PANELS}},
    "FREEZER": {"allowed": {"FRONT": ["PU"], "SIDES": ["PU"], "ROOF": ["EPS", "PU"], "FLOOR": ["EPS", "PU"],
                            "DRD": ["PU"], "SRD": ["PU"]}},
}
SIDE_DOOR = ("SIDE DOOR", "SIDE-DOOR", "SIDEDOOR")


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


def saved_payload(res: dict) -> tuple[dict | None, str]:
    """A saved costing's selections as the payload the check reads, or None when it kept no selection snapshot."""
    st = res.get("input_state") or {}
    snap = (st.get("ui_snapshot") or {}) if isinstance(st.get("ui_snapshot"), dict) else {}
    sel = st.get("body_option_selections") or snap.get("body_option_selections") or {}
    flags = st.get("flag_overrides") or {}
    if not sel and not flags:
        return None, ("no input_state" if not st else "no selection snapshot")
    return {"body_option_selections": sel, "flag_overrides": flags}, "selection snapshot"


def priced(res: dict) -> list[tuple[str, str]]:
    """(panel, insulation) of every non-excluded EPS / PU line with a cost — what the saved quote actually priced."""
    out = []
    for it in res.get("items") or []:
        if not isinstance(it, dict) or it.get("excluded"):
            continue
        cat, ins = norm(it.get("category")), ir._LINE_MATERIAL.get(norm(it.get("material")))
        try:
            cost = float(it.get("line_cost") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        if ins and cat in ir.PANELS and cost > 0 and (cat, ins) not in out:
            out.append((cat, ins))
    return out


def thickness(res: dict, rule) -> list[tuple[str, str]]:
    bv = res.get("body_variables") or {}
    out = []
    for p in ir.PANELS:
        for ins in ir.INSULATIONS:
            if ins in rule[p]:
                continue
            try:
                if float(bv.get(f"{p} {ins}") or 0) > 0:
                    out.append((p, ins))
            except (TypeError, ValueError):
                pass
    return out


def offered(nodes: dict, cls, forb: dict) -> list[str]:
    """The forbidden choices a draft tree offers: a flag bound to a forbidden master (by id), an unbound flag or a
    category named after a forbidden choice."""
    bad_ids, bad_names = set(forb["master_ids"]), {norm(n) for n in forb["names"]}
    out = []
    for k, n in (nodes or {}).items():
        if not isinstance(n, dict):
            continue
        t, bid = n.get("type"), n.get("flagBindingId")
        label = n.get("label") or n.get("flagBindingName") or n.get("sourceCategoryKey") or k
        hit = None
        if t == "flag":
            if bid not in (None, ""):
                try:
                    if int(bid) in bad_ids:
                        hit = cls.by_master_id[int(bid)]
                except (TypeError, ValueError):
                    pass
            elif norm(n.get("flagBindingName") or n.get("label")) in bad_names:
                hit = cls.by_name.get(n.get("flagBindingName") or n.get("label")) or ("?", norm(label))
        elif t == "category" and norm(n.get("sourceCategoryKey")) in bad_names:
            hit = ("?", norm(n.get("sourceCategoryKey")))
        if hit:
            out.append(f"{t} '{label}'")
    return sorted(set(out))


def main(url: str, out_dir: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    lines: list[str] = []
    say = lines.append
    doc: dict = {"rules": RULES}
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

        bodies = rows("""select t.id, t.name, t.is_active, t.configurator_v2 v2, g.name family
                         from icb_costings.trailer_types t left join icb_costings.trailer_groups g on g.id = t.group_id
                         order by g.name nulls last, t.id""")
        bom = defaultdict(list)
        for r in rows("""select b.trailer_type_id tid, b.id, b.is_body_option, b.body_option_group, b.body_option_subgroup,
                                b.selection_group, m.name material_name, b.bom_section, b.bom_conditions,
                                b.body_option_linked, b.variable_value, b.body_option_default
                         from icb_costings.bill_of_materials b join icb_costings.materials m on m.id = b.material_id"""):
            bom[r.pop("tid")].append(r)
        classes = {b["id"]: ir.classify_body(bom[b["id"]]) for b in bodies}
        scope = {b["id"]: b for b in bodies if norm(b["family"]) in RULES}

        # ---- 1. classification ---------------------------------------------------------------------------
        say("\n== 1 · classification: every insulation master on the CHILLER and FREEZER bodies (panel x insulation)")
        doc["classification"] = {}
        for tid, b in scope.items():
            cls = classes[tid]
            fam = norm(b["family"])
            forb = ir.forbidden_choices(RULES[fam], cls)
            thick = {r["id"]: (r["variable_value"], r["body_option_default"]) for r in bom[tid] if r["is_body_option"]}
            say(f"   #{tid} {b['name']} ({fam}{'' if b['is_active'] else ', inactive'}{'' if b['v2'] else ', NON-v2'}): "
                f"{len(cls.by_master_id)} classified, {len(cls.unclassified)} unclassified, "
                f"{len(cls.lines)} insulation cost lines")
            recs = []
            for m in sorted(cls.masters, key=lambda m: (ir.PANELS.index(m.panel) if m.panel in ir.PANELS else 9,
                                                         m.insulation or "", m.id)):
                t, d = thick.get(m.id, (None, None))
                tag = f"{m.panel} x {m.insulation}" if m.panel else "UNCLASSIFIED"
                bad = " FORBIDDEN" if m.id in forb["master_ids"] else ""
                say(f"      {m.name:<16} -> {tag:<12}{bad:<10} T={t} default={d}  [{m.how}]")
                recs.append({"id": m.id, "name": m.name, "panel": m.panel, "insulation": m.insulation, "how": m.how,
                             "forbidden": bool(bad), "thickness": t, "default": d})
            for u in cls.unclassified:
                say(f"      !! UNCLASSIFIED {u['name']!r} (id {u['id']}): {u['reason']}")
            extra = sorted(set(cls.by_name) - {m.name for m in cls.masters})
            if extra:
                say(f"      names that also select an insulation (condition aliases): {extra}")
            doc["classification"][str(tid)] = {"masters": recs, "unclassified": cls.unclassified,
                                               "forbidden": forb, "aliases": extra}
        tally = Counter()
        for b in bodies:
            f = norm(b["family"]) or "(no family)"
            tally[(f, "classified")] += len(classes[b["id"]].by_master_id)
            tally[(f, "unclassified")] += len(classes[b["id"]].unclassified)
        say("   every family (the classifier is by mechanism, not by family): " + "; ".join(
            f"{f}: {tally[(f, 'classified')]} classified / {tally[(f, 'unclassified')]} unclassified"
            for f in sorted({k[0] for k in tally})))
        for b in bodies:
            for u in classes[b["id"]].unclassified:
                if b["id"] not in scope:
                    say(f"      !! #{b['id']} {b['name']} ({b['family'] or '-'}): {u['name']!r}: {u['reason']}")
        doc["tally"] = {f"{k[0]}:{k[1]}": v for k, v in tally.items()}

        say("\n   side doors on the freezers: do their options carry an insulation master?")
        sd_doc = {}
        for tid, b in scope.items():
            if norm(b["family"]) != "FREEZER":
                continue
            sd = [r for r in bom[tid] if any(k in norm(r["material_name"]) or k in norm(r["bom_section"])
                                              or k in norm(r["body_option_group"]) for k in SIDE_DOOR)]
            ins_masters = [m for m in classes[tid].masters if any(k in norm(m.group) or k in norm(m.name) for k in SIDE_DOOR)]
            sd_ins_lines = [r for r in sd if ir._LINE_MATERIAL.get(norm(r["material_name"]))]
            say(f"      #{tid} {b['name']}: {len(sd)} side-door row(s) "
                f"({sum(1 for r in sd if r['is_body_option'])} of them masters); insulation masters among them: "
                f"{len(ins_masters)}; EPS/PU cost lines among them: {len(sd_ins_lines)} — "
                + "; ".join(f"{r['bom_section']}: {r['material_name']}" for r in sd))
            sd_doc[str(tid)] = {"rows": len(sd), "insulation_masters": [m.name for m in ins_masters],
                                "insulation_lines": len(sd_ins_lines)}
        doc["side_doors"] = sd_doc

        # ---- 2. today's breaches --------------------------------------------------------------------------
        say("\n== 2 · today's breaches under Burt's two rules (live costings; quote numbers only)")
        calcs = rows("""select id, quote_number, status, created_at::date created, trailer_type_id tid,
                               deleted_at is not null deleted, result_json
                        from icb_costings.calculations where trailer_type_id = any(%s) order by id""", (list(scope),))
        per = Counter()
        found = []
        for c in calcs:
            b = scope[c["tid"]]
            fam = norm(b["family"])
            rule = ir.normalise_rule(RULES[fam])
            res = parse(c.pop("result_json"))
            payload, basis = saved_payload(res)
            sel_breach = [(x.panel, x.insulation, x.via) for x in ir.breaches(rule, classes[c["tid"]], payload or {})]
            pr = [(p, i) for p, i in priced(res) if i not in rule[p]]
            th = thickness(res, rule)
            unknown_ids = []
            if payload:
                known = {str(r["id"]) for r in bom[c["tid"]] if r["is_body_option"]}
                unknown_ids = [k for k, v in payload["body_option_selections"].items() if v is True and k not in known]
            kind = ("BREACH" if sel_breach else
                    "BREACH (priced; no selection snapshot)" if (pr and payload is None) else
                    "priced but not selected" if pr else
                    "thickness only — not a breach" if th else None)
            per[(c["tid"], c["deleted"], bool(kind and kind.startswith("BREACH")))] += 1
            if kind or unknown_ids:
                found.append({"id": c["id"], "quote_number": c["quote_number"], "status": c["status"],
                              "created": str(c["created"]), "deleted": c["deleted"], "body": c["tid"],
                              "body_name": b["name"], "family": fam, "kind": kind, "basis": basis,
                              "selected": sel_breach, "priced": pr, "thickness": th,
                              "unknown_master_ids": unknown_ids})
        for tid, b in scope.items():
            live = per[(tid, False, True)] + per[(tid, False, False)]
            say(f"   #{tid} {b['name']}: {live} live costing(s), {per[(tid, False, True)]} breaching; "
                f"{per[(tid, True, True)] + per[(tid, True, False)]} soft-deleted ({per[(tid, True, True)]} breaching)")
        live_b = [f for f in found if not f["deleted"] and (f["kind"] or "").startswith("BREACH")]
        say(f"\n   LIVE BREACHES: {len(live_b)}  (by status {dict(Counter(f['status'] for f in live_b))})")
        for f in found:
            if f["deleted"]:
                continue
            fmt = lambda xs: ",".join(f"{p} {i}" for p, i, *_ in xs) or "-"  # noqa: E731
            say(f"      {f['quote_number'] or '(no number) id ' + str(f['id']):<16} {f['status']:<10} {f['created']} "
                f"#{f['body']} {f['body_name']:<18} {f['kind'] or 'unmatched ids only'} · selected={fmt(f['selected'])} "
                f"priced={fmt(f['priced'])} thickness={fmt(f['thickness'])} [{f['basis']}]"
                + (f" · selection names master id(s) no longer on the body: {f['unknown_master_ids']}" if f["unknown_master_ids"] else ""))
        say(f"   soft-deleted costings carrying a breach: {sum(1 for f in found if f['deleted'] and (f['kind'] or '').startswith('BREACH'))} (not listed)")
        doc["costings"] = found

        # ---- 3. validated references ------------------------------------------------------------------------
        say("\n== 3 · validated references whose costing breaches (recall re-applies it)")
        bad_ids = {f["id"]: f for f in found if (f["kind"] or "").startswith("BREACH")}
        refs = rows("select id, calculation_id, active from icb_costings.validated_references where trailer_type_id = any(%s)",
                    (list(scope),))
        hit = [r for r in refs if r["calculation_id"] in bad_ids]
        say(f"   {len(refs)} reference(s) on these bodies; {len(hit)} point at a breaching costing: " + ("; ".join(
            f"ref {r['id']} ({'active' if r['active'] else 'retired'}) -> {bad_ids[r['calculation_id']]['quote_number']}"
            for r in hit) or "none"))
        doc["references"] = [{"id": r["id"], "calculation_id": r["calculation_id"], "active": r["active"]} for r in hit]

        # ---- 4. drafts and their backups ---------------------------------------------------------------------
        say("\n== 4 · drafts that would OFFER a forbidden choice (the save / restore warning's input)")
        drafts = {r["trailer_type_id"]: parse(r["payload"]).get("nodes") or {}
                  for r in rows("select trailer_type_id, payload from icb_costings.configurator_drafts "
                                "where trailer_type_id = any(%s)", (list(scope),))}
        backups = defaultdict(list)
        for r in rows("select id, trailer_type_id, label, created_at from icb_costings.configurator_draft_snapshots "
                      "where trailer_type_id = any(%s) order by created_at", (list(scope),)):
            backups[r["trailer_type_id"]].append(r)
        payloads = {r["id"]: parse(r["payload"]).get("nodes") or {}
                    for r in rows("select id, payload from icb_costings.configurator_draft_snapshots "
                                  "where trailer_type_id = any(%s)", (list(scope),))}
        doc["drafts"] = {}
        for tid, b in scope.items():
            forb = ir.forbidden_choices(RULES[norm(b["family"])], classes[tid])
            live = offered(drafts.get(tid, {}), classes[tid], forb)
            bk = [(r["id"], f"{r['created_at']:%Y-%m-%d}", offered(payloads.get(r["id"], {}), classes[tid], forb))
                  for r in backups[tid]]
            say(f"   #{tid} {b['name']}: live draft offers {len(live)} forbidden choice(s){': ' + ', '.join(live) if live else ''}; "
                f"{len(bk)} backup(s), {sum(1 for _i, _d, o in bk if o)} would offer one — "
                + "; ".join(f"#{i} {d}: {len(o)}" for i, d, o in bk))
            doc["drafts"][str(tid)] = {"live": live, "backups": [{"id": i, "date": d, "offers": o} for i, d, o in bk]}

    out.mkdir(parents=True, exist_ok=True)
    (out / "discovery.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "discovery.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.splitlines()[4].strip())
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
