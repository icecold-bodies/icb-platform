"""v1.58.1 SRD rear-frame discovery (dispatch 6 §3.0 + BA ruling 6a). READ ONLY.

Every database read runs in a read-only session (psycopg: default_transaction_read_only;
the engine re-price: a NullPool engine with default_transaction_read_only + SET TRANSACTION
READ ONLY, always rolled back). Prints pricing/config data and quote numbers only: no
customer, contact, end-user, user or person column is selected.

  A. scope: active bodies with a REAR FRAME% line; the lane's scope (v2, an SRD master,
     not RHINORANGE); the classic (non-v2) bodies that are active and offer SRD
  B. Trailer Designer picker scope: the REAR FRAME category per in-scope body, then a generic
     sweep over EVERY saved item rule on every drafted v2 body (rules whose options the editor
     cannot offer = exposed to the replace-on-save defect)
  C. saved quotes: each saved v2 non-repair costing on an in-scope body, re-priced in-process
     by the engine twice (today's data as-is, and with the proposed REAR FRAME rule applied
     IN MEMORY to the rows) -> REAR FRAME total with / without. Preceded by a known-hit
     self-test (SRD PU on -> RF 0; nothing on -> RF unchanged).
  D. Part B lines 5851 / 6159 / 5585 and each MEAT HANGER's SRD masters

Usage (PYTHONPATH must reach the app's backend/, DATABASE_URL must be set for app.database):
    python srd_discovery.py <DATABASE_URL>
"""
import collections
import json
import sys

import psycopg

SRD_NAMES = ("SRD EPS", "SRD PU", "SRD")
OUT_OF_LANE = ("RHINORANGE",)   # BA ruling 6a §4: SRD master present but not offered in its draft


def norm(v):
    return str(v or "").strip().upper()


# ---------------------------------------------------------------- editor scope (JS port)
def resolve_flag_binding(node, body_options):
    """resolveFlagBinding (admin_visual_configurator_settings.html:1288)."""
    if not node or node.get("type") != "flag":
        return ""
    if node.get("flagBindingName"):
        return node["flagBindingName"]
    label = norm(node.get("label"))
    if not label:
        return ""
    matches = [o for o in body_options
               if norm(o) == label or label in norm(o) or norm(o) in label]
    return matches[0] if len(matches) == 1 else ""


def scoped_options(draft, cat_id, body_options):
    """collectScopedRuleOptions (admin_visual_configurator_settings.html:1416)."""
    nodes = draft.get("nodes") or {}
    node = nodes.get(cat_id)
    if not node or node.get("type") != "category":
        return []
    folder_path = []
    pid = node.get("parentId")
    while pid:
        parent = nodes.get(pid)
        if not parent:
            break
        if parent.get("type") == "folder":
            folder_path.insert(0, parent.get("id"))  # JS: parent.id (undefined -> skipped by walk)
        pid = parent.get("parentId")
    seen, out = set(), []

    def add(child, scope):
        if not child or child.get("type") not in ("flag", "condition"):
            return
        val = (resolve_flag_binding(child, body_options) or child.get("label")) \
            if child["type"] == "flag" else child.get("label")
        k = norm(val)
        if not k or k in seen:
            return
        seen.add(k)
        out.append((val, child["type"], scope))

    def walk(fid, scope):
        f = nodes.get(fid)
        if not f:
            return
        for cid in f.get("childIds") or []:
            c = nodes.get(cid)
            if not c:
                continue
            if c.get("type") == "folder":
                walk(c.get("id"), scope)  # JS: child.id; a node without id walks nothing
            elif c.get("type") == "category":
                for g in c.get("childIds") or []:
                    add(nodes.get(g), f"{scope} > {c.get('label')}")
            else:
                add(c, scope)

    for cid in draft.get("rootIds") or []:
        c = nodes.get(cid)
        if c and c.get("type") == "category":
            for g in c.get("childIds") or []:
                add(nodes.get(g), c.get("label"))
        else:
            add(c, "Root")
    for fid in folder_path:
        walk(fid, (nodes.get(fid) or {}).get("label") or "Folder")
    for cid in node.get("childIds") or []:
        add(nodes.get(cid), node.get("label"))
    return out


