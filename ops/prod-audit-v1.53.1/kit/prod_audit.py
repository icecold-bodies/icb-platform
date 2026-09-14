#!/usr/bin/env python3
"""v1.53.1 prod audit: master-bound draft-flag shadowing (PR #181 → fixed by #186).

READ-ONLY BY CONSTRUCTION
  * PGOPTIONS=-c default_transaction_read_only=on is forced before any DB import.
  * Every pooled connection also runs SET SESSION CHARACTERISTICS AS TRANSACTION
    READ ONLY. The script aborts unless SHOW transaction_read_only reports "on".
  * No data-modifying statement exists in this script. The only COMMITs end
    the connection-setup transactions that hold the read-only SETs; every
    audit session is rolled back and closed.
  * Output goes only to --out (a directory the caller owns). The script never
    writes to the repo, the DB, or any other path.

Runs with the app's own code and DATABASE_URL, from backend/ (the wrapper
audit.sh sources /etc/icb/backend.env). The identical script runs on dev:
    cd backend && python <kit>/prod_audit.py --out <dir>

Sections
  A  context: database, read-only proof, timezone, alembic head, counts
  B  exposure census: per trailer with a configurator draft
  C  EPS/PU pair invariant (both sides > 0) on exposed trailers
  D  saved costings on exposed trailers: per-name shadow classification,
     bug-window scan, snapshot-less possible shadows
  E  validated references touching the window or a flagged costing
  F  impact recompute for SHADOW costings: saved-run vs corrected-run
  G  deploy readiness for 94ed70b: stale bindings on v2 bodies, whitespace
     drift, flagVarDefault on master names, Manni (masterless) sanity
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime

# ── read-only guard #1: before anything can open a libpq connection ────────
os.environ["PGOPTIONS"] = (os.environ.get("PGOPTIONS", "") + " -c default_transaction_read_only=on").strip()

HERE = os.path.dirname(os.path.abspath(__file__))

# Timeline (SAST = UTC+2). calculations.created_at is a naive timestamp; the
# windows below are chosen so they are conservative under BOTH readings
# (naive-as-UTC and naive-as-SAST): each starts at the earlier of the two.
W178 = "2026-09-07 14:00:00"   # e9dd6da (#176-#178 draft-flag thickness) live 7 Sep 16:42 SAST = 14:42 UTC
W181 = "2026-09-08 07:00:00"   # e5c7837 (#181 explicit-zero) checked out 8 Sep 09:35 SAST = 07:35 UTC
EPS_TOL = 1e-9


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Report:
    def __init__(self, out_dir: str):
        self.out = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self._txt = open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8")
        self.summary: list[str] = []
        self.data: dict = {}

    def h(self, title: str):
        self.p("")
        self.p("=" * 78)
        self.p(title)
        self.p("=" * 78)

    def p(self, line: str = ""):
        print(line, flush=True)
        self._txt.write(line + "\n")

    def s(self, line: str):
        self.summary.append(line)

    def csv(self, name: str, rows: list[dict], fields: list[str] | None = None):
        path = os.path.join(self.out, name)
        fields = fields or (sorted({k for r in rows for k in r}) if rows else ["(none)"])
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})

    def close(self):
        with open(os.path.join(self.out, "SUMMARY.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(self.summary) + "\n")
        with open(os.path.join(self.out, "audit.json"), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, default=str)
        self._txt.close()


def _up(s) -> str:
    return str(s or "").strip().upper()


def _loads(raw):
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-recompute", type=int, default=400)
    args = ap.parse_args()

    rep = Report(args.out)
    rep.s(f"v1.53.1 master-bound flag-shadow PROD AUDIT — run {_now()} (read-only)")

    backend_dir = os.getcwd()
    if not os.path.isdir(os.path.join(backend_dir, "app")):
        rep.p(f"FATAL: run from the backend/ directory (cwd={backend_dir})")
        rep.close()
        return 2
    sys.path.insert(0, backend_dir)

    from sqlalchemy import event, text
    from app import database as dbm

    # ── read-only guard #2: every pooled connection ─────────────────────────
    # The app's own connect listener (SET search_path) has already opened a
    # transaction, so the SET below must be COMMITTED or the first rollback
    # would undo it. Those commits end transactions that contain only SET
    # statements; no data-modifying statement exists anywhere in this script.
    @event.listens_for(dbm.engine, "connect")
    def _ro(dbapi_conn, _rec):   # noqa: ANN001
        cur = dbapi_conn.cursor()
        try:
            cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            dbapi_conn.commit()
            cur.execute("SHOW default_transaction_read_only")
            val = cur.fetchone()[0]
            dbapi_conn.commit()
        finally:
            cur.close()
        if val != "on":
            raise RuntimeError("database connection is not read-only - refusing to continue")

    db = dbm.SessionLocal()
    try:
        return _run(rep, db, text, dbm, args)
    except Exception:
        rep.p("FATAL: " + traceback.format_exc())
        rep.s("AUDIT ABORTED — see report.txt")
        return 1
    finally:
        try:
            db.rollback()
        finally:
            db.close()
            rep.close()


def _run(rep: Report, db, text, dbm, args) -> int:
    q = lambda sql, **kw: db.execute(text(sql), kw).mappings().all()   # noqa: E731

    # ── A. context + read-only proof ───────────────────────────────────────
    rep.h("A. CONTEXT")
    ctx = q("SELECT current_database() AS db, current_user AS usr, "
            "current_setting('transaction_read_only') AS ro, "
            "current_setting('default_transaction_read_only') AS default_ro, "
            "current_setting('TimeZone') AS tz, now()::text AS now")[0]
    for k, v in ctx.items():
        rep.p(f"  {k:12} {v}")
    if ctx["ro"] != "on" or ctx["default_ro"] != "on":
        rep.p("FATAL: transaction_read_only is not 'on' — refusing to continue.")
        rep.s("AUDIT ABORTED: session was not read-only")
        return 3
    rep.s(f"database={ctx['db']}  read_only={ctx['ro']}  tz={ctx['tz']}  db_now={ctx['now']}")
    try:
        alembic = q("SELECT version_num FROM alembic_version")
        rep.p(f"  alembic      {[r['version_num'] for r in alembic]}")
        rep.s(f"alembic={[r['version_num'] for r in alembic]}")
    except Exception as e:   # different schema on some hosts — informational only
        db.rollback()
        rep.p(f"  alembic      (not readable: {e.__class__.__name__})")
    rep.data["context"] = dict(ctx)

    trailers = {r["id"]: dict(r) for r in q(
        "SELECT id, name, is_active, configurator_v2 FROM trailer_types ORDER BY id")}
    bom = q("""SELECT b.id, b.trailer_type_id AS tid, m.name AS mname, b.is_body_option,
                      b.variable_value, b.body_option_group AS grp, b.body_option_subgroup AS sub,
                      b.formula_expression AS formula, b.sort_order, b.bom_section, mc.name AS catname
               FROM bill_of_materials b
               LEFT JOIN materials m ON m.id = b.material_id
               LEFT JOIN material_categories mc ON mc.id = m.category_id""")
    section_order = {r["name"]: r["sort_order"] for r in q("SELECT name, sort_order FROM bom_sections")}
    drafts = q("SELECT trailer_type_id AS tid, payload, updated_at FROM configurator_drafts ORDER BY trailer_type_id")
    rep.p(f"  trailers={len(trailers)} bom_rows={len(bom)} drafts={len(drafts)}")

    import re
    tok_re = re.compile(r"\{([^{}]+)\}")
    rows_by_id = {r["id"]: r for r in bom}
    by_tid: dict[int, list] = defaultdict(list)
    for r in bom:
        by_tid[r["tid"]].append(r)
    # Position of each row in the approve path's order. _build_body_variables
    # overwrites by name, so for duplicate-named masters the engine's template
    # is the LAST one in this order.
    approve_pos: dict[int, int] = {}
    for tid_rows in by_tid.values():
        ordered = sorted(tid_rows, key=lambda r: (r["sort_order"] is None, r["sort_order"] or 0, r["id"]))

        def _sec_key(r):
            name = r["bom_section"] or (r["catname"] or "")
            return (section_order.get(name, 99998), name.lower(), str(r["mname"] or "").lower())
        ordered.sort(key=_sec_key)
        for pos, r in enumerate(ordered):
            approve_pos[r["id"]] = pos

    def engine_template_now(tid, key):
        """The value the engine would use for normalised name `key` from the
        CURRENT template: last non-null master in approve order."""
        best = None
        for r in by_tid[tid]:
            if r["is_body_option"] and r["variable_value"] is not None and _up(r["mname"]) == key:
                if best is None or approve_pos[r["id"]] > approve_pos[best["id"]]:
                    best = r
        return None if best is None else float(best["variable_value"])

    def master_var_names(tid):          # == _masterBodyVarNameSet / server _build_body_variables keys
        return {_up(r["mname"]) for r in by_tid[tid] if r["is_body_option"] and r["variable_value"] is not None and r["mname"]}

    def master_ids_by_name_untrimmed(tid):   # == calculator.js masterIdsByName (upper, NOT trimmed)
        d = defaultdict(list)
        for r in by_tid[tid]:
            if r["is_body_option"]:
                d[str(r["mname"] or "").upper()].append(r["id"])
        return d

    def wired(tid):
        out = set()
        for r in by_tid[tid]:
            for m in tok_re.findall(str(r["formula"] or "")):
                out.add(m.strip().upper())
        return out

    # ── B. exposure census ─────────────────────────────────────────────────
    rep.h("B. EXPOSURE CENSUS (trailers with a configurator draft)")
    census, flag_rows = [], []
    exposed: set[int] = set()
    for d in drafts:
        tid = d["tid"]
        payload = _loads(d["payload"]) or {}
        nodes = payload.get("nodes") or {}
        flags = [n for n in nodes.values() if isinstance(n, dict) and n.get("type") == "flag"]
        mv, mids_untr, wset = master_var_names(tid), master_ids_by_name_untrimmed(tid), wired(tid)
        c = Counter()
        for n in flags:
            raw_name = n.get("flagBindingName") or n.get("label") or ""
            key = _up(raw_name)
            bid = n.get("flagBindingId")
            try:
                bid_i = int(bid) if bid not in (None, "") else None
            except (TypeError, ValueError):
                bid_i = None
            if bid_i is None:
                binding = "unbound"
            elif bid_i in rows_by_id and rows_by_id[bid_i]["tid"] == tid:
                binding = "live"
            elif bid_i in rows_by_id:
                binding = "foreign"
            else:
                binding = "missing"
            untr_hits = mids_untr.get(str(raw_name).upper(), [])
            is_master = key in mv
            fvd = n.get("flagVarDefault")
            try:
                fvd_f = float(fvd) if fvd not in (None, "") else None
            except (TypeError, ValueError):
                fvd_f = None
            row = {
                "tid": tid, "trailer": trailers.get(tid, {}).get("name"), "v2": trailers.get(tid, {}).get("configurator_v2"),
                "node_id": n.get("id"), "label": n.get("label"), "flagBindingName": n.get("flagBindingName"),
                "flagBindingId": bid, "binding": binding, "flagMode": n.get("flagMode"),
                "master_named": is_master, "wired": key in wset,
                "heal_name_matches": len(untr_hits) if binding in ("foreign", "missing") else "",
                "whitespace_drift": bool(is_master and not untr_hits),
                "flagVarDefault": fvd_f,
            }
            flag_rows.append(row)
            c["flags"] += 1
            c[f"binding_{binding}"] += 1
            if is_master:
                c["master_named"] += 1
                if key in wset:
                    c["master_named_wired"] += 1
            if binding in ("foreign", "missing"):
                c["stale"] += 1
                c["stale_heals" if len(untr_hits) == 1 else ("stale_ambiguous" if untr_hits else "stale_no_match")] += 1
            if row["whitespace_drift"]:
                c["whitespace_drift"] += 1
            if fvd_f and fvd_f > 0:
                c["flagVarDefault"] += 1
                if is_master:
                    c["flagVarDefault_on_master_name"] += 1
        if c["master_named"]:
            exposed.add(tid)
        t = trailers.get(tid, {})
        census.append({"tid": tid, "trailer": t.get("name"), "active": t.get("is_active"), "v2": t.get("configurator_v2"),
                       "draft_updated_at": d["updated_at"], **{k: c.get(k, 0) for k in (
                           "flags", "master_named", "master_named_wired", "binding_live", "binding_unbound",
                           "binding_foreign", "binding_missing", "stale_heals", "stale_ambiguous", "stale_no_match",
                           "whitespace_drift", "flagVarDefault", "flagVarDefault_on_master_name")}})
    cf = ["tid", "trailer", "active", "v2", "flags", "master_named", "master_named_wired", "binding_live",
          "binding_unbound", "binding_foreign", "binding_missing", "stale_heals", "stale_ambiguous",
          "stale_no_match", "whitespace_drift", "flagVarDefault", "flagVarDefault_on_master_name", "draft_updated_at"]
    rep.csv("B_exposure_census.csv", census, cf)
    rep.csv("B_flags.csv", flag_rows)
    rep.p(f"  {'tid':>4} {'v2':>5} {'act':>5} {'flags':>5} {'mstr':>5} {'wired':>5} {'stale':>5} {'heal1':>5} {'amb':>4} {'ws':>3} {'fvd':>4}  trailer")
    for r in census:
        stale = r["binding_foreign"] + r["binding_missing"]
        rep.p(f"  {r['tid']:>4} {str(r['v2']):>5} {str(r['active']):>5} {r['flags']:>5} {r['master_named']:>5} "
              f"{r['master_named_wired']:>5} {stale:>5} {r['stale_heals']:>5} {r['stale_ambiguous']:>4} "
              f"{r['whitespace_drift']:>3} {r['flagVarDefault']:>4}  {r['trailer']}")
    exp_v2 = sorted(t for t in exposed if trailers.get(t, {}).get("configurator_v2"))
    exp_active_v2 = sorted(t for t in exp_v2 if trailers.get(t, {}).get("is_active"))
    rep.s(f"B exposed trailers (a flag named after a master body variable): {len(exposed)} → {sorted(exposed)}")
    rep.s(f"  of which configurator_v2 (live panel exposure): {len(exp_v2)} → {exp_v2}; active v2: {exp_active_v2}")
    rep.data["exposed"] = sorted(exposed)
    rep.data["exposed_v2"] = exp_v2

    # ── C. EPS/PU pair invariant ───────────────────────────────────────────
    rep.h("C. EPS/PU PAIR INVARIANT on exposed trailers (structural pairs, both sides > 0)")
    pair_rows, pairs_total = [], 0
    for tid in sorted(exposed):
        groups = defaultdict(list)
        for r in by_tid[tid]:
            if r["is_body_option"]:
                groups[f"{r['grp']}|{r['sub'] or ''}"].append(r)
        for key, sibs in groups.items():
            if len(sibs) != 2:
                continue
            eps = next((r for r in sibs if "EPS" in str(r["mname"] or "").upper()), None)
            pu = next((r for r in sibs if "PU" in str(r["mname"] or "").upper()), None)
            if not eps or not pu or eps["id"] == pu["id"]:
                continue
            pairs_total += 1
            if (eps["variable_value"] or 0) > 0 and (pu["variable_value"] or 0) > 0:
                pair_rows.append({"tid": tid, "group": key, "eps_id": eps["id"], "eps": eps["mname"], "eps_v": eps["variable_value"],
                                  "pu_id": pu["id"], "pu": pu["mname"], "pu_v": pu["variable_value"]})
    rep.csv("C_pairs_both_gt0.csv", pair_rows, ["tid", "group", "eps_id", "eps", "eps_v", "pu_id", "pu", "pu_v"])
    rep.p(f"  structural pairs={pairs_total}  both>0={len(pair_rows)}")
    for r in pair_rows:
        rep.p(f"  ! tid {r['tid']} {r['group']}: {r['eps']}={r['eps_v']} / {r['pu']}={r['pu_v']}")
    rep.s(f"C pair invariant: {len(pair_rows)} violation(s) of {pairs_total} structural pairs")

    # ── D. saved costings scan ─────────────────────────────────────────────
    rep.h("D. SAVED COSTINGS on exposed trailers — per-name shadow classification + bug window")
    names_by_id = {r["id"]: r["mname"] for r in bom}
    master_ids = {r["id"] for r in bom if r["is_body_option"]}
    # The ONLY names #178/#181 could shadow: master-named draft flags that some
    # formula on the trailer references (only wired names were ever sent).
    shadowable = defaultdict(set)
    for fr in flag_rows:
        if fr["master_named"] and fr["wired"]:
            shadowable[fr["tid"]].add(_up(fr["flagBindingName"] or fr["label"]))
    scan, flagged = [], []
    totals = Counter()
    ids = sorted(exposed)
    calc_meta = q("""SELECT id, trailer_type_id AS tid, created_at, approved_at, status, quote_number,
                            deleted_at, is_repair
                     FROM calculations WHERE trailer_type_id = ANY(:ids) ORDER BY id""", ids=ids) if ids else []
    for cm in calc_meta:
        totals["calcs"] += 1
        try:
            # body_variables via ::json (NOT jsonb): json keeps the saved key ORDER,
            # which is the engine's precedence when two keys normalise equal
            # (e.g. template 'SIDES PU ' followed by the override 'SIDES PU').
            part = q("""SELECT result_json::json -> 'body_variables' AS bv,
                               result_json::jsonb #> '{input_state,ui_snapshot,body_variables}' AS snap_bv,
                               (result_json::jsonb #> '{input_state,ui_snapshot}') ? 'draft_flag_vars' AS v153,
                               result_json::jsonb #> '{input_state,ui_snapshot,draft_flag_vars}' AS dfv,
                               result_json::jsonb ->> 'grand_total' AS grand_total,
                               result_json::jsonb ->> 'selling_price' AS selling_price,
                               result_json::jsonb ->> 'net_total' AS net_total
                        FROM calculations WHERE id = :id AND result_json LIKE '{%'""", id=cm["id"])
        except Exception as e:
            db.rollback()
            totals["unparseable"] += 1
            scan.append({**dict(cm), "error": f"json: {e.__class__.__name__}"})
            continue
        if not part:
            totals["no_result_json"] += 1
            continue
        p = part[0]
        bv = p["bv"] if isinstance(p["bv"], dict) else {}
        snap = p["snap_bv"] if isinstance(p["snap_bv"], dict) else {}
        dfv = {_up(k): v for k, v in p["dfv"].items()} if isinstance(p["dfv"], dict) else {}
        # engine-effective value per normalised name: strip().upper(), LAST key wins
        eff, spellings = {}, Counter()
        for k, v in bv.items():
            eff[_up(k)] = v
            spellings[_up(k)] += 1
        # template values the page held at save time, grouped by normalised name
        tmpl_rows, unmapped = defaultdict(list), 0      # name -> [(approve_pos, value)]
        for sid, sval in snap.items():
            try:
                rid, fv = int(sid), float(sval)
            except (TypeError, ValueError):
                continue
            if rid not in names_by_id:
                unmapped += 1
            elif rid in master_ids and names_by_id[rid]:
                tmpl_rows[_up(names_by_id[rid])].append((approve_pos.get(rid, -1), fv))
        shadow, drift, ambiguous = [], [], 0
        for key, pairs in tmpl_rows.items():
            if key not in eff:
                continue
            try:
                rv = float(eff[key])
            except (TypeError, ValueError):
                continue
            tv = max(pairs)[1]                   # engine template = last master in approve order
            if len({round(v, 9) for _, v in pairs}) > 1:
                ambiguous += 1                   # informational: duplicate-named masters disagree
            if abs(rv - tv) <= 1e-6:
                continue
            m = {"name": key, "saved_result": rv, "snapshot_template": tv, "split_keys": spellings[key] > 1}
            is_shadow = (bool(p["v153"]) and key in shadowable[cm["tid"]]
                         and (abs(rv) <= EPS_TOL or (key in dfv and _num_eq(rv, dfv[key]))))
            (shadow if is_shadow else drift).append(m)
        # Snapshot-less saves (edit-replay re-saves store ui_snapshot=null) cannot be
        # compared with a save-time template: flag a shadowable name the engine used
        # at 0 while the CURRENT template is > 0, for a manual look (never recomputed).
        possible = []
        if not snap:
            for key in sorted(shadowable[cm["tid"]]):
                if key in eff:
                    try:
                        rv = float(eff[key])
                    except (TypeError, ValueError):
                        continue
                    now = engine_template_now(cm["tid"], key)
                    if abs(rv) <= EPS_TOL and now is not None and now > EPS_TOL:
                        possible.append({"name": key, "saved_result": rv, "template_now": now,
                                         "split_keys": spellings[key] > 1})
        pattern = ("SHADOW+DRIFT" if shadow and drift else "SHADOW" if shadow else "PIN_DRIFT" if drift
                   else "NO_SNAPSHOT_POSSIBLE_SHADOW" if possible else "")
        created = str(cm["created_at"] or "")
        row = {**dict(cm), "trailer": trailers.get(cm["tid"], {}).get("name"),
               "v2": trailers.get(cm["tid"], {}).get("configurator_v2"),
               "has_ui_snapshot": bool(snap), "v153_save": bool(p["v153"]),
               "created_ge_W178": created >= W178, "created_ge_W181": created >= W181,
               "approved_ge_W178": str(cm["approved_at"] or "") >= W178,
               "pattern": pattern, "shadow_n": len(shadow), "drift_n": len(drift), "ambiguous_dup_names": ambiguous,
               "split_keys": any(x["split_keys"] for x in shadow + drift), "unmapped_snapshot_ids": unmapped,
               "shadow": shadow, "drift": drift, "no_snapshot_possible_shadow": possible, "draft_flag_vars": p["dfv"],
               "grand_total": p["grand_total"], "selling_price": p["selling_price"], "net_total": p["net_total"]}
        in_window = bool(row["created_ge_W178"] or row["approved_ge_W178"] or row["v153_save"])
        row["in_window"] = in_window
        for k in ("has_ui_snapshot", "v153_save", "created_ge_W178", "created_ge_W181", "approved_ge_W178"):
            totals[k] += int(bool(row[k]))
        if in_window and not snap:
            totals["in_window_without_ui_snapshot"] += 1     # unassessable: no save-time template to compare
        if shadow:
            totals["shadow_costings"] += 1
            totals["shadow_costings_in_window"] += int(in_window)
        if drift and not shadow:
            totals["drift_only_costings"] += 1
            totals["drift_only_in_window"] += int(in_window)
        if possible:
            totals["no_snapshot_possible_shadow"] += 1
        totals["ambiguous_dup_names"] += ambiguous
        totals["split_key_costings"] += int(row["split_keys"])
        if shadow or drift or possible or in_window:
            scan.append(row)
        if shadow or drift:
            flagged.append(row)
    sf = ["id", "tid", "trailer", "v2", "pattern", "quote_number", "status", "created_at", "approved_at", "deleted_at",
          "in_window", "v153_save", "created_ge_W178", "created_ge_W181", "approved_ge_W178", "has_ui_snapshot",
          "shadow_n", "drift_n", "ambiguous_dup_names", "split_keys", "unmapped_snapshot_ids",
          "grand_total", "selling_price", "net_total", "shadow", "drift", "no_snapshot_possible_shadow",
          "draft_flag_vars", "error"]
    rep.csv("D_costings_in_scope.csv", scan, sf)
    rep.p("  " + "  ".join(f"{k}={v}" for k, v in sorted(totals.items())))
    rep.p(f"  in-scope rows written: {len(scan)}   flagged (shadow or drift): {len(flagged)}")
    for r in [x for x in scan if x.get("no_snapshot_possible_shadow")]:
        rep.p(f"  [NO_SNAPSHOT_POSSIBLE_SHADOW] calc {r['id']} tid {r['tid']} {r['quote_number']} status={r['status']} :: "
              + "; ".join(f"{x['name']} saved={x['saved_result']} template_now={x['template_now']}"
                          for x in r["no_snapshot_possible_shadow"]))
    for r in flagged:
        rep.p(f"  [{r['pattern']}] calc {r['id']} tid {r['tid']} {r['quote_number']} status={r['status']} created={r['created_at']} "
              f"v153={r['v153_save']} deleted={bool(r['deleted_at'])} :: "
              + "; ".join(f"{'S' if x in r['shadow'] else 'd'}:{x['name']} saved={x['saved_result']} template={x['snapshot_template']}"
                          + (" (split keys)" if x["split_keys"] else "") for x in r["shadow"] + r["drift"]))
    rep.s(f"D costings on exposed trailers: {totals['calcs']}; created since {W178}: {totals['created_ge_W178']} "
          f"(since {W181}: {totals['created_ge_W181']}); accepted since {W178}: {totals['approved_ge_W178']}; "
          f"saved by a v1.53 client (any date): {totals['v153_save']}; in window but no ui_snapshot (unassessable): "
          f"{totals['in_window_without_ui_snapshot']}")
    rep.s(f"D #178/#181 SHADOW costings (v1.53 save; a wired master-named flag saved at 0 or at its draft-flag value "
          f"while the template differed) = {totals['shadow_costings']} (in window: {totals['shadow_costings_in_window']})")
    rep.s(f"D pin/template drift only (pre-existing edit-pin class, informational) = {totals['drift_only_costings']} "
          f"(in window: {totals['drift_only_in_window']}); duplicate-name disagreements={totals['ambiguous_dup_names']}; "
          f"split-key costings={totals['split_key_costings']}")
    rep.s(f"D snapshot-less costings with a POSSIBLE shadow (shadowable name at 0 while today's template > 0; "
          f"manual look, not recomputed) = {totals['no_snapshot_possible_shadow']}")
    rep.data["costing_totals"] = dict(totals)

    # ── E. validated references ────────────────────────────────────────────
    rep.h("E. VALIDATED REFERENCES (window or linked to a flagged costing)")
    flagged_ids = [r["id"] for r in flagged]
    vrefs = q("""SELECT v.id, v.calculation_id, v.trailer_type_id AS tid, v.label, v.created_at, v.active
                 FROM validated_references v
                 WHERE v.trailer_type_id = ANY(:ids)
                   AND (v.created_at >= CAST(:w AS timestamp) OR v.calculation_id = ANY(:cids))
                 ORDER BY v.id""", ids=ids or [-1], w=W178, cids=flagged_ids or [-1])
    rep.csv("E_validated_references.csv", [dict(v) for v in vrefs], ["id", "calculation_id", "tid", "label", "created_at", "active"])
    for v in vrefs:
        rep.p(f"  vref {v['id']} calc {v['calculation_id']} tid {v['tid']} active={v['active']} created={v['created_at']} label={v['label']}")
    rep.p(f"  rows={len(vrefs)}")
    rep.s(f"E validated references in window or on flagged costings: {len(vrefs)}")

    # ── F. impact recompute ────────────────────────────────────────────────
    rep.h("F. IMPACT RECOMPUTE for SHADOW costings (current prices; delta isolates the shadowed names)")
    impact = []
    cands = [r for r in flagged if r["shadow"]]
    cands.sort(key=lambda r: (0 if r["in_window"] else 1, -int(r["id"])))
    todo = cands[: args.max_recompute]
    if len(cands) > len(todo):
        msg = (f"F NOTE: capped at --max-recompute={args.max_recompute}; {len(cands) - len(todo)} SHADOW costing(s) "
               f"NOT recomputed (out-of-window and oldest are dropped first)")
        rep.p("  " + msg)
        rep.s(msg)
    if todo:
        impact = _recompute(rep, db, text, todo)
    rep.csv("F_impact.csv", impact, ["id", "tid", "quote_number", "status", "pattern", "in_window", "saved_net_total",
                                     "shadow_net_total", "corrected_net_total", "delta_net", "delta_pct",
                                     "shadow_materials", "corrected_materials", "delta_materials",
                                     "saved_vs_replay_drift", "names", "error"])
    ok = [r for r in impact if r.get("delta_net") is not None]
    if impact:
        rep.s(f"F SHADOW impact: {len(ok)} costing(s) recomputed, sum(corrected - shadow) net = R {sum(r['delta_net'] for r in ok):,.2f} "
              f"(+ = under-quoted, - = over-quoted); errors={len(impact) - len(ok)}")
    else:
        rep.s("F impact recompute: no SHADOW costings, nothing to recompute")

    # ── G. deploy readiness for 94ed70b ────────────────────────────────────
    rep.h("G. DEPLOY READINESS for 94ed70b (JS-only) — what the heal + guard will change on prod")
    heal_v2 = [r for r in census if r["v2"] and (r["binding_foreign"] + r["binding_missing"]) > 0]
    amb = [r for r in census if r["stale_ambiguous"]]
    ws = [r for r in flag_rows if r["whitespace_drift"]]
    fvd_master = [r for r in flag_rows if r["master_named"] and (r["flagVarDefault"] or 0) > 0]
    manni = [t for t in trailers.values() if "MANNI" in str(t["name"] or "").upper()]
    for t in manni:
        n_bo = sum(1 for r in by_tid[t["id"]] if r["is_body_option"])
        n_mv = len(master_var_names(t["id"]))
        n_tok = len(wired(t["id"]))
        rep.p(f"  Manni tid {t['id']} '{t['name']}' active={t['is_active']} v2={t['configurator_v2']} "
              f"is_body_option rows={n_bo} master vars={n_mv} formula tokens={n_tok}")
    rep.p(f"  v2 bodies with stale flag bindings (render changes after the heal): {[(r['tid'], r['trailer']) for r in heal_v2]}")
    rep.p(f"  bodies with AMBIGUOUS stale-name heals: {[(r['tid'], r['trailer']) for r in amb]}")
    rep.p(f"  whitespace-drift master-named flags: {[(r['tid'], r['label']) for r in ws]}")
    rep.p(f"  flagVarDefault set on master-named flags (ignored after deploy): {[(r['tid'], r['label'], r['flagVarDefault']) for r in fvd_master]}")
    rep.s(f"G deploy readiness: v2 bodies with stale bindings={len(heal_v2)}; ambiguous heals={len(amb)}; "
          f"whitespace drift={len(ws)}; flagVarDefault on master names={len(fvd_master)}")
    rep.data["deploy_readiness"] = {"heal_v2": heal_v2, "ambiguous": amb, "whitespace": ws, "fvd_master": fvd_master}

    db.rollback()
    rep.s("DONE — nothing was written to the database (read-only session, rolled back).")
    return 0


def _num_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= 1e-6
    except (TypeError, ValueError):
        return False


def _recompute(rep: Report, db, text, todo) -> list[dict]:
    """Re-run the approve-path engine twice per SHADOW costing against CURRENT
    templates/prices, with body_variable_overrides built from the costing's own
    SAVED body_variables (every key, in saved order):
      shadow    = the saved body_variables exactly (what the quote was computed with)
      corrected = the same, but every key that normalises to a SHADOW name set to
                  the save-time template value (drift names stay as saved)
    delta = corrected - shadow isolates the shadowing from later price drift and
    from inputs a replay cannot reproduce (formula_overrides are not stored)."""
    from app.database import BillOfMaterial, BOMSection, Formula, GlobalVariable, TrailerType
    from app.formula_engine import calculate_bom
    from app.routers.calculator import (
        _append_free_hand_lines, _apply_body_variable_overrides, _apply_chassis_and_margin,
        _apply_discount, _build_body_variables, _build_bom_items,
    )
    from app.services import _bom_load_options
    from app.services import insulation_foam as pu_foam

    formula_lib = {f.name.lower(): f.expression for f in db.query(Formula).filter_by(is_active=True).all()}
    global_vars = {gv.name: gv.value for gv in db.query(GlobalVariable).all()}
    section_order = {s.name: s.sort_order for s in db.query(BOMSection).all()}
    out = []

    def run(tid, dims, body, bvo):
        tt = db.query(TrailerType).filter_by(id=tid).first()
        bom_rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=tid)
                    .options(*_bom_load_options()).order_by(BillOfMaterial.sort_order).all())

        def _sec_key(r):
            name = r.bom_section or (r.material.category.name if r.material and r.material.category else "")
            return (section_order.get(name, 99998), name.lower(), r.material.name.lower() if r.material else "")
        bom_rows.sort(key=_sec_key)
        overrides = {str(k): float(v) for k, v in (body.get("overrides") or {}).items()}
        body_opt_sel = {str(k): bool(v) for k, v in (body.get("body_option_selections") or {}).items()}
        flag_overrides = {str(k): bool(v) for k, v in (body.get("flag_overrides") or {}).items()}
        opt_enabled = body.get("optional_sections_enabled") or []
        items = _build_bom_items(bom_rows, dims, overrides, body_opt_sel, db, body.get("excluded_categories") or [],
                                 trailer=tt, flag_overrides=flag_overrides, include_all_items=False,
                                 user_excluded_bom_ids=body.get("user_excluded_bom_ids") or [],
                                 optional_sections_enabled=opt_enabled, formula_overrides=None,
                                 insulation_foam=pu_foam.normalise(body.get("insulation_foam")))
        _append_free_hand_lines(items, body, opt_enabled)
        bvars = _build_body_variables(bom_rows)
        _apply_body_variable_overrides(bvars, bvo)
        res = calculate_bom(items, dims, bvars, formula_lib, global_vars)
        materials = float(res.get("grand_total") or 0)
        res = _apply_chassis_and_margin(res, body, db)
        res = _apply_discount(res, body)
        return materials, float(res.get("net_total") or 0)

    for r in todo:
        names = {x["name"]: x["snapshot_template"] for x in r["shadow"]}
        row = {"id": r["id"], "tid": r["tid"], "quote_number": r["quote_number"], "status": r["status"],
               "pattern": r["pattern"], "in_window": r["in_window"], "names": sorted(names)}
        try:
            full = db.execute(text("SELECT dimensions_json, result_json, discount_kind, discount_input "
                                   "FROM calculations WHERE id = :id"), {"id": r["id"]}).mappings().first()
            result = _loads(full["result_json"]) or {}          # json.loads keeps saved key order
            ist = result.get("input_state") or {}
            dims = _loads(full["dimensions_json"]) or result.get("dimensions") or {}
            body = dict(ist)
            body["discount_kind"] = full["discount_kind"] if full["discount_kind"] is not None else result.get("discount_kind")
            body["discount_input"] = full["discount_input"] if full["discount_input"] is not None else result.get("discount_input")
            saved_bv = result.get("body_variables") or {}
            shadow_bvo = dict(saved_bv)
            corrected_bvo = {k: (names[_up(k)] if _up(k) in names else v) for k, v in saved_bv.items()}
            sm, sn = run(r["tid"], dims, body, shadow_bvo)
            cm, cn = run(r["tid"], dims, body, corrected_bvo)
            saved_net = float(r["net_total"] or r["selling_price"] or r["grand_total"] or 0)
            row.update({"saved_net_total": round(saved_net, 2), "shadow_net_total": round(sn, 2),
                        "corrected_net_total": round(cn, 2), "delta_net": round(cn - sn, 2),
                        "delta_pct": round((cn - sn) / sn * 100, 2) if sn else None,
                        "shadow_materials": round(sm, 2), "corrected_materials": round(cm, 2),
                        "delta_materials": round(cm - sm, 2), "saved_vs_replay_drift": round(sn - saved_net, 2)})
            rep.p(f"  calc {r['id']} {r['quote_number']} [{r['pattern']}] saved={row['saved_net_total']:,.2f} "
                  f"shadow={row['shadow_net_total']:,.2f} corrected={row['corrected_net_total']:,.2f} "
                  f"delta={row['delta_net']:,.2f} ({row['delta_pct']}%) replay_drift={row['saved_vs_replay_drift']:,.2f}")
        except Exception as e:
            db.rollback()
            row["error"] = f"{e.__class__.__name__}: {e}"[:300]
            rep.p(f"  calc {r['id']} recompute ERROR: {row['error']}")
        out.append(row)
    return out


if __name__ == "__main__":
    sys.exit(main())
