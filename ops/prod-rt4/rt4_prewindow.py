"""RT4_RULING_2 — the pre-window check of Michael's hand removals on prod (chillers: no PU; freezers: EPS on the ROOF
and FLOOR only). READ ONLY: every query runs in one read-only session (default_transaction_read_only AND
SET TRANSACTION READ ONLY).

    PYTHONPATH=/opt/icb-platform/backend python rt4_prewindow.py facts <out-dir> <stage-dir>
    PYTHONPATH=/opt/icb-platform/backend python rt4_prewindow.py cells <out-dir> <cli-report-dir> <base-run-id>

facts — (a) and (b):
  (a) WHAT CHANGED.
      * The 15 bodies of the committed CI snapshot (all.json = prod after RT2's close, 2 Oct 17:33) are exported NOW
        with the audit tool's own exporter and diffed against it, table by table and row by row: every BOM row
        deleted, added or changed (body, master or line, name, group / subgroup, section) and every material change.
        RT3's families (3 Oct: trailer_types.group_id, trailer_groups) are labelled as such.
      * The drafts (Settings page) of every chiller and freezer body and the other snapshot bodies: the saved time
        against the 3 Oct door report; a changed draft's nodes against its Settings-page backups
        (configurator_draft_snapshots); per body, each insulation master and whether a draft node offers it, and
        Burt's two rulings read as data (chillers: no PU offered; freezers: EPS offered on ROOF and FLOOR only).
      * Every per-line rule (bom_conditions) on those bodies that names a master which no longer exists.
  (b) MANIFEST A's REAR FRAME & FLOOR PLATE rules: per line, the conditions as written vs now, and each condition's
      master by option_id AND by name on that body; then the ENGINE — every Manifest A body priced DRD and SRD with
      each door-insulation master it still has (the payload of docs/audit/srd_rear_frame_2026-09/verify_rule_on_db.py):
      DRD must cost REAR FRAME, SRD must exclude every REAR FRAME line by its condition.
cells — (d): the deployed code's CLI reports (the five packs, --env prod) against the 3 Oct page run
  costing_audit_runs #<base-run-id>, cell by cell on (status, base_status, excel_total, mes_total to the cent).

Writes only under <out-dir>. Selects pricing / configuration columns only — configurator_drafts.updated_by,
configurator_draft_snapshots.created_by and costing_audit_runs.started_by are never selected.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

RF = "REAR FRAME & FLOOR PLATE"
PANELS = ("FRONT", "DRD", "SRD", "SIDES", "ROOF", "FLOOR")
INS_RE = re.compile(r"^(FRONT|DRD|SRD|SIDES|ROOF|FLOOR) (EPS|PU)$")
SIX = (25, 26, 27, 19, 20, 21)                    # the 3 chillers and 3 freezers RT4_RULING_2 (b) names
# RT3 (3 Oct): every body's family (group_id), RHINORANGE kept its quote template by an override when it moved
# to OTHER (override_report_template_id), and the families themselves (trailer_groups)
RT3_EXPECTED = {("trailer_types", "group_id"), ("trailer_types", "override_report_template_id"), ("trailer_groups", "*")}
ALL_PACKS = ("chillers", "freezers", "icecream", "explosive")      # the page's All (smoke is a subset)
STATUSES = ("PASS", "ACCEPTED", "SKIP", "UNVERIFIABLE", "EXPIRED", "FLAG", "PRESENCE", "UNMAPPED", "NO_GOLDEN")


def norm(s) -> str:
    return " ".join(str(s or "").upper().split())


def short(v, n: int = 70) -> str:
    s = json.dumps(v, default=str) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 1] + "…"


def body_kind(name: str, family: str | None) -> str | None:
    for k in ("CHILLER", "FREEZER"):
        if k in norm(name).split() or norm(family) == k:
            return k
    return None


# ---------------------------------------------------------------------------------------------------------------
# (a) the snapshot diff — pure
# ---------------------------------------------------------------------------------------------------------------
def snapshot_diff(base: dict, now: dict, pk_cols: dict[str, list[str]]) -> dict:
    """Row-by-row diff of two exporter documents. Returns {table: {removed, added, changed, cols_only_*}}."""
    out = {}
    for t in sorted(set(base["tables"]) | set(now["tables"])):
        b_rows, n_rows = base["tables"].get(t, []), now["tables"].get(t, [])
        pk = pk_cols.get(t) or (["id"] if (b_rows or n_rows) and "id" in (b_rows or n_rows)[0] else None)
        if not pk:
            continue
        key = lambda r: tuple(r.get(c) for c in pk)          # noqa: E731
        bi, ni = {key(r): r for r in b_rows}, {key(r): r for r in n_rows}
        bcols = set().union(*[set(r) for r in b_rows]) if b_rows else set()
        ncols = set().union(*[set(r) for r in n_rows]) if n_rows else set()
        common = bcols & ncols if (b_rows and n_rows) else (bcols | ncols)
        changed = []
        for k in sorted(set(bi) & set(ni), key=str):
            d = {c: (bi[k].get(c), ni[k].get(c)) for c in sorted(common) if bi[k].get(c) != ni[k].get(c)}
            if d:
                changed.append({"pk": list(k), "cols": d})
        rec = {"removed": [bi[k] for k in sorted(set(bi) - set(ni), key=str)],
               "added": [ni[k] for k in sorted(set(ni) - set(bi), key=str)],
               "changed": changed,
               "cols_only_before": sorted(bcols - ncols) if (b_rows and n_rows) else [],
               "cols_only_now": sorted(ncols - bcols) if (b_rows and n_rows) else []}
        if any(rec.values()):
            out[t] = rec
    return out


def describe_bom(r: dict, names: dict, bodies: dict) -> str:
    kind = "MASTER" if r.get("is_body_option") else "line"
    grp = "/".join(x for x in (r.get("body_option_group"), r.get("body_option_subgroup")) if x)
    return (f"body {r.get('trailer_type_id')} {bodies.get(r.get('trailer_type_id'), '?')} · {kind} bom {r.get('id')} "
            f"'{names.get(r.get('material_id'), '?')}'" + (f" [{grp}]" if grp else "")
            + f" · section {r.get('bom_section') or '-'}" + (f" · T={r.get('variable_value')}" if r.get("is_body_option") else ""))


def render_diff(diff: dict, base: dict, now: dict, say) -> dict:
    """Print the diff; return counts for the verdict."""
    names = {m["id"]: m.get("name") for d in (base, now) for m in d["tables"].get("materials", [])}
    bodies = {t["id"]: t.get("name") for d in (base, now) for t in d["tables"].get("trailer_types", [])}
    counts = Counter()
    if not diff:
        say("   no difference in any table: the 15 bodies' pricing rows are exactly as on 2 Oct 17:33")
    for t, rec in diff.items():
        rt3 = (t, "*") in RT3_EXPECTED
        say(f"   -- {t}: removed {len(rec['removed'])} · added {len(rec['added'])} · changed {len(rec['changed'])}"
            + ("   (RT3's families, 3 Oct: expected)" if rt3 else ""))
        if rec["cols_only_before"] or rec["cols_only_now"]:
            say(f"      columns only before {rec['cols_only_before']} · only now {rec['cols_only_now']} (schema, not data)")
        for label, rows in (("REMOVED", rec["removed"]), ("ADDED", rec["added"])):
            for r in rows[:200]:
                if t == "bill_of_materials":
                    counts[f"bom_{label.lower()}" + ("_master" if r.get("is_body_option") else "_line")] += 1
                    say(f"      {label:<7} {describe_bom(r, names, bodies)}")
                else:
                    if not rt3:
                        counts[f"{t}_{label.lower()}"] += 1
                    say(f"      {label:<7} {t} {short({k: v for k, v in r.items() if k in ('id', 'name', 'key')} or r, 110)}"
                        + ("   (RT3)" if rt3 else ""))
        nb = {r["id"]: r for r in base["tables"].get(t, []) if "id" in r}
        nn = {r["id"]: r for r in now["tables"].get(t, []) if "id" in r}
        for c in rec["changed"][:300]:
            only_rt3 = all((t, col) in RT3_EXPECTED for col in c["cols"]) or rt3
            row = nn.get(c["pk"][0]) or nb.get(c["pk"][0]) or {}
            what = describe_bom(row, names, bodies) if t == "bill_of_materials" else \
                f"{t} {c['pk']} {short(row.get('name') or row.get('key') or '', 50)}"
            if not only_rt3:
                counts[f"{t}_changed"] += 1
                if t == "bill_of_materials" and row.get("is_body_option"):
                    counts["bom_changed_master"] += 1
            for col, (b, n) in c["cols"].items():
                say(f"      CHANGED {what} · {col}: {short(b, 60)} -> {short(n, 60)}"
                    + ("   (RT3)" if rt3 or (t, col) in RT3_EXPECTED else ""))
    return dict(counts)


# ---------------------------------------------------------------------------------------------------------------
# (a) drafts — pure helpers
# ---------------------------------------------------------------------------------------------------------------
def parse_payload(p) -> dict:
    if isinstance(p, dict):
        return p
    try:
        d = json.loads(p or "{}")
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def node_label(n: dict) -> str:
    return str(n.get("label") or n.get("name") or n.get("sourceCategoryKey") or n.get("flagBindingName") or n.get("id"))


def node_path(nodes: dict, n: dict) -> str:
    parts, pid, seen = [], n.get("parentId"), set()
    while pid and pid in nodes and pid not in seen:
        seen.add(pid)
        parts.append(node_label(nodes[pid]))
        pid = nodes[pid].get("parentId")
    return " > ".join(reversed(parts)) or "(top)"


def describe_node(nodes: dict, n: dict) -> str:
    bits = [f"{n.get('type', '?')} '{node_label(n)}'"]
    if n.get("sourceCategoryKey"):
        bits.append(f"key={n['sourceCategoryKey']}")
    if n.get("flagBindingId") or n.get("flagBindingName"):
        bits.append(f"bound={n.get('flagBindingId')}/{n.get('flagBindingName')}")
    return " ".join(bits) + f" under {node_path(nodes, n)}"


def node_diff(before: dict, after: dict) -> dict:
    nb, na = before.get("nodes") or {}, after.get("nodes") or {}
    removed = [describe_node(nb, nb[k]) for k in nb if k not in na and isinstance(nb[k], dict)]
    added = [describe_node(na, na[k]) for k in na if k not in nb and isinstance(na[k], dict)]
    changed = []
    for k in nb:
        if k in na and isinstance(nb[k], dict) and isinstance(na[k], dict) and nb[k] != na[k]:
            d = {f: (nb[k].get(f), na[k].get(f)) for f in sorted(set(nb[k]) | set(na[k])) if nb[k].get(f) != na[k].get(f)}
            changed.append(describe_node(na, na[k]) + " · " + "; ".join(f"{f}: {short(b, 30)} -> {short(a, 30)}"
                                                                         for f, (b, a) in d.items()))
    return {"removed": removed, "added": added, "changed": changed}


def refs_to_master(nodes: dict, m: dict) -> list[str]:
    """The draft nodes that offer master m (a flag bound to it by id, or by name when unbound; a category keyed on
    its name)."""
    out = []
    for n in nodes.values():
        if not isinstance(n, dict):
            continue
        t = n.get("type")
        bid = n.get("flagBindingId")
        hit = False
        if t == "flag":
            if bid not in (None, ""):
                try:
                    hit = int(bid) == int(m["id"])
                except (TypeError, ValueError):
                    hit = False
            else:
                hit = norm(n.get("flagBindingName") or n.get("label")) == norm(m["name"])
        elif t == "category":
            hit = norm(n.get("sourceCategoryKey")) == norm(m["name"])
        if hit:
            out.append(describe_node(nodes, n))
    return out


def stale_bindings(nodes: dict, master_ids: set[int]) -> list[str]:
    out = []
    for n in nodes.values():
        if isinstance(n, dict) and n.get("type") == "flag" and n.get("flagBindingId") not in (None, ""):
            try:
                ok = int(n["flagBindingId"]) in master_ids
            except (TypeError, ValueError):
                ok = False
            if not ok:
                out.append(describe_node(nodes, n))
    return out


def burt_check(kind: str | None, offered: dict[str, set]) -> tuple[bool | None, str]:
    """offered: panel -> {'EPS','PU'} that a draft node offers. (ok, text) — None when the body is out of scope."""
    if kind == "CHILLER":
        pu = sorted(p for p, ks in offered.items() if "PU" in ks)
        return (not pu, "no PU offered (as ruled)" if not pu else f"!! PU still offered on {', '.join(pu)}")
    if kind == "FREEZER":
        eps = sorted(p for p, ks in offered.items() if "EPS" in ks)
        bad = [p for p in eps if p not in ("ROOF", "FLOOR")]
        return (not bad, (f"EPS offered on {', '.join(eps) or 'no panel'} only (as ruled)" if not bad
                          else f"!! EPS still offered on {', '.join(bad)}"))
    return None, "-"


def parse_door_report(text: str) -> dict[int, str]:
    """{body id: 'YYYY-MM-DD HH:MM' draft saved} from a committed door report."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+.+?\|\s+(\d{4}-\d\d-\d\d \d\d:\d\d|-)\s+\|", line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