def used_category_map(draft):
    """buildUsedCategoryMap: sourceCategoryKey -> node id (the LAST node wins, like JS)."""
    out = {}
    for n in (draft.get("nodes") or {}).values():
        if n.get("type") == "category" and n.get("sourceCategoryKey"):
            out[n["sourceCategoryKey"]] = n["id"]
    return out


def parse_rule(raw):
    """-> (mode, [option names]) exactly as the categories endpoint reads bom_conditions."""
    if not raw:
        return "include", []
    try:
        p = json.loads(raw)
    except (ValueError, TypeError):
        return "include", []
    if isinstance(p, list):
        return "include", [str(c.get("option")) for c in p if isinstance(c, dict) and c.get("option")]
    if isinstance(p, dict):
        mode = (p.get("mode") or "include").lower()
        return mode, [str(c.get("option")) for c in (p.get("all") or []) if isinstance(c, dict) and c.get("option")]
    return "include", []


def rule_json(masters_for_body):
    """The proposed REAR FRAME rule for one body, in the endpoint's stored shape
    (trailers.py:3790-3800: include + non-empty -> json.dumps(list of {option, equals, option_id}))."""
    by_name = {}
    for mid, nm, *_ in masters_for_body:
        by_name.setdefault(nm, mid)
    door_type_srd = next((mid for mid, nm, grp, *_ in masters_for_body
                          if nm == "SRD" and norm(grp) == "DOOR TYPE"), None)
    if door_type_srd is not None:
        # A body with a DOOR TYPE selector (CHILLER LARGE) picks the door THERE and keeps the
        # SRD insulation flag ticked on double-door quotes (dev: A32795 / A32817 carry
        # SRD EPS = true with DRD) — the EPS/PU pair would zero REAR FRAME on a DRD quote.
        return json.dumps([{"option": "SRD", "equals": "N", "option_id": door_type_srd}])
    names = [n for n in ("SRD EPS", "SRD PU") if n in by_name] or (["SRD"] if "SRD" in by_name else [])
    if not names:
        return None
    return json.dumps([{"option": n, "equals": "N", "option_id": by_name[n]} for n in names])


