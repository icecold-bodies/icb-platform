r"""
tools/september_price_import.py
───────────────────────────────
Manifest-driven apply of Burt's September 2026 price + description update
(v1.52). Reads ONLY the BA change manifest (already reconciled against an
independent workbook diff by tools/diff_grp_costings.py — ratified default 1);
never opens the workbooks itself.

Modes
─────
    dry-run (default)  builds the full plan and writes the BEFORE/AFTER table,
                       excluded-scope list, override-survivor list and review
                       list into --out-dir. Nothing touches the DB.
    --apply            backs up every table it writes, then applies the plan in
                       ONE transaction, stamping badges and writing the journal
                       JSON that --revert replays.
    --revert J.json    byte-exact reverse of a previous --apply, from its
                       journal (0046 pattern: apply -> revert -> re-apply is
                       provably identical).

Scope (Michael's ruling, enforced in code)
──────────────────────────────────────────
The five Manni sheets and Sheet1 are REFUSED even when present in the input
manifest; AELER PANELS has no MES body (reported, skipped). Everything else
maps per the §3.0 table below.

What one manifest row can do
────────────────────────────
  LINE_UPDATE   price and/or description change on a matched BOM line.
                The new identity lives on the MATERIAL, so the material is
                either updated IN PLACE (when every referencing line is in
                this update with the same target) or the line is REPOINTED to
                a found-or-created material carrying exactly (new name, new
                price) — nothing leaks onto Manni / deleted / unchanged lines.
                An existing quote-independent override on the line is RESET
                (journaled) when the update supplies a new price; a desc-only
                change keeps the override.
  PU_COVERED    PU foam lines keep their price in unit_price_override (0046
                architecture). The manifest value's grade flavour is resolved
                against the stored 32D price:
                  rule 32D: new ≈ stored × 4100/4310            -> store new
                  rule 4G-display: new/factor_new ≈ stored × 4100/4310
                                                               -> store new/factor_new
                  rule 4G-continuation (RHINORANGE): new ≈ stored × 5400/5875
                                                               -> store new, flag
                No rule fits -> REVIEW list, no write. A covered PU line with
                no override (Chester pattern) gets one created, flavour read
                from the manifest pair itself.
  PU_RESCALE    in-scope PU lines the manifest never prices (their sheet cell
                shows 0 while the option is deselected) but which carry a
                32D-stored override: × 4100/4310, so a PU-insulated quote on
                those bodies prices at September too. Rate-guarded: an
                override whose price/thickness rate is not ≈ the 32D rate goes
                to REVIEW instead.
  FACTOR        admin_settings['costings.pu_foam_4g_factor']
                1.363109048723898 -> 5400/4100 (ratified default 7).

Every touched line is stamped bill_of_materials.price_updated_at = batch time
(migration 0047) — the calculator's "Updated Sep 2026" badge reads it with a
30-day window. Touched materials get last_updated + last_bulk_update_at/note,
so the existing admin machinery (Undo Last Bulk Update, amber chip) sees this
batch like any other.

Usage
─────
    python tools/september_price_import.py --manifest docs/audit/september_price_update/september_change_manifest.csv
    python tools/september_price_import.py --manifest ... --apply
    python tools/september_price_import.py --revert docs/audit/september_price_update/apply_journal_dev_20260904T090000Z.json

DATABASE_URL env var selects the database (default: backend/.env's dev value
is NOT read — pass it explicitly or via env; refuses to run without one).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

# ── constants ────────────────────────────────────────────────────────────────

BATCH_NOTE = "September 2026 price update"
CHANGED_BY = "september_2026_price_update (v1.52)"

SHEET_32D_OLD, SHEET_32D_NEW = 4310.0, 4100.0
SHEET_4G_OLD, SHEET_4G_NEW = 5875.0, 5400.0
SCALE_32D = SHEET_32D_NEW / SHEET_32D_OLD          # 0.95127610...
SCALE_4G = SHEET_4G_NEW / SHEET_4G_OLD             # 0.91914893...
FACTOR_NEW = SHEET_4G_NEW / SHEET_32D_NEW          # 1.31707317...
FACTOR_KEY = "costings.pu_foam_4g_factor"
RATE_32D_OLD = SHEET_32D_OLD * (1.22 * 2.44) / 2.98  # 4305.37 — 0046's rate
PU_TOL = 0.005                                     # 0.5% relative
PRICE_TOL = 0.005                                  # rand, exact-value compares

PU_NAMES = {"PU", "PU FOAM"}

# §3.0 mapping — workbook sheet name (exact spelling) -> trailer_types.id
SHEET_TO_TRAILER = {
    "Adv Vacuum panels": 1, "ADVANTICA BODY": 2, "TAUT LINER RIGID": 9,
    "CHESTER SPEC MEAT BODY": 10, "MEAT BODY": 12, "DRY FREIGHT TRAILER": 13,
    "GRP TRAILERS": 14, "RHINORANGE TRAILER": 15,
    "icecream up to 3,2": 16, "icecream up to 4.8": 17, " icecream 4.9 up": 18,
    " UP TO 2,3 MTR FREEZER ": 19, " UP TO 4.8 MT FREEZER  (2": 20,
    " 4.9 & UP FREEZER BODY (2": 21,
    "EXPLOSIVE UP TO 2.7": 34, "EXPLOSIVE 2.7 TO 4.8": 37, "EXPLOSIVE 4.9 AND UP": 24,
    "UP TO 2.3 CHILLER BODY": 25, "UP TO 5.5 CHILLER AND 2.3 WIDE": 26,
    " 4.9 & UP CHILLER AND 2.5 WIDE ": 27,
    "BAKERY BODIES": 39, "SMALL MEAT BODY UP TO 5,2": 36,
}
# Refused by ruling — the import must reject these even if present in input.
REFUSED_SHEETS = {"Manni RIGIDS CB", "Manni RIGIDS FB", "Manni Bakkie Rigids",
                  "Manni TRAILERS", "Manni DF", "Sheet1"}
# In scope by ruling but with no MES body — reported, skipped.
UNMAPPED_SHEETS = {"AELER PANELS"}

TABLES_WRITTEN = ["materials", "bill_of_materials", "admin_settings",
                  "price_history", "bom_override_history"]

CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").upper().strip())


def fnum(s):
    s = (s or "").strip() if isinstance(s, str) else s
    if s in (None, ""):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def approx(a: float | None, b: float | None, rel: float = PU_TOL) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.01, rel * max(abs(a), abs(b)))


def resolve_covered_pu(stored, old, new):
    """PU grade-flavour resolution for a manifest-covered PU line.

    `stored` is the line's current unit_price_override (32D by 0046, except
    RHINORANGE), `old`/`new` the manifest pair. Returns (rule, value_to_store)
    or (None, None) when no rule fits — the caller sends that to REVIEW.

    Order matters: continuity against the STORED price dominates, so the
    FREEZER LARGE rows whose (old, new) pair happens to sit near the 4G sheet
    ratio (Burt fixed a thickness on the way) still resolve as plain 32D.
    """
    if new is None:
        return None, None
    if stored is not None:
        if approx(new, stored * SCALE_32D):
            return "PU-32D", new
        if approx(new / FACTOR_NEW, stored * SCALE_32D):
            return "PU-4G-DISPLAY", new / FACTOR_NEW
        if approx(new, stored * SCALE_4G):
            return "PU-4G-CONTINUATION", new
        return None, None
    if old is not None and approx(new, old * SCALE_32D):
        return "PU-32D(new override)", new
    if old is not None and approx(new, old * SCALE_4G):
        return "PU-4G-DISPLAY(new override)", new / FACTOR_NEW
    return None, None


# ── manifest ─────────────────────────────────────────────────────────────────

def load_manifest(path: str):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    in_scope, refused, unmapped = [], [], []
    for r in rows:
        sheet = r["sheet"]
        if sheet in REFUSED_SHEETS:
            refused.append(r)
        elif sheet in UNMAPPED_SHEETS:
            unmapped.append(r)
        elif sheet in SHEET_TO_TRAILER:
            in_scope.append(r)
        else:
            raise SystemExit(f"manifest sheet {sheet!r} is not in the §3.0 mapping, "
                             f"the refused list, or the unmapped list — refusing to guess.")
    return in_scope, refused, unmapped


# ── DB snapshot ──────────────────────────────────────────────────────────────

class Db:
    def __init__(self, conn):
        self.conn = conn
        self.trailers = {r.id: dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT id, name, is_active FROM trailer_types"))}
        self.materials = {r.id: dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT id, name, category_id, unit_of_measure, price_per_unit, supplier, "
            "material_code, sap_code, size, manufacture_sub_category, is_active "
            "FROM materials"))}
        self.bom = {r.id: dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT id, trailer_type_id, material_id, bom_section, sort_order, "
            "source_cell, unit_price_override, is_body_option, skin_formula_id, "
            "taping_block_id, floor_plate_id, mounting_cleat_id, "
            "body_option_linked_id FROM bill_of_materials"))}
        self.mat_refs = defaultdict(list)
        for b in self.bom.values():
            self.mat_refs[b["material_id"]].append(b)
        self.by_tt_name = defaultdict(list)
        for b in self.bom.values():
            if not b["is_body_option"]:
                self.by_tt_name[(b["trailer_type_id"],
                                 norm(self.materials[b["material_id"]]["name"]))].append(b)
        # last override-history provenance per bom line (who/when context for resets)
        self.ovr_prov = {}
        for r in conn.execute(sa.text(
                "SELECT DISTINCT ON (bom_id) bom_id, changed_at, batch_at "
                "FROM bom_override_history ORDER BY bom_id, changed_at DESC")):
            self.ovr_prov[r.bom_id] = f"last override batch {r.batch_at or r.changed_at}"
        # insulation thickness per PU line (0046's linkage)
        self.thickness = {}
        for r in conn.execute(sa.text("""
            SELECT b.id, bo.variable_value AS th
            FROM bill_of_materials b
            JOIN materials m ON m.id = b.material_id
            LEFT JOIN bill_of_materials bo
              ON bo.trailer_type_id = b.trailer_type_id AND bo.is_body_option
             AND bo.body_option_subgroup = 'INSULATION'
             AND bo.material_id = b.body_option_linked_id
            WHERE UPPER(BTRIM(m.name)) IN ('PU','PU FOAM')
              AND COALESCE(b.is_body_option, FALSE) = FALSE""")):
            self.thickness[r.id] = r.th

    def src_row(self, b) -> int | None:
        m = CELL_RE.match((b["source_cell"] or "").strip())
        return int(m.group(2)) if m else None

    def is_pu(self, b) -> bool:
        return (not b["is_body_option"]
                and norm(self.materials[b["material_id"]]["name"]) in PU_NAMES)

    def eff_price(self, b):
        if b["unit_price_override"] is not None:
            return b["unit_price_override"]
        return self.materials[b["material_id"]]["price_per_unit"]


# ── matching (settled in §3.0: 426 matched / 1 unmatched / 0 ambiguous) ─────

def match_rows(db: Db, in_scope: list[dict]):
    actionable, no_action = [], []
    for r in in_scope:
        if r["price_changed"] == "True" or r["desc_changed"] == "True":
            actionable.append(r)
        else:
            no_action.append(r)

    groups = defaultdict(list)
    for r in actionable:
        groups[(SHEET_TO_TRAILER[r["sheet"]], norm(r["desc_old"]))].append(r)

    matched, unmatched, ambiguous = [], [], []
    for (tid, name), mrows in groups.items():
        cands = sorted(db.by_tt_name.get((tid, name), []),
                       key=lambda b: (db.src_row(b) or 10**9, b["sort_order"] or 0, b["id"]))
        mrows = sorted(mrows, key=lambda r: int(r["row"]))
        if not cands:
            unmatched.extend(mrows)
            continue
        if len(mrows) == len(cands):
            matched.extend(zip(mrows, cands))
            continue
        if len(cands) > len(mrows):
            for mr in mrows:
                sec = norm(mr["section"])
                insec = [b for b in cands if sec and sec in norm(b["bom_section"] or "")]
                if len(insec) == 1:
                    matched.append((mr, insec[0]))
                elif len(insec) > 1:
                    ranked = sorted(insec, key=lambda b: abs((db.src_row(b) or 10**9) - int(mr["row"])))
                    r0 = abs((db.src_row(ranked[0]) or 10**9) - int(mr["row"]))
                    r1 = abs((db.src_row(ranked[1]) or 10**9) - int(mr["row"])) if len(ranked) > 1 else 10**9
                    if db.src_row(ranked[0]) is not None and r0 + 3 < r1:
                        matched.append((mr, ranked[0]))
                    else:
                        ambiguous.append(mr)
                else:
                    ambiguous.append(mr)
        else:
            matched.extend(zip(mrows, cands))
            unmatched.extend(mrows[len(cands):])
    return matched, unmatched, ambiguous, no_action


# ── plan ─────────────────────────────────────────────────────────────────────

class Plan:
    def __init__(self):
        self.line_actions = []      # dicts, see build_plan
        self.mat_inplace = {}       # mid -> {"name":..., "price":...} post-state
        self.mat_creates = []       # dicts of new material field sets (id assigned at apply)
        self.review = []            # rows refused by a guard, with reason
        self.factor_old = None
        self.warnings = []


def build_plan(db: Db, matched, in_scope_tids) -> Plan:
    plan = Plan()

    # -- 1. covered rows: split PU from normal lines --------------------------
    covered_pu, normal = [], []
    for mr, b in matched:
        (covered_pu if db.is_pu(b) else normal).append((mr, b))

    # -- 2. normal lines: compute target identity per line --------------------
    # target = (new_name or keep, new_price or keep-material-price)
    line_target = {}   # bom_id -> (name, price, mr)
    for mr, b in normal:
        mat = db.materials[b["material_id"]]
        d_chg, p_chg = mr["desc_changed"] == "True", mr["price_changed"] == "True"
        new_name = (mr["desc_new"].strip() if d_chg and mr["desc_new"].strip() else mat["name"])
        new_price = fnum(mr["price_new"]) if p_chg else mat["price_per_unit"]
        if p_chg and new_price is None:
            plan.review.append({**mr, "reason": "price_changed but price_new not numeric"})
            continue
        line_target[b["id"]] = (new_name, new_price, mr, b)

    # -- 3. material disposition: IN_PLACE when every referencing row is ours
    #       with one common target; SPLIT (repoint) otherwise -----------------
    by_mid = defaultdict(list)
    for bid, (nm, pr, mr, b) in line_target.items():
        by_mid[b["material_id"]].append((bid, nm, pr))
    for mid, items in by_mid.items():
        targets = {(norm(nm), round(pr, 4) if pr is not None else None) for _, nm, pr in items}
        all_refs = db.mat_refs[mid]
        ours = {bid for bid, _, _ in items}
        outside = [x for x in all_refs if x["id"] not in ours]
        if not outside and len(targets) == 1:
            nm, pr = items[0][1], items[0][2]
            plan.mat_inplace[mid] = {"name": nm, "price": pr}

    # -- 4. find-or-create registry for SPLIT targets -------------------------
    # existing pool: post-states of IN_PLACE mats + all untouched materials
    pool = {}
    for mid in sorted(db.materials):        # lowest id wins a key — deterministic
        m = db.materials[mid]
        if mid in plan.mat_inplace:
            st = plan.mat_inplace[mid]
            key = (norm(st["name"]), round(st["price"], 4) if st["price"] is not None else None)
        else:
            key = (norm(m["name"]), round(m["price_per_unit"], 4) if m["price_per_unit"] is not None else None)
        if m["is_active"] and key not in pool:
            pool[key] = mid
    creates = {}   # key -> create-record index

    def resolve_target_material(nm, pr, template_mid):
        key = (norm(nm), round(pr, 4) if pr is not None else None)
        if key in pool:
            return pool[key], None
        if key in creates:
            return None, creates[key]
        tpl = db.materials[template_mid]
        rec = {
            "name": nm.strip(), "price_per_unit": pr,
            "category_id": tpl["category_id"], "unit_of_measure": tpl["unit_of_measure"],
            "supplier": tpl["supplier"], "material_code": tpl["material_code"],
            "sap_code": tpl["sap_code"], "size": tpl["size"],
            "manufacture_sub_category": tpl["manufacture_sub_category"],
            "template_material_id": template_mid,
        }
        plan.mat_creates.append(rec)
        idx = len(plan.mat_creates) - 1
        creates[key] = idx
        return None, idx

    # -- 5. line actions for normal lines --------------------------------------
    for bid, (nm, pr, mr, b) in line_target.items():
        mid = b["material_id"]
        mat = db.materials[mid]
        p_chg = mr["price_changed"] == "True"
        act = {
            "kind": "LINE_UPDATE", "bom_id": bid, "sheet": mr["sheet"], "row": int(mr["row"]),
            "trailer_id": b["trailer_type_id"],
            "trailer": db.trailers[b["trailer_type_id"]]["name"],
            "section": b["bom_section"] or "", "desc_before": mat["name"], "desc_after": nm,
            "eff_before": db.eff_price(b), "eff_after": pr,
            "override_before": b["unit_price_override"],
            # default 3: a new PRICE resets the line's override; desc-only keeps it
            "override_after": None if p_chg else b["unit_price_override"],
            "override_reset": p_chg and b["unit_price_override"] is not None,
            "override_provenance": db.ovr_prov.get(bid, "") if b["unit_price_override"] is not None else "",
            "material_before": mid, "pu_rule": "",
            "manifest_price_old": fnum(mr["price_old"]),
            "drift_note": "",
        }
        po = fnum(mr["price_old"])
        if po is not None and not approx(db.eff_price(b), po, 0.002):
            act["drift_note"] = f"DB was {db.eff_price(b)} vs Aug sheet {po} (pre-existing drift)"
        if mid in plan.mat_inplace:
            act["mat_disposition"] = "IN_PLACE"
            act["material_after"] = mid
        else:
            ex_mid, cr_idx = resolve_target_material(nm, pr, mid)
            if ex_mid is not None:
                act["mat_disposition"] = ("UNCHANGED" if ex_mid == mid else "REPOINT_EXISTING")
                act["material_after"] = ex_mid
            else:
                act["mat_disposition"] = "REPOINT_CREATED"
                act["material_after"] = f"NEW#{cr_idx}"
        # desc-only line keeps its override -> its effective price stays the override
        if not p_chg and b["unit_price_override"] is not None:
            act["eff_after"] = b["unit_price_override"]
        plan.line_actions.append(act)

    # -- 6. covered PU lines ----------------------------------------------------
    for mr, b in covered_pu:
        stored = b["unit_price_override"]
        O, N = fnum(mr["price_old"]), fnum(mr["price_new"])
        rule, new_override = resolve_covered_pu(stored, O, N)
        if rule is None:
            plan.review.append({**mr, "reason": f"PU flavour unresolved (stored={stored}, old={O}, new={N})"})
            continue
        plan.line_actions.append({
            "kind": "PU_COVERED", "bom_id": b["id"], "sheet": mr["sheet"], "row": int(mr["row"]),
            "trailer_id": b["trailer_type_id"],
            "trailer": db.trailers[b["trailer_type_id"]]["name"],
            "section": b["bom_section"] or "",
            "desc_before": db.materials[b["material_id"]]["name"],
            "desc_after": db.materials[b["material_id"]]["name"],
            "eff_before": db.eff_price(b), "eff_after": new_override,
            "override_before": stored, "override_after": new_override,
            "override_reset": False,
            "override_provenance": db.ovr_prov.get(b["id"], "") if stored is not None else "",
            "material_before": b["material_id"], "material_after": b["material_id"],
            "mat_disposition": "UNCHANGED", "pu_rule": rule,
            "manifest_price_old": O,
            "drift_note": "" if approx(db.eff_price(b), O or -1, 0.002) else
                          f"DB was {db.eff_price(b)} vs Aug sheet {O}",
        })

    # -- 7. PU rescale for uncovered in-scope PU lines with an override -------
    covered_ids = {a["bom_id"] for a in plan.line_actions}
    for b in db.bom.values():
        if b["trailer_type_id"] not in in_scope_tids or b["id"] in covered_ids:
            continue
        if not db.is_pu(b) or b["unit_price_override"] is None:
            continue
        th = db.thickness.get(b["id"])
        rate = (b["unit_price_override"] / th) if th else None
        if rate is None or not approx(rate, RATE_32D_OLD, 0.01):
            plan.review.append({
                "sheet": "(uncovered PU)", "row": "", "section": b["bom_section"] or "",
                "desc_old": "PU", "desc_new": "PU", "price_old": "", "price_new": "",
                "reason": f"uncovered PU override on {db.trailers[b['trailer_type_id']]['name']} "
                          f"bom={b['id']} rate={rate and round(rate, 2)} not ≈ 32D rate "
                          f"{round(RATE_32D_OLD, 2)} — left untouched",
            })
            continue
        plan.line_actions.append({
            "kind": "PU_RESCALE", "bom_id": b["id"], "sheet": "(not in manifest)", "row": 0,
            "trailer_id": b["trailer_type_id"],
            "trailer": db.trailers[b["trailer_type_id"]]["name"],
            "section": b["bom_section"] or "",
            "desc_before": db.materials[b["material_id"]]["name"],
            "desc_after": db.materials[b["material_id"]]["name"],
            "eff_before": b["unit_price_override"],
            "eff_after": b["unit_price_override"] * SCALE_32D,
            "override_before": b["unit_price_override"],
            "override_after": b["unit_price_override"] * SCALE_32D,
            "override_reset": False,
            "override_provenance": db.ovr_prov.get(b["id"], ""),
            "material_before": b["material_id"], "material_after": b["material_id"],
            "mat_disposition": "UNCHANGED", "pu_rule": "PU-RESCALE-32D",
            "manifest_price_old": None, "drift_note": "",
        })
    return plan


# ── reports ──────────────────────────────────────────────────────────────────

PLAN_FIELDS = ["kind", "sheet", "row", "trailer", "section", "bom_id",
               "desc_before", "desc_after", "eff_before", "eff_after",
               "override_before", "override_after", "override_reset",
               "override_provenance", "material_before", "material_after",
               "mat_disposition", "pu_rule", "manifest_price_old", "drift_note"]


def write_reports(plan: Plan, db: Db, refused, unmapped, unmatched, ambiguous,
                  no_action, out_dir: Path, in_scope_tids):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "before_after_plan.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PLAN_FIELDS)
        w.writeheader()
        for a in sorted(plan.line_actions, key=lambda a: (a["trailer"], a["section"], str(a["row"]))):
            w.writerow({k: a.get(k, "") for k in PLAN_FIELDS})

    with open(out_dir / "excluded_scope.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["class", "sheet", "row", "section", "desc_old", "desc_new",
                    "price_old", "price_new", "note"])
        for r in refused:
            w.writerow(["REFUSED (Michael's ruling)", r["sheet"], r["row"], r["section"],
                        r["desc_old"], r["desc_new"], r["price_old"], r["price_new"], ""])
        for r in unmapped:
            w.writerow(["UNMAPPED SHEET (falls away)", r["sheet"], r["row"], r["section"],
                        r["desc_old"], r["desc_new"], r["price_old"], r["price_new"],
                        "no MES body for AELER PANELS"])
        for r in unmatched:
            w.writerow(["UNMATCHED (no line found)", r["sheet"], r["row"], r["section"],
                        r["desc_old"], r["desc_new"], r["price_old"], r["price_new"],
                        "reported, never guessed (default 2)"])
        for r in ambiguous:
            w.writerow(["AMBIGUOUS (multiple lines)", r["sheet"], r["row"], r["section"],
                        r["desc_old"], r["desc_new"], r["price_old"], r["price_new"],
                        "reported, never guessed (default 2)"])
        for r in no_action:
            klass = ("HIGHLIGHT-ONLY" if r["highlighted"] == "True"
                     and r["total_changed"] == "False" else "TOTAL-ONLY (derived)")
            w.writerow([klass, r["sheet"], r["row"], r["section"],
                        r["desc_old"], r["desc_new"], r["price_old"], r["price_new"], ""])

    with open(out_dir / "review_rows.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "row", "section", "desc_old", "desc_new",
                    "price_old", "price_new", "reason"])
        for r in plan.review:
            w.writerow([r.get("sheet", ""), r.get("row", ""), r.get("section", ""),
                        r.get("desc_old", ""), r.get("desc_new", ""),
                        r.get("price_old", ""), r.get("price_new", ""), r["reason"]])

    touched = {a["bom_id"] for a in plan.line_actions}
    with open(out_dir / "override_survivors.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trailer", "section", "material", "override_price",
                    "material_price", "bom_id"])
        for b in sorted(db.bom.values(),
                        key=lambda b: (db.trailers[b["trailer_type_id"]]["name"] if b["trailer_type_id"] in db.trailers else "?",
                                       b["bom_section"] or "", b["id"])):
            if b["trailer_type_id"] not in in_scope_tids or b["id"] in touched:
                continue
            if b["unit_price_override"] is None:
                continue
            m = db.materials[b["material_id"]]
            w.writerow([db.trailers[b["trailer_type_id"]]["name"], b["bom_section"] or "",
                        m["name"], b["unit_price_override"], m["price_per_unit"], b["id"]])


# ── backup ───────────────────────────────────────────────────────────────────

def backup_tables(conn, out_dir: Path, tag: str):
    bdir = out_dir / "backups" / tag
    bdir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for t in TABLES_WRITTEN:
        rows = conn.execute(sa.text(f"SELECT * FROM {t} ORDER BY id")).mappings().all()
        p = bdir / f"{t}.csv"
        with open(p, "w", newline="", encoding="utf-8") as fh:
            if rows:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for r in rows:
                    w.writerow(dict(r))
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest[t] = {"rows": len(rows), "sha256": h}
    (bdir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return bdir, manifest


# ── apply ────────────────────────────────────────────────────────────────────

def apply_plan(conn, db: Db, plan: Plan, out_dir: Path, env_tag: str):
    batch = datetime.now(timezone.utc)
    ts = batch.strftime("%Y%m%dT%H%M%SZ")
    journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE, "env": env_tag,
               "materials_created": [], "materials_inplace": [], "lines": [],
               "price_history_ids": [], "override_history_ids": [], "factor": None}

    # 1. create SPLIT target materials
    created_ids = {}
    for idx, rec in enumerate(plan.mat_creates):
        mid = conn.execute(sa.text("""
            INSERT INTO materials (name, category_id, unit_of_measure, price_per_unit,
                                   supplier, material_code, sap_code, size,
                                   manufacture_sub_category, is_active, last_updated,
                                   last_bulk_update_at, last_bulk_update_note)
            VALUES (:name, :category_id, :unit_of_measure, :price_per_unit, :supplier,
                    :material_code, :sap_code, :size, :manufacture_sub_category,
                    TRUE, :now, :now, :note)
            RETURNING id"""),
            {**{k: rec[k] for k in ("name", "category_id", "unit_of_measure",
                                    "price_per_unit", "supplier", "material_code",
                                    "sap_code", "size", "manufacture_sub_category")},
             "now": batch, "note": BATCH_NOTE}).scalar()
        created_ids[idx] = mid
        journal["materials_created"].append({"id": mid, **{k: rec[k] for k in rec}})

    # 2. in-place material updates
    for mid, st in plan.mat_inplace.items():
        m = db.materials[mid]
        before = {k: m[k] for k in ("name", "price_per_unit")}
        pre = conn.execute(sa.text(
            "SELECT last_updated, last_bulk_update_at, last_bulk_update_note "
            "FROM materials WHERE id=:i"), {"i": mid}).mappings().one()
        conn.execute(sa.text("""
            UPDATE materials SET name=:n, price_per_unit=:p, last_updated=:now,
                   last_bulk_update_at=:now, last_bulk_update_note=:note
            WHERE id=:i"""),
            {"n": st["name"], "p": st["price"], "now": batch, "note": BATCH_NOTE, "i": mid})
        if not approx(before["price_per_unit"] or 0, st["price"] or 0, 1e-12):
            phid = conn.execute(sa.text("""
                INSERT INTO price_history (material_id, old_price, new_price, changed_date, changed_by)
                VALUES (:m, :o, :n, :now, :who) RETURNING id"""),
                {"m": mid, "o": before["price_per_unit"], "n": st["price"],
                 "now": batch, "who": CHANGED_BY}).scalar()
            journal["price_history_ids"].append(phid)
        journal["materials_inplace"].append({
            "id": mid, "before": {**before, **{k: (pre[k].isoformat() if hasattr(pre[k], "isoformat") and pre[k] else pre[k]) for k in pre.keys()}},
            "after": {"name": st["name"], "price_per_unit": st["price"]}})

    # 3. line actions
    for a in plan.line_actions:
        b = db.bom[a["bom_id"]]
        before = {"material_id": b["material_id"],
                  "unit_price_override": b["unit_price_override"]}
        after_mid = a["material_after"]
        if isinstance(after_mid, str) and after_mid.startswith("NEW#"):
            after_mid = created_ids[int(after_mid[4:])]
        conn.execute(sa.text("""
            UPDATE bill_of_materials
               SET material_id=:m, unit_price_override=:o, price_updated_at=:now
             WHERE id=:i"""),
            {"m": after_mid, "o": a["override_after"], "now": batch, "i": a["bom_id"]})
        # journal override movement (reset, PU write, or rescale) for the admin trail
        if (a["override_before"] is not None or a["override_after"] is not None) \
                and a["override_before"] != a["override_after"]:
            ohid = conn.execute(sa.text("""
                INSERT INTO bom_override_history
                    (bom_id, material_id, trailer_type_id, trailer_type_name,
                     material_name, old_price, new_price, changed_at, batch_at)
                VALUES (:b, :m, :t, :tn, :mn, :o, :n, :now, :batch) RETURNING id"""),
                {"b": a["bom_id"], "m": after_mid, "t": a["trailer_id"],
                 "tn": a["trailer"], "mn": a["desc_after"],
                 "o": a["override_before"], "n": a["override_after"],
                 "now": batch, "batch": batch}).scalar()
            journal["override_history_ids"].append(ohid)
        journal["lines"].append({"bom_id": a["bom_id"], "before": before,
                                 "after": {"material_id": after_mid,
                                           "unit_price_override": a["override_after"]},
                                 "kind": a["kind"]})

    # 4. touched materials that are targets of repoints also get the badge stamps
    target_mids = {j["after"]["material_id"] for j in journal["lines"]}
    target_mids -= set(plan.mat_inplace) | set(created_ids.values())
    stamped = []
    for mid in sorted(m for m in target_mids if m is not None):
        # only stamp when the line actually changed material or price — repoint targets
        pre = conn.execute(sa.text(
            "SELECT last_updated, last_bulk_update_at, last_bulk_update_note "
            "FROM materials WHERE id=:i"), {"i": mid}).mappings().one()
        touched_lines = [j for j in journal["lines"] if j["after"]["material_id"] == mid
                         and j["before"]["material_id"] != mid]
        if not touched_lines:
            continue
        conn.execute(sa.text(
            "UPDATE materials SET last_updated=:now, last_bulk_update_at=:now, "
            "last_bulk_update_note=:note WHERE id=:i"),
            {"now": batch, "note": BATCH_NOTE, "i": mid})
        stamped.append({"id": mid, "before": {k: (pre[k].isoformat() if hasattr(pre[k], "isoformat") and pre[k] else pre[k]) for k in pre.keys()}})
    journal["materials_stamped"] = stamped

    # 5. the 4G factor (ratified default 7)
    pre_factor = conn.execute(sa.text(
        "SELECT value, updated_at FROM admin_settings WHERE key=:k"),
        {"k": FACTOR_KEY}).mappings().one()
    conn.execute(sa.text(
        "UPDATE admin_settings SET value=:v, updated_at=:now WHERE key=:k"),
        {"v": repr(FACTOR_NEW), "now": batch, "k": FACTOR_KEY})
    journal["factor"] = {"key": FACTOR_KEY, "before": pre_factor["value"],
                        "before_updated_at": (pre_factor["updated_at"].isoformat()
                                              if pre_factor["updated_at"] else None),
                        "after": repr(FACTOR_NEW)}

    jpath = out_dir / f"apply_journal_{env_tag}_{ts}.json"
    jpath.write_text(json.dumps(journal, indent=2, default=str))
    return jpath, journal


# ── revert ───────────────────────────────────────────────────────────────────

def revert_journal(conn, jpath: Path):
    j = json.loads(jpath.read_text())
    # reverse order: factor, stamps, lines, in-place materials, creations
    conn.execute(sa.text(
        "UPDATE admin_settings SET value=:v, updated_at=:u WHERE key=:k"),
        {"v": j["factor"]["before"], "u": j["factor"].get("before_updated_at"),
         "k": j["factor"]["key"]})
    for s in j.get("materials_stamped", []):
        conn.execute(sa.text(
            "UPDATE materials SET last_updated=:lu, last_bulk_update_at=:lb, "
            "last_bulk_update_note=:ln WHERE id=:i"),
            {"lu": s["before"]["last_updated"], "lb": s["before"]["last_bulk_update_at"],
             "ln": s["before"]["last_bulk_update_note"], "i": s["id"]})
    for ln in j["lines"]:
        conn.execute(sa.text(
            "UPDATE bill_of_materials SET material_id=:m, unit_price_override=:o, "
            "price_updated_at=NULL WHERE id=:i"),
            {"m": ln["before"]["material_id"], "o": ln["before"]["unit_price_override"],
             "i": ln["bom_id"]})
    for m in j["materials_inplace"]:
        conn.execute(sa.text(
            "UPDATE materials SET name=:n, price_per_unit=:p, last_updated=:lu, "
            "last_bulk_update_at=:lb, last_bulk_update_note=:ln WHERE id=:i"),
            {"n": m["before"]["name"], "p": m["before"]["price_per_unit"],
             "lu": m["before"]["last_updated"], "lb": m["before"]["last_bulk_update_at"],
             "ln": m["before"]["last_bulk_update_note"], "i": m["id"]})
    for ph in j["price_history_ids"]:
        conn.execute(sa.text("DELETE FROM price_history WHERE id=:i"), {"i": ph})
    for oh in j["override_history_ids"]:
        conn.execute(sa.text("DELETE FROM bom_override_history WHERE id=:i"), {"i": oh})
    for mc in j["materials_created"]:
        n = conn.execute(sa.text(
            "SELECT COUNT(*) FROM bill_of_materials WHERE material_id=:i"),
            {"i": mc["id"]}).scalar()
        if n:
            raise SystemExit(f"revert: created material {mc['id']} still referenced by {n} lines "
                             f"— journal does not cover them; aborting (nothing committed).")
        conn.execute(sa.text("DELETE FROM materials WHERE id=:i"), {"i": mc["id"]})
    return j


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="September 2026 price/description import (v1.52)")
    ap.add_argument("--manifest")
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default="docs/audit/september_price_update")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="JOURNAL_JSON")
    ap.add_argument("--env-tag", default="dev", help="labels backups + journal (dev/prod)")
    args = ap.parse_args()

    if not args.db:
        raise SystemExit("no DATABASE_URL (env or --db) — refusing to guess a database.")
    out_dir = Path(args.out_dir)
    eng = sa.create_engine(args.db)

    if args.revert:
        with eng.begin() as conn:
            bdir, _ = backup_tables(conn, out_dir, f"pre_revert_{args.env_tag}_"
                                    + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            j = revert_journal(conn, Path(args.revert))
        print(f"reverted journal {args.revert} ({len(j['lines'])} lines, "
              f"{len(j['materials_inplace'])} in-place materials, "
              f"{len(j['materials_created'])} created materials removed). Backup: {bdir}")
        return 0

    if not args.manifest:
        raise SystemExit("--manifest is required for dry-run/apply")

    in_scope, refused, unmapped = load_manifest(args.manifest)
    in_scope_tids = set(SHEET_TO_TRAILER.values())

    with eng.begin() as conn:
        db = Db(conn)
        matched, unmatched, ambiguous, no_action = match_rows(db, in_scope)
        plan = build_plan(db, matched, in_scope_tids)
        write_reports(plan, db, refused, unmapped, unmatched, ambiguous,
                      no_action, out_dir, in_scope_tids)

        kinds = Counter(a["kind"] for a in plan.line_actions)
        disp = Counter(a["mat_disposition"] for a in plan.line_actions)
        resets = sum(1 for a in plan.line_actions if a["override_reset"])
        print(f"manifest: {len(in_scope)} in-scope rows "
              f"({len(refused)} refused by ruling, {len(unmapped)} unmapped AELER)")
        print(f"plan: {len(plan.line_actions)} line actions {dict(kinds)}")
        print(f"      material dispositions {dict(disp)}; "
              f"{len(plan.mat_inplace)} in-place materials, {len(plan.mat_creates)} created")
        print(f"      override resets: {resets}; review rows: {len(plan.review)}; "
              f"unmatched: {len(unmatched)}; ambiguous: {len(ambiguous)}")
        print(f"      4G factor: {FACTOR_KEY} -> {FACTOR_NEW!r}")
        print(f"reports written to {out_dir}/")

        if not args.apply:
            print("\n(DRY RUN — nothing written. Re-run with --apply to commit.)")
            return 0

        # One-shot guard: after an apply the OLD descriptions are gone, so a
        # second --apply would mostly mis-plan (unmatched rows) while
        # re-stamping every badge. A revert restores applyability.
        already = conn.execute(sa.text(
            "SELECT COUNT(*) FROM materials WHERE last_bulk_update_note = :n "
            "AND last_bulk_update_at > now() - interval '7 days'"),
            {"n": BATCH_NOTE}).scalar()
        if already:
            raise SystemExit(
                f"REFUSED: {already} materials already carry the '{BATCH_NOTE}' "
                f"stamp from the last 7 days — this apply has already run. "
                f"To redo it, --revert the journal first.")

        bdir, bman = backup_tables(conn, out_dir, f"pre_apply_{args.env_tag}_"
                                   + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        print(f"backup: {bdir} " + ", ".join(f"{t}={bman[t]['rows']}" for t in TABLES_WRITTEN))
        jpath, journal = apply_plan(conn, db, plan, out_dir, args.env_tag)
        print(f"APPLIED. journal: {jpath}")
        print(f"  lines={len(journal['lines'])}, in-place mats={len(journal['materials_inplace'])}, "
              f"created mats={len(journal['materials_created'])}, "
              f"price_history={len(journal['price_history_ids'])}, "
              f"override_history={len(journal['override_history_ids'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