# ---------------------------------------------------------------------------------------------------------------
# (b) Manifest A — pure helpers
# ---------------------------------------------------------------------------------------------------------------
def cond_list(raw) -> tuple[str, list]:
    """('include'|'exclude'|'always_exclude'|'none'|'malformed', [conditions])"""
    if raw in (None, "", "[]"):
        return "none", []
    try:
        p = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return "malformed", []
    if isinstance(p, list):
        return ("include" if p else "none"), p
    if isinstance(p, dict):
        mode = (p.get("mode") or "include").lower()
        return mode, list(p.get("all") or [])
    return "malformed", []


def cond_key(c: dict) -> tuple:
    return (norm(c.get("option")), (c.get("equals") or "Y").upper(), c.get("option_id"))


def check_condition(c: dict, body_id: int, masters_by_id: dict, masters_by_name: dict,
                    was_master: set | None = None) -> tuple[bool | None, str]:
    """(names an existing master on this body — None for a condition on a draft-only flag that never had a master
    row, text). The engine evaluates a condition by the option's NAME against the selected names."""
    oid, name = c.get("option_id"), norm(c.get("option"))
    m = masters_by_id.get(oid) if oid is not None else None
    on_body = m is not None and m["trailer_type_id"] == body_id
    named = [x for x in masters_by_name.get((body_id, name), [])]
    cond = f"{c.get('option')}={c.get('equals')}"
    if on_body and norm(m["name"]) == name:
        return True, f"{cond} -> master {oid} exists"
    if named:
        why = (f"master {oid} is '{m['name']}', but " if on_body else f"master {oid} gone, but " if oid is not None else "")
        return True, f"{cond} -> {why}'{c.get('option')}' exists as {[x['id'] for x in named]} (the engine matches by NAME)"
    if on_body:
        return False, f"{cond} -> master {oid} is named '{m['name']}' and no master is named '{c.get('option')}' (the engine matches by NAME)"
    if oid is None and not (was_master and (body_id, name) in was_master):
        return None, f"{cond} -> a draft flag by name (no master row, before or now)"
    return False, (f"{cond} -> " + (f"master {oid} GONE, " if oid is not None else "the master is GONE, ")
                   + f"no master named '{c.get('option')}' on this body: reads as not selected (N)")