# ---------------------------------------------------------------- main
def main(url):
    url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("show default_transaction_read_only")
        print("read_only session:", cur.fetchone()[0])

        cur.execute("""
            SELECT t.id, t.name, t.configurator_v2, s.id, s.name, count(b.id),
                   count(b.id) FILTER (WHERE b.bom_conditions IS NOT NULL
                                         AND b.bom_conditions NOT IN ('null','[]','')),
                   string_agg(DISTINCT coalesce(b.selection_mode,'<null>'), ','),
                   array_agg(b.id ORDER BY b.id)
              FROM trailer_types t
              JOIN bill_of_materials b ON b.trailer_type_id = t.id
              JOIN bom_sections s ON s.id = b.bom_section_id
             WHERE t.is_active AND s.name ILIKE 'REAR FRAME%%'
             GROUP BY t.id, t.name, t.configurator_v2, s.id, s.name
             ORDER BY t.name, s.id""")
        rf_rows = cur.fetchall()
        cur.execute("""
            SELECT m.trailer_type_id, m.id, mt.name, coalesce(g.name, m.body_option_group, '?'),
                   m.variable_value, m.body_option_default
              FROM bill_of_materials m
              JOIN materials mt ON mt.id = m.material_id
              LEFT JOIN body_option_groups g ON g.id = m.body_option_group_id
             WHERE m.is_body_option ORDER BY m.id""")
        masters = collections.defaultdict(list)
        for tid, mid, name, grp, var, dflt in cur.fetchall():
            masters[tid].append((mid, (name or "").strip(), grp, var, dflt))

        def srd_of(tid):
            return [nm for _, nm, *_ in masters[tid] if nm in SRD_NAMES]

        # ---- A. scope
        print("\n=== A. SCOPE SWEEP (active bodies with a REAR FRAME% line)")
        scope = {}          # tid -> (name, [rf bom ids], rule json)
        classic_srd = []
        for tid, tname, v2, sid, sname, n, ncond, modes, ids in rf_rows:
            door = [f"{m}:{nm}[{g}]" for m, nm, g, _, _ in masters[tid]
                    if g in ("DRD", "SRD", "DOOR TYPE") or "SRD" in nm or "DRD" in nm]
            srd = srd_of(tid)
            if not v2:
                verdict = "OUT (classic: engine ignores bom_conditions)"
                if srd:
                    classic_srd.append((tid, tname, srd))
            elif not srd:
                verdict = "OUT (no SRD master)"
            elif any(norm(tname).startswith(x) for x in OUT_OF_LANE):
                verdict = "OUT (BA 6a §4: SRD not offered in its draft)"
            else:
                verdict = "IN"
                scope[tid] = (tname, list(ids), rule_json(masters[tid]))
            print(f"{tid:>4} | {tname:<28} | v2={'Y' if v2 else 'N'} | sec {sid} {sname} | "
                  f"lines={n} with_cond={ncond} modes={modes} | SRD masters={srd or '-'} | {verdict}")
            print(f"       door masters: {' '.join(door) or '-'}")
            print(f"       rear-frame bom ids: {','.join(map(str, ids))}")
        cur.execute("""SELECT s.id, s.name, count(b.id) FROM bom_sections s
                       LEFT JOIN bill_of_materials b ON b.bom_section_id = s.id
                       WHERE s.name ILIKE 'REAR FRAME%%' GROUP BY s.id, s.name ORDER BY s.id""")
        print("REAR FRAME% sections (all bodies incl. inactive):", cur.fetchall())
        print(f"\nLANE SCOPE: {len(scope)} bodies, {sum(len(v[1]) for v in scope.values())} REAR FRAME lines")
        for tid, (tname, ids, rj) in sorted(scope.items(), key=lambda kv: kv[1][0]):
            print(f"   {tid:>4} {tname:<28} {len(ids)} lines  rule={rj}")
        print("ACTIVE CLASSIC BODIES THAT OFFER SRD (-> BA separate item):",
              classic_srd or "none")

        # ---- B. picker scope + generic sweep
        print("\n=== B. PICKER SCOPE (Trailer Designer rule editor)")
        cur.execute("SELECT trailer_type_id, payload, updated_at FROM configurator_drafts")
        drafts = {}
        for tid, payload, upd in cur.fetchall():
            drafts[tid] = (json.loads(payload) if isinstance(payload, str) else payload, upd)

        def body_opts(tid):
            out, seen = [], set()
            for _, nm, *_ in masters[tid]:
                if nm and norm(nm) not in seen:
                    seen.add(norm(nm))
                    out.append(nm)
            return out

        print("-- B1. REAR FRAME category, in-scope bodies")
        for tid, (tname, ids, rj) in sorted(scope.items(), key=lambda kv: kv[1][0]):
            d = drafts.get(tid)
            if not d:
                print(f"{tid:>4} | {tname:<28} | NO SERVER DRAFT (editor problem does not apply)")
                continue
            draft, upd = d
            sec_names = {sname for t2, _, _, _, sname, *_ in rf_rows if t2 == tid}
            ucm = used_category_map(draft)
            for sname in sorted(sec_names):
                cat = ucm.get(norm(sname))
                if not cat:
                    print(f"{tid:>4} | {tname:<28} | draft {upd:%Y-%m-%d} | {sname}: category NOT IN DRAFT")
                    continue
                vals = {v for v, _, _ in scoped_options(draft, cat, body_opts(tid))}
                want = [n for n in SRD_NAMES if n in srd_of(tid)]
                print(f"{tid:>4} | {tname:<28} | draft {upd:%Y-%m-%d} | "
                      f"{ {n: ('IN SCOPE' if n in vals else 'OUT') for n in want} } | offered: {sorted(vals)}")

        print("-- B2. SWEEP: every saved item rule on every drafted v2 body")
        cur.execute("""SELECT b.id, b.trailer_type_id, coalesce(b.bom_section, s.name), b.bom_conditions
                         FROM bill_of_materials b
                         JOIN trailer_types t ON t.id = b.trailer_type_id
                         LEFT JOIN bom_sections s ON s.id = b.bom_section_id
                        WHERE t.is_active AND t.configurator_v2 AND NOT b.is_body_option
                          AND b.bom_conditions IS NOT NULL AND b.bom_conditions NOT IN ('null','[]','')""")
        per_body = collections.Counter()
        tot = collections.Counter()
        examples = collections.defaultdict(list)
        cache = {}
        for bid, tid, sname, raw in cur.fetchall():
            mode, opts = parse_rule(raw)
            if not opts:
                tot["rules without named conditions (always/always_exclude)"] += 1
                continue
            tot["rules with conditions"] += 1
            d = drafts.get(tid)
            if not d:
                tot["  on a body with no draft (not exposed)"] += 1
                continue
            draft = d[0]
            cat = used_category_map(draft).get(norm(sname))
            if not cat:
                tot["  category not in draft (editor keeps them: no options)"] += 1
                continue
            key = (tid, cat)
            if key not in cache:
                cache[key] = {v for v, _, _ in scoped_options(draft, cat, body_opts(tid))}
            vals = cache[key]
            if not vals:
                tot["  category offers no options (editor keeps them)"] += 1
                continue
            missing = [o for o in opts if o not in vals]
            if not missing:
                tot["  all conditions in scope (safe)"] += 1
            elif len(missing) == len(opts):
                tot["  ALL conditions out of scope -> REPLACED by options[0] on save"] += 1
                per_body[tid] += 1
                if len(examples[tid]) < 3:
                    examples[tid].append((bid, sname, missing))
            else:
                tot["  SOME conditions out of scope -> those DROPPED on save"] += 1
                per_body[tid] += 1
                if len(examples[tid]) < 3:
                    examples[tid].append((bid, sname, missing))
        for k, v in tot.items():
            print(f"   {k}: {v}")
        cur.execute("SELECT id, name FROM trailer_types")
        tnames = dict(cur.fetchall())
        for tid, n in per_body.most_common():
            print(f"   exposed on {tid} {tnames.get(tid)}: {n}  e.g. {examples[tid]}")

        # ---- D. Part B (psycopg, before C so it prints even if C fails)
        print("\n=== D. PART B lines + MEAT HANGER SRD masters")
        cur.execute("""
            SELECT b.id, t.name, b.bom_section, m.id, m.name, m.price_per_unit, b.unit_price_override,
                   b.formula_expression, b.bom_conditions, b.source_cell
              FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
              JOIN materials m ON m.id = b.material_id
             WHERE b.id IN (5851, 6159, 5585) ORDER BY b.id""")
        for row in cur.fetchall():
            print(" | ".join(str(x) for x in row))
        cur.execute("SELECT id, name, configurator_v2 FROM trailer_types WHERE name ILIKE 'MEAT HANGER%%'")
        for tid, tname, v2 in cur.fetchall():
            print(f"{tid} {tname} v2={v2}:",
                  [(mid, nm, g, var, dflt) for mid, nm, g, var, dflt in masters[tid] if nm in SRD_NAMES])
        # material ids differ dev <-> prod: key off line 5585's material (the global SRD PU)
        cur.execute("""SELECT b.id, b.trailer_type_id, t.is_active FROM bill_of_materials b
                         JOIN trailer_types t ON t.id = b.trailer_type_id
                        WHERE b.material_id = (SELECT material_id FROM bill_of_materials WHERE id = 5585)
                          AND b.unit_price_override IS NULL AND t.is_active ORDER BY b.id""")
        print("ACTIVE lines on 5585's material with no own price (id, trailer, active):", cur.fetchall())

        cur.execute("SELECT id, trailer_type_id, quote_number, created_at::date, result_json, dimensions_json "
                    "FROM calculations WHERE deleted_at IS NULL AND coalesce(is_repair, false) = false "
                    "AND trailer_type_id = ANY(%s) ORDER BY id", (list(scope),))
        saved = cur.fetchall()

    requote(scope, masters, saved)