# ---------------------------------------------------------------------------------------------------------------
# (b) the engine — needs the deployed app
# ---------------------------------------------------------------------------------------------------------------
def price_rear_frame(db, tid: int) -> list[dict]:
    """Price body `tid` DRD and SRD with every door-insulation master it still has; the RF verdict per combination.
    The payload is verify_rule_on_db.py's (the live calculator's), tolerant of a missing master."""
    from app.database import BillOfMaterial, TrailerType
    from app.formula_engine import calculate_bom
    from app.routers.calculator import (_apply_body_variable_overrides, _bom_load_options, _build_body_variables,
                                        _build_bom_items)
    from app.services import get_formula_lib, get_global_vars, get_section_snapshot
    tt = db.query(TrailerType).filter_by(id=tid).first()
    if tt is None:
        return [{"door": "-", "ins": "-", "ok": False, "text": f"body {tid} not found"}]
    rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
    order = get_section_snapshot().order
    rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                             r.material.name.lower() if r.material else ""))
    masters = [r for r in rows if r.is_body_option and r.material]
    by_name = {}
    for r in masters:
        by_name.setdefault(norm(r.material.name), r)
    ins = {}
    for r in masters:
        mm = INS_RE.match(norm(r.material.name))
        if mm and mm.group(1) in ("DRD", "SRD"):
            ins.setdefault((mm.group(1), mm.group(2)), r)
    doortype = "DRD" in by_name and "SRD" in by_name
    n_rf = sum(1 for r in rows if r.bom_section == RF)
    dims = {"length": tt.default_length or 4.0, "width": tt.default_width or 2.4, "height": tt.default_height or 2.2}
    out = []
    for door in ("DRD", "SRD"):
        other = "SRD" if door == "DRD" else "DRD"
        for kind in ("EPS", "PU"):
            if (door, kind) not in ins:
                continue
            sel = {str(r.id): False for r in ins.values()}
            sel[str(ins[(door, kind)].id)] = True
            if doortype:
                sel[str(by_name["DRD"].id)] = door == "DRD"
                sel[str(by_name["SRD"].id)] = door == "SRD"
                if door == "DRD" and ("SRD", kind) in ins:      # CHILLER LARGE: the SRD radio stays ticked on DRD
                    sel[str(ins[("SRD", kind)].id)] = True
            flags = {r.material.name: sel[str(r.id)] for r in masters if str(r.id) in sel}
            excl = [other] if doortype else [other, f"{other} DOOR FITTINGS"]
            items = _build_bom_items(rows, dims, {}, sel, db, excl, trailer=tt, flag_overrides=flags,
                                     include_all_items=False, user_excluded_bom_ids=[],
                                     optional_sections_enabled=[], formula_overrides=None,
                                     insulation_foam=getattr(tt, "default_insulation_foam", None) or "32D")
            bv = _build_body_variables(rows)
            _apply_body_variable_overrides(bv, {ins[(door, kind)].material.name: 0.06})
            res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
            rf = [it for it in res["items"] if it.get("category") == RF]
            total = round(sum(float(it.get("line_cost") or 0) for it in rf), 2)
            nx = sum(1 for it in rf if it.get("excluded"))
            by = {it.get("excluded_by") for it in rf if it.get("excluded")}
            reason = next((it.get("excluded_reason") for it in rf if it.get("excluded")), "") or "-"
            if door == "DRD":
                ok = total > 0 and nx == 0 and len(rf) == n_rf > 0
            else:
                ok = total == 0 and nx == n_rf == len(rf) > 0 and (by == {"condition"} or by == {None})
            out.append({"door": door, "ins": kind, "ok": ok, "rf_total": total, "excluded": nx, "rf_lines": len(rf),
                        "text": f"{door} {kind:<3} REAR FRAME {total:>10.2f}  excluded {nx}/{len(rf)}  {reason}"})
    if not out:
        out.append({"door": "-", "ins": "-", "ok": False, "text": "no DRD/SRD insulation master left to price"})
    return out