# ---------------------------------------------------------------- C. engine re-price
class _RuleRow:
    """A read-only stand-in for a BillOfMaterial row whose bom_conditions is replaced IN
    MEMORY by the proposed rule. Nothing is assigned on the ORM object, so nothing can flush."""
    __slots__ = ("_row", "bom_conditions")

    def __init__(self, row, cond):
        object.__setattr__(self, "_row", row)
        object.__setattr__(self, "bom_conditions", cond)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_row"), name)


def requote(scope, masters, saved):
    print("\n=== C. SAVED QUOTES re-priced by the engine: REAR FRAME with / without the rule")
    from sqlalchemy import create_engine, text, event
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool
    import app.database as _db
    from app.database import TrailerType, BillOfMaterial
    from app.routers.calculator import (_bom_load_options, _build_bom_items, _build_body_variables,
                                        _apply_body_variable_overrides)
    from app.services import get_formula_lib, get_global_vars, get_section_snapshot
    from app.services import insulation_foam as pu_foam
    from app.formula_engine import calculate_bom

    eng = create_engine(_db.engine.url, poolclass=NullPool,
                        connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    db = Session(bind=conn, autoflush=False)
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        print("engine session read only:", db.execute(text("show transaction_read_only")).scalar())
        order = get_section_snapshot().order
        cache = {}

        def load(tid):
            if tid not in cache:
                tt = db.query(TrailerType).filter_by(id=tid).first()
                rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=tid)
                        .options(*_bom_load_options()).all())
                rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                                         r.material.name.lower() if r.material else ""))
                cache[tid] = (tt, rows)
            return cache[tid]

        def price(tid, dims, st, body_vars_saved, with_rule):
            tt, rows = load(tid)
            rf_ids = set(scope[tid][1])
            rj = scope[tid][2]
            use = [(_RuleRow(r, rj) if (with_rule and r.id in rf_ids) else r) for r in rows]
            items = _build_bom_items(
                use, dims, st.get("overrides") or {},
                {str(k): bool(v) for k, v in (st.get("body_option_selections") or {}).items()}, db,
                st.get("excluded_categories") or [], trailer=tt,
                flag_overrides={str(k): bool(v) for k, v in (st.get("flag_overrides") or {}).items()},
                include_all_items=False, user_excluded_bom_ids=st.get("user_excluded_bom_ids") or [],
                optional_sections_enabled=st.get("optional_sections_enabled") or [],
                formula_overrides=None, insulation_foam=pu_foam.normalise(st.get("insulation_foam")))
            bv = _build_body_variables(rows)
            _apply_body_variable_overrides(bv, body_vars_saved or {})
            res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
            rf = [it for it in res["items"] if int(it.get("bom_id") or 0) in rf_ids]
            return (round(sum(float(it.get("line_cost") or 0) for it in rf), 2),
                    sum(1 for it in rf if it.get("excluded")), round(float(res.get("grand_total") or 0), 2))

        # known-hit self-test on the first in-scope body (by id) with an SRD PU (or SRD) master
        st_tid = next(iter(sorted(scope)), None)
        if st_tid is not None:
            ms = {nm: mid for mid, nm, *_ in masters[st_tid]}
            srd_id = ms.get("SRD PU") or ms.get("SRD")
            tt, _ = load(st_tid)
            dims = {"length": tt.default_length or 4.0, "width": tt.default_width or 2.4,
                    "height": tt.default_height or 2.2}
            on = {"body_option_selections": {str(srd_id): True}, "flag_overrides": {}}
            off = {"body_option_selections": {}, "flag_overrides": {}}
            a0, _, _ = price(st_tid, dims, off, {}, False)
            a1, x1, _ = price(st_tid, dims, off, {}, True)
            b0, _, _ = price(st_tid, dims, on, {}, False)
            b1, x2, _ = price(st_tid, dims, on, {}, True)
            ok = a0 == a1 and x1 == 0 and b0 > 0 and b1 == 0 and x2 == len(scope[st_tid][1])
            print(f"SELF-TEST on {st_tid} {scope[st_tid][0]}: SRD off RF {a0} -> {a1} (excluded {x1}); "
                  f"SRD on RF {b0} -> {b1} (excluded {x2}/{len(scope[st_tid][1])})  => {'PASS' if ok else 'FAIL'}")
            if not ok:
                raise SystemExit("self-test FAILED — the check cannot be trusted; send the CA this output")

        stats = collections.Counter()
        print("quote | body | saved | door | RF saved | RF no-rule | RF rule | excl | verdict")
        for cid, tid, qn, day, rj, dj in saved:
            try:
                r = json.loads(rj or "{}")
                st = r.get("input_state") or {}
                if isinstance(st, str):
                    st = json.loads(st)
                dims = json.loads(dj) if dj else {}
            except Exception:
                stats["unparseable"] += 1
                print(f"{qn} | {scope[tid][0]} | {day} | unparseable")
                continue
            if not st or not dims:
                stats["no input_state/dims (pre-v1.39.9)"] += 1
                print(f"{qn} | {scope[tid][0]} | {day} | no input_state — skipped")
                continue
            items = r.get("items") or []
            secs = {norm(it.get("category") or it.get("category_name")) for it in items
                    if not it.get("excluded")}
            drd = bool(secs & {"DRD DOOR FITTINGS", "DOOR FITTINGS DRD", "DRD"})
            srd = bool(secs & {"SRD DOOR FITTINGS", "DOOR FITTINGS SRD", "SRD"})
            door = "BOTH" if drd and srd else "DRD" if drd else "SRD" if srd else "NONE"
            rf_ids = set(scope[tid][1])
            rf_saved = round(sum(float(it.get("line_cost") or 0) for it in items
                                 if int(it.get("bom_id") or 0) in rf_ids), 2)
            try:
                n0, _, _ = price(tid, dims, st, r.get("body_variables"), False)
                n1, x, _ = price(tid, dims, st, r.get("body_variables"), True)
            except Exception as e:  # report, never abort the sweep
                stats["engine error"] += 1
                print(f"{qn} | {scope[tid][0]} | {day} | {door} | engine error {type(e).__name__}: {str(e)[:120]}")
                continue
            if door == "DRD":
                verdict = "OK (unchanged)" if n0 == n1 else "!! DRD CHANGED"
            elif door == "SRD":
                verdict = "OK (SRD loses RF)" if n1 == 0 and n0 > 0 else (
                    "rule does not fire (no SRD master sent)" if n0 == n1 else "!! SRD partial")
            else:
                verdict = "unchanged" if n0 == n1 else "!! changed (door unknown)"
            stats[(door, verdict)] += 1
            print(f"{qn} | {scope[tid][0]} | {day} | {door} | {rf_saved} | {n0} | {n1} | {x} | {verdict}")
        print("SUMMARY:", dict(stats))
        print("(expected: every DRD 'OK (unchanged)'; SRD 'OK (SRD loses RF)'; any '!!' = STOP)")
    finally:
        db.rollback()
        db.close()
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1])