# ---------------------------------------------------------------------------------------------------------------
def open_ro():
    """The app's database, one connection, one READ ONLY transaction (asserted)."""
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.pool import NullPool
    import app.database as _db
    eng = create_engine(_db.engine.url, poolclass=NullPool,
                        connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    conn.execute(text("SET TRANSACTION READ ONLY"))
    ro = (conn.execute(text("show default_transaction_read_only")).scalar(),
          conn.execute(text("show transaction_read_only")).scalar())
    if ro != ("on", "on"):
        raise SystemExit(f"the session is not read-only: {ro}")
    return eng, conn


def q(conn, sql: str, **params) -> list[dict]:
    from sqlalchemy import text
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def facts(conn, db, stage: Path, out: Path, now_doc: dict | None, say) -> dict:
    """(a) + (b) on `conn` (and an ORM session `db` on the same connection for the engine). Returns verdicts."""
    verdict: dict = {}
    base_doc = json.loads((stage / "all.json").read_text(encoding="utf-8"))
    snap_ids = [int(x) for x in base_doc["trailer_ids"]]
    db_name = q(conn, "select current_database() as d")[0]["d"]
    say(f"database {db_name} · read-only session · snapshot baseline all.json generated {base_doc.get('generated_at')}")

    # ---- the bodies in scope ----------------------------------------------------------------------------------
    bodies = q(conn, """select t.id, t.name, t.is_active, t.configurator_v2, g.name as family
                          from trailer_types t left join trailer_groups g on g.id = t.group_id
                         where upper(t.name) like '%CHILLER%' or upper(t.name) like '%FREEZER%'
                            or upper(coalesce(g.name, '')) in ('CHILLER', 'FREEZER') or t.id = any(:ids)
                         order by t.id""", ids=snap_ids)
    for b in bodies:
        b["kind"] = body_kind(b["name"], b["family"])
    scope = [b for b in bodies if b["kind"] and "[DELETED-" not in norm(b["name"])]
    ids = [b["id"] for b in bodies]
    bname = {b["id"]: b["name"] for b in bodies}
    say("\n== scope: every chiller and freezer body (by name or family), and the 15 snapshot bodies")
    for b in bodies:
        say(f"   #{b['id']:<3} {b['name']:<28} {b['kind'] or '-':<8} family={b['family'] or '-':<10} "
            f"active={b['is_active']!s:<5} v2={b['configurator_v2']}" + ("" if b["id"] in snap_ids else "  (not in the snapshot)"))

    # ---- (a1) the snapshot diff ---------------------------------------------------------------------------------
    say("\n== (a1) pricing rows of the 15 snapshot bodies: NOW against all.json (prod, 2 Oct 17:33)")
    from app.database import Base
    pk_cols = {t.name: [c.name for c in t.primary_key.columns] for t in Base.metadata.tables.values()}
    if now_doc is None:
        say("   (no fresh export: skipped)")
        diff, counts = {}, {"skipped": 1}
    else:
        diff = snapshot_diff(base_doc, now_doc, pk_cols)
        counts = render_diff(diff, base_doc, now_doc, say)
    (out / "snapshot_diff.json").write_text(json.dumps(diff, indent=1, default=str), encoding="utf-8")

    # ---- (a2) masters + drafts per body -------------------------------------------------------------------------
    masters = q(conn, """select b.id, b.trailer_type_id, m.name, coalesce(g.name, b.body_option_group) as grp,
                                b.body_option_subgroup as sub, b.variable_value, b.body_option_default
                           from bill_of_materials b left join materials m on m.id = b.material_id
                           left join body_option_groups g on g.id = b.body_option_group_id
                          where b.is_body_option and b.trailer_type_id = any(:ids) order by b.id""", ids=ids)
    by_body = defaultdict(list)
    for m in masters:
        by_body[m["trailer_type_id"]].append(m)
    drafts = {r["trailer_type_id"]: r for r in q(
        conn, "select trailer_type_id, payload, updated_at from configurator_drafts where trailer_type_id = any(:ids)",
        ids=ids)}
    backups = defaultdict(list)
    for r in q(conn, """select id, trailer_type_id, label, created_at, payload from configurator_draft_snapshots
                        where trailer_type_id = any(:ids) order by trailer_type_id, created_at, id""", ids=ids):
        backups[r["trailer_type_id"]].append(r)
    base_saved = parse_door_report((stage / "door_report_20261003.txt").read_text(encoding="utf-8"))
    snap_masters = {(r["trailer_type_id"], r["id"]) for r in base_doc["tables"]["bill_of_materials"] if r.get("is_body_option")}
    mat_names = {m["id"]: m.get("name") for m in base_doc["tables"].get("materials", [])}
    gone_masters = {r["id"]: (r["trailer_type_id"], mat_names.get(r["material_id"]))
                    for r in base_doc["tables"]["bill_of_materials"]
                    if r.get("is_body_option") and r["trailer_type_id"] in snap_ids}
    say("\n== (a2) per chiller / freezer body: its drafts and its insulation masters")
    burt_ok, draft_changed, doc_bodies, burt_read = True, [], {}, []
    for b in scope:
        tid = b["id"]
        ms = by_body.get(tid, [])
        d = drafts.get(tid)
        payload = parse_payload(d["payload"]) if d else {}
        nodes = payload.get("nodes") or {}
        saved = d["updated_at"].strftime("%Y-%m-%d %H:%M") if d and d["updated_at"] else "-"
        then = base_saved.get(tid)
        if not d:
            state = "NO DRAFT"
        elif then is None:
            state = f"saved {saved} (no 3 Oct record for this body)"
        elif saved > then:
            state = f"SAVED SINCE 3 Oct: {then} -> {saved}"
            draft_changed.append(tid)
        else:
            state = f"unchanged since 3 Oct (saved {saved})"
        say(f"\n   #{tid} {b['name']} ({b['kind']}) · draft: {state} · {len(nodes)} nodes · backups {len(backups[tid])}")
        # the masters, now vs the snapshot
        now_ids = {m["id"] for m in ms}
        lost = [mid for (t, mid) in snap_masters if t == tid and mid not in now_ids]
        if tid in snap_ids:
            say(f"      masters: {len(ms)} now · " + (f"DELETED since 2 Oct: {sorted(lost)} "
                + str([gone_masters.get(x, (None, '?'))[1] for x in sorted(lost)]) if lost else "none deleted since 2 Oct"))
        offered = defaultdict(set)
        rows_txt = []
        for m in ms:
            mm = INS_RE.match(norm(m["name"]))
            if not mm:
                continue
            refs = refs_to_master(nodes, m)
            if refs:
                offered[mm.group(1)].add(mm.group(2))
            rows_txt.append(f"      {m['id']:>6} {m['name']:<10} T={m['variable_value']!s:<6} default={m['body_option_default']!s:<5} "
                            + (f"offered by {len(refs)} node(s): {refs[0]}" if refs else "NOT offered by any draft node"))
        say("      insulation masters (name · thickness · default · offered by the draft):")
        for t in rows_txt:
            say(t)
        stale = stale_bindings(nodes, now_ids)
        if stale:
            say(f"      draft flags bound to a master id that no longer exists on this body: {len(stale)}")
            for s in stale[:20]:
                say(f"         {s}")
        ok, txt = burt_check(b["kind"], offered) if d else (None, "no draft: not read (the click-through decides)")
        burt_read.append((tid, ok))
        if ok is False:
            burt_ok = False
        say(f"      Burt's ruling, read from the draft: {txt}")
        # the draft against its backups
        diffs = []
        cur_sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        for s in backups[tid][-8:]:
            sp = parse_payload(s["payload"])
            ssha = hashlib.sha256(json.dumps(sp, sort_keys=True).encode()).hexdigest()[:12]
            nd = node_diff(sp, payload)
            say(f"      backup #{s['id']} '{s['label']}' {s['created_at']:%Y-%m-%d %H:%M} · {len(sp.get('nodes') or {})} nodes · "
                + ("IDENTICAL to the draft now" if ssha == cur_sha else
                   f"since then: {len(nd['removed'])} removed, {len(nd['added'])} added, {len(nd['changed'])} changed"))
            diffs.append((s, nd))
        # the full node diff against the newest backup taken before the draft's last save
        before = [x for x in diffs if d and d["updated_at"] and x[0]["created_at"] <= d["updated_at"]]
        if before:
            s, nd = before[-1]
            say(f"      the draft now vs backup #{s['id']} '{s['label']}' (newest before the last save):")
            for k in ("removed", "added", "changed"):
                for line in nd[k][:40]:
                    say(f"         {k.upper():<8} {line}")
                if len(nd[k]) > 40:
                    say(f"         … {len(nd[k]) - 40} more {k}")
        doc_bodies[tid] = {"name": b["name"], "kind": b["kind"], "draft_state": state, "offered": {k: sorted(v) for k, v in offered.items()},
                           "burt": txt, "masters_deleted_since_2oct": sorted(lost), "stale_bindings": stale,
                           "draft_sha": cur_sha}

    # ---- (a3) rules naming a master that is gone ----------------------------------------------------------------
    say("\n== (a3) every per-line rule on these bodies that names a master which is not on the body now")
    m_by_id = {m["id"]: m for m in masters}
    m_by_name = defaultdict(list)
    for m in masters:
        m_by_name[(m["trailer_type_id"], norm(m["name"]))].append(m)
    lines = q(conn, """select b.id, b.trailer_type_id, m.name as line, b.bom_section, b.bom_conditions
                         from bill_of_materials b left join materials m on m.id = b.material_id
                        where b.trailer_type_id = any(:ids) and b.bom_conditions is not null
                          and b.bom_conditions not in ('', '[]')""", ids=[b["id"] for b in scope])
    was_master = {(r["trailer_type_id"], norm(mat_names.get(r["material_id"])))
                  for r in base_doc["tables"]["bill_of_materials"] if r.get("is_body_option")}
    # the same check against the masters of 2 Oct: a condition that was already off then is not Michael's
    b_by_id = {r["id"]: {"id": r["id"], "trailer_type_id": r["trailer_type_id"], "name": mat_names.get(r["material_id"])}
               for r in base_doc["tables"]["bill_of_materials"] if r.get("is_body_option")}
    b_by_name = defaultdict(list)
    for m in b_by_id.values():
        b_by_name[(m["trailer_type_id"], norm(m["name"]))].append(m)
    dangling, flag_only, new_n = [], 0, 0
    for ln in sorted(lines, key=lambda x: (x["trailer_type_id"], x["id"])):
        mode, cs = cond_list(ln["bom_conditions"])
        for c in cs:
            if isinstance(c, dict):
                good, txt = check_condition(c, ln["trailer_type_id"], m_by_id, m_by_name, was_master)
                if good is None:
                    flag_only += 1
                elif not good:
                    old = ln["trailer_type_id"] in snap_ids and \
                        check_condition(c, ln["trailer_type_id"], b_by_id, b_by_name, was_master)[0] is False
                    new_n += 0 if old else 1
                    dangling.append(f"#{ln['trailer_type_id']} bom {ln['id']} '{ln['line']}' [{ln['bom_section']}] {mode}: {txt}"
                                    + ("   (already so on 2 Oct)" if old else ""))
    say(f"   {len(lines)} rule line(s) on {len(scope)} bodies · {len(dangling)} condition(s) naming a missing master, "
        f"{new_n} of them new since 2 Oct · {flag_only} on draft-only flags (never a master)")
    for x in dangling[:150]:
        say(f"   {x}")

    # ---- (b) Manifest A ----------------------------------------------------------------------------------------
    import yaml
    man = yaml.safe_load((stage / "manifest_a.yaml").read_text(encoding="utf-8"))
    per_body = defaultdict(list)
    for e in man["changes"]:
        per_body[e["body_id"]].append(e)
    cur = {r["id"]: r for r in q(conn, """select b.id, b.trailer_type_id, m.name as line, b.bom_section, b.bom_conditions
                                            from bill_of_materials b left join materials m on m.id = b.material_id
                                           where b.id = any(:ids)""", ids=[e["bom_id"] for e in man["changes"]])}
    allm = q(conn, """select b.id, b.trailer_type_id, m.name from bill_of_materials b
                        left join materials m on m.id = b.material_id
                       where b.is_body_option and b.trailer_type_id = any(:ids)""", ids=list(per_body))
    a_by_id = {m["id"]: m for m in allm}
    a_by_name = defaultdict(list)
    for m in allm:
        a_by_name[(m["trailer_type_id"], norm(m["name"]))].append(m)
    say("\n== (b) Manifest A's REAR FRAME & FLOOR PLATE rules (the 3 chillers and 3 freezers first, then the other 8)")
    order_ids = [t for t in SIX if t in per_body] + sorted(t for t in per_body if t not in SIX)
    b_verdict = {}
    for tid in order_ids:
        es = per_body[tid]
        name = es[0]["body"][0]
        as_written, changed_l, missing_l, cond_txt = 0, [], [], {}
        all_named = True
        for e in es:
            r = cur.get(e["bom_id"])
            if r is None or r["trailer_type_id"] != tid:
                missing_l.append(f"bom {e['bom_id']} '{e['line']}' is gone")
                continue
            mode, cs = cond_list(r["bom_conditions"])
            if mode == "include" and sorted(map(cond_key, cs)) == sorted(map(cond_key, e["new"])):
                as_written += 1
            else:
                changed_l.append(f"bom {e['bom_id']} '{e['line']}': now {mode} {short(r['bom_conditions'], 140)}")
            for c in cs:
                if isinstance(c, dict):
                    good, txt = check_condition(c, tid, a_by_id, a_by_name, was_master)
                    cond_txt[txt] = good is not False
                    all_named &= good is True
        say(f"\n   #{tid} {name}: {len(es)} lines · as written {as_written} · changed {len(changed_l)} · gone {len(missing_l)}")
        for t, good in cond_txt.items():
            say(f"      {'ok ' if good else '!! '} {t}")
        for x in changed_l + missing_l:
            say(f"      !! {x}")
        try:
            priced = price_rear_frame(db, tid)
            eng_ok = all(p["ok"] for p in priced)
            for p in priced:
                say(f"      engine: {p['text']}  {'OK' if p['ok'] else '!! FAIL'}")
        except Exception as ex:                                         # noqa: BLE001
            eng_ok = False
            say(f"      engine: !! could not price: {type(ex).__name__}: {ex}")
            (out / f"engine_{tid}.trace.txt").write_text(traceback.format_exc(), encoding="utf-8")
        ok = eng_ok and not missing_l
        b_verdict[tid] = {"name": name, "ok": ok, "every_condition_names_an_existing_master": all_named,
                          "as_written": as_written, "changed": changed_l, "gone": missing_l, "engine_ok": eng_ok}
        say(f"      VERDICT #{tid}: " + ("OK — the rule holds" if ok else "!! PROBLEM")
            + ("" if all_named else " (a condition names a master that is gone: it reads as not selected)"))

    # ---- verdicts -----------------------------------------------------------------------------------------------
    bom_touched = sum(v for k, v in counts.items() if k.startswith("bom_") or k == "bill_of_materials_changed")
    lost_all = {t: v["masters_deleted_since_2oct"] for t, v in doc_bodies.items() if v["masters_deleted_since_2oct"]}
    kind = ("DRAFT NODES ONLY" if draft_changed and not bom_touched else
            "BOM ROWS AS WELL" if bom_touched else "NOTHING CHANGED")
    verdict["a"] = (f"{kind} · drafts saved since 3 Oct on {len(draft_changed)} chiller/freezer bodies {draft_changed}"
                    + (f" · pricing rows changed {counts}" if bom_touched else " · no BOM row deleted, added or changed")
                    + (f" · other pricing rows changed {counts}" if counts and not bom_touched else "")
                    + (f" · masters deleted {lost_all}" if lost_all else "")
                    + (" · materials changed (see facts.txt)" if any(k.startswith("materials") for k in counts) else "")
                    + " · Burt's rulings read from the drafts: "
                    + (f"as ruled on {sum(1 for _, o in burt_read if o)} of {sum(1 for _, o in burt_read if o is not None)} "
                       f"bodies with a draft" if burt_ok else
                       f"!! NOT as ruled on {[t for t, o in burt_read if o is False]}")
                    + (f" ({[t for t, o in burt_read if o is None]} without a draft)" if any(o is None for _, o in burt_read) else ""))
    six = [t for t in SIX if t in b_verdict]
    verdict["b"] = ("; ".join(f"#{t} {'OK' if b_verdict[t]['ok'] else '!! PROBLEM'}"
                              + ("" if b_verdict[t]["every_condition_names_an_existing_master"] else " (names a gone master)")
                              for t in six)
                    + f" · other Manifest A bodies: {sum(1 for t in b_verdict if t not in SIX and b_verdict[t]['ok'])}"
                      f"/{sum(1 for t in b_verdict if t not in SIX)} OK")
    verdict["b_ok"] = all(v["ok"] for v in b_verdict.values())
    (out / "facts.json").write_text(json.dumps({"bodies": bodies, "per_body": doc_bodies, "dangling": dangling,
                                                 "manifest_a": b_verdict, "diff_counts": counts, "verdict": verdict},
                                                indent=1, default=str), encoding="utf-8")
    return verdict


# ---------------------------------------------------------------------------------------------------------------
# (d) cells
# ---------------------------------------------------------------------------------------------------------------
def cell_key(c: dict) -> tuple:
    return (c["scenario_id"], c.get("section_excel") or "", c.get("section_mes") or "")


def cell_sig(c: dict) -> tuple:
    r = lambda v: None if v is None else round(float(v), 2)     # noqa: E731
    return (c["status"], c.get("base_status"), r(c.get("excel_total")), r(c.get("mes_total")))


def compare_cells(page_cells: list, cli_cells: list) -> dict:
    p = {cell_key(c): c for c in page_cells}
    c = {cell_key(x): x for x in cli_cells}
    moved = [k for k in sorted(set(p) & set(c)) if cell_sig(p[k]) != cell_sig(c[k])]
    return {"identical": len(set(p) & set(c)) - len(moved), "moved": moved,
            "only_page": sorted(set(p) - set(c)), "only_cli": sorted(set(c) - set(p)), "p": p, "c": c}


def cells(conn, cli_dir: Path, base_id: int, out: Path, say) -> tuple[int, str]:
    row = q(conn, """select id, pack, started_at::text as started, finished_at::text as finished, status, environment,
                            db_name, accepted_list, golden_fingerprint, count_pass, count_flag, count_accepted,
                            count_expired, count_unverifiable, report_json_gz
                       from costing_audit_runs where id = :i""", i=base_id)
    if not row:
        say(f"   !! page run #{base_id} not found")
        return 2, f"no baseline: page run #{base_id} not found"
    b = row[0]
    say(f"baseline: page run #{b['id']} pack={b['pack']} {b['status']} started {b['started']} finished {b['finished']}")
    say(f"   stored counts PASS {b['count_pass']} FLAG {b['count_flag']} ACCEPTED {b['count_accepted']} "
        f"EXPIRED {b['count_expired']} UNVERIFIABLE {b['count_unverifiable']} · golden {(b['golden_fingerprint'] or '-')[:16]}")
    later = q(conn, """select id, pack, started_at::text as started, finished_at::text as finished, status, count_pass,
                              count_flag, count_accepted, count_unverifiable
                         from costing_audit_runs where id > :i order by id""", i=base_id)
    say(f"page runs after #{base_id}: {len(later)}")
    for r in later:
        say(f"   #{r['id']} {r['pack']:<9} {r['status']:<8} started {r['started']}  PASS {r['count_pass']} FLAG {r['count_flag']} "
            f"ACCEPTED {r['count_accepted']} UNVERIFIABLE {r['count_unverifiable']}")
    if b["pack"] != "all" or not b["report_json_gz"]:
        return 2, f"no baseline: page run #{base_id} is not a finished All run"
    page = json.loads(gzip.decompress(b["report_json_gz"]).decode("utf-8"))
    cli = []
    say("\nCLI now (the deployed code, --env prod), per pack:")
    for p in ALL_PACKS:
        f = cli_dir / f"prod_{p}.json"
        if not f.is_file():
            return 2, f"the CLI report {f.name} is missing"
        d = json.loads(f.read_text(encoding="utf-8"))
        cnt = Counter(x["status"] for x in d["cells"])
        say(f"   {p:<10} " + "  ".join(f"{s} {cnt[s]}" for s in STATUSES if cnt.get(s)) + f"  (cells {sum(cnt.values())})")
        cli.extend(d["cells"])
    pc = Counter(x["status"] for x in page["cells"])
    say(f"   page #{base_id}  " + "  ".join(f"{s} {pc[s]}" for s in STATUSES if pc.get(s)) + f"  (cells {len(page['cells'])})")
    r = compare_cells(page["cells"], cli)
    say(f"\ncells: baseline {len(r['p'])}, now {len(r['c'])}, identical {r['identical']}, MOVED {len(r['moved'])}, "
        f"only in the baseline {len(r['only_page'])}, only now {len(r['only_cli'])}")
    rows = []
    for k in r["moved"]:
        a, z = r["p"][k], r["c"][k]
        delta = None if a.get("mes_total") is None or z.get("mes_total") is None else round(float(z["mes_total"]) - float(a["mes_total"]), 2)
        rows.append({"scenario": k[0], "section": k[1] or k[2], "before": cell_sig(a), "now": cell_sig(z), "mes_delta": delta})
    for x in rows[:200]:
        say(f"   MOVED {x['scenario']} | {x['section']}: {x['before']} -> {x['now']}  (MES {x['mes_delta']:+,.2f})"
            if x["mes_delta"] is not None else f"   MOVED {x['scenario']} | {x['section']}: {x['before']} -> {x['now']}")
    for k in (r["only_page"] + r["only_cli"])[:60]:
        say(f"   ONLY {'baseline' if k in r['p'] else 'now     '} {k[0]} | {k[1] or k[2]}")
    (out / "cells_moved.json").write_text(json.dumps({"baseline_run": base_id, "moved": rows,
                                                      "only_baseline": r["only_page"], "only_now": r["only_cli"]},
                                                     indent=1, default=str), encoding="utf-8")
    n = len(r["moved"]) + len(r["only_page"]) + len(r["only_cli"])
    return (0 if n == 0 else 1), (f"no cell moved since page run #{base_id} ({r['identical']} identical)" if n == 0 else
                                  f"{len(r['moved'])} cell(s) moved, {len(r['only_page'])} only in the baseline, "
                                  f"{len(r['only_cli'])} only now — listed in cells.txt")


# ---------------------------------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    out = Path(argv[1])
    lines: list[str] = []

    def say(s=""):
        lines.append(s)
        print(s, flush=True)

    if cmd == "facts":
        stage = Path(argv[2])
        from tools.costing_audit.mes_snapshot import export_snapshot
        base_doc = json.loads((stage / "all.json").read_text(encoding="utf-8"))
        now_path = out / "now_snapshot.json"
        export_snapshot([int(x) for x in base_doc["trailer_ids"]], now_path, log=lambda s: say(f"   {s}"))
        now_doc = json.loads(now_path.read_text(encoding="utf-8"))
        eng, conn = open_ro()
        from sqlalchemy.orm import Session
        db = Session(bind=conn, autoflush=False)
        try:
            v = facts(conn, db, stage, out, now_doc, say)
        finally:
            db.rollback()
            db.close()
            conn.rollback()
            conn.close()
            eng.dispose()
        (out / "facts.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (out / "verdicts.txt").write_text(f"a: {v['a']}\nb: {v['b']}\n", encoding="utf-8")
        return 0
    if cmd == "cells":
        cli_dir, base_id = Path(argv[2]), int(argv[3])
        eng, conn = open_ro()
        try:
            rc, txt = cells(conn, cli_dir, base_id, out, say)
        finally:
            conn.rollback()
            conn.close()
            eng.dispose()
        (out / "cells.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with (out / "verdicts.txt").open("a", encoding="utf-8") as f:
            f.write(f"d: {txt}\n")
        return rc
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
