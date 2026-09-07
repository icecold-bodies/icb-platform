r"""
tools/icecream_reardoor_thickness.py
────────────────────────────────────
Sync the icecream bodies' REAR-DOOR insulation thickness to Burt's September
sheets (Michael, 7 Sep — after the Medium body quoted DRD PU at half cost).

The rear-door invariant (calculator.js:640-647): a body is quoted as EITHER
DRD (double) OR SRD (single), never both. ONE rear-door thickness follows the
door choice — the selected door carries it, the other is ZERO. The calculator
rewrites these template values on every door/EPS-PU toggle, and its fallback is
DEFAULT_REAR_DOOR_THICKNESS_M = 0.06, which is how a body drifts off the sheet.

Truth comes from the workbook's INPUT cells, read live:
    C10/D10 DRD EPS   C11/D11 DRD PU
    C12/D12 SRD EPS   C13/D13 SRD PU
⚠ NEVER trust the workbook's cached H/G/I results here — this file's cached
results are stale relative to its inputs (Excel recalculates on open, openpyxl
does not). The C/D input cells are authoritative; that stale cache is exactly
what made row 78 look inactive while Michael's screen showed it live.

Per body the tool sets, for the rear-door pair only:
  * the door the sheet marks 'Y'  → PU thickness = that door's sheet C-value,
                                    body_option_default = True
  * the other door                → PU thickness 0, default False
  * both EPS siblings             → 0 (the sheets run these bodies on PU)
Non-rear-door pairs (FRONT/SIDES/ROOF/FLOOR) are CHECKED and REPORTED but never
written — they were verified in agreement with the sheets on 7 Sep.

Modes: dry-run (default) / --apply (journaled) / --revert J.json / --verify.
Delta-driven and idempotent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

BATCH_NOTE = "September 2026 — icecream rear-door insulation thickness sync"

WORKBOOK = os.environ.get(
    "GRP_PATH",
    r"C:\Users\micge\Documents\Burt Costing Model\September costings\GRP Costings 2018.xlsx")

#: trailer_id -> workbook sheet name (the §3.0 mapping, icecream family only)
SHEETS = {16: "icecream up to 3,2", 17: "icecream up to 4.8", 18: " icecream 4.9 up"}

#: option name -> (thickness cell row, toggle cell row) in the options block
OPTION_ROWS = {
    "FRONT EPS": 8, "FRONT PU": 9,
    "DRD EPS": 10, "DRD PU": 11,
    "SRD EPS": 12, "SRD PU": 13,
    "SIDES EPS": 14, "SIDES PU": 15,
    "ROOF EPS": 16, "ROOF PU": 17,
    "FLOOR EPS": 18, "FLOOR PU": 19,
}
REAR_DOOR_NAMES = ("DRD EPS", "DRD PU", "SRD EPS", "SRD PU")
TOL = 1e-9


def read_sheet_truth() -> dict:
    """{tid: {option_name: (thickness, is_yes)}} from the workbook INPUT cells."""
    from openpyxl import load_workbook
    wb = load_workbook(WORKBOOK, data_only=True)
    out = {}
    for tid, sheet in SHEETS.items():
        if sheet not in wb.sheetnames:
            raise SystemExit(f"sheet {sheet!r} not found in {WORKBOOK}")
        ws = wb[sheet]
        vals = {}
        for name, row in OPTION_ROWS.items():
            a = ws[f"A{row}"].value
            if not (isinstance(a, str) and a.strip().upper() == name):
                raise SystemExit(
                    f"{sheet!r} row {row}: expected {name!r} in column A, found {a!r} — "
                    f"the options block has moved; refusing to guess.")
            c = ws[f"C{row}"].value
            d = ws[f"D{row}"].value
            thickness = float(c) if isinstance(c, (int, float)) else 0.0
            is_yes = isinstance(d, str) and d.strip().upper() == "Y"
            vals[name] = (thickness, is_yes)
        out[tid] = vals
    wb.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="JOURNAL_JSON")
    ap.add_argument("--truth-json", metavar="FILE",
                    help="sheet truth exported by --export-truth; for hosts without "
                         "the workbook (the prod VM). Keeps prod from ever reading a "
                         "stale or absent sheet.")
    ap.add_argument("--export-truth", metavar="FILE",
                    help="read the workbook, write the sheet truth to FILE, exit")
    ap.add_argument("--all-pairs", action="store_true",
                    help="also sync FRONT/SIDES/ROOF/FLOOR insulation pairs to the "
                         "sheet (default: rear-door DRD/SRD pair only, others "
                         "reported)")
    args = ap.parse_args()

    if args.export_truth:
        t = read_sheet_truth()
        Path(args.export_truth).write_text(json.dumps(
            {str(k): {n: list(v) for n, v in vals.items()} for k, vals in t.items()},
            indent=2))
        print(f"sheet truth -> {args.export_truth}")
        for tid, vals in t.items():
            door = [n for n in ("DRD PU", "SRD PU") if vals[n][1]]
            print(f"  tid {tid} {SHEETS[tid]!r}: rear door {door or ['-']} "
                  f"@ {vals[door[0]][0] if door else '-'}")
        return 0

    if not args.db:
        raise SystemExit("no DATABASE_URL — refusing to guess a database.")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    eng = sa.create_engine(args.db)

    if args.revert:
        with eng.begin() as conn:
            j = json.loads(Path(args.revert).read_text())
            for r in j["rows"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET variable_value=:v, "
                    "body_option_default=:d WHERE id=:i"),
                    {"v": r["before"]["variable_value"],
                     "d": r["before"]["body_option_default"], "i": r["bom_id"]})
        print(f"reverted {args.revert} ({len(j['rows'])} rows)")
        return 0

    if args.truth_json:
        raw = json.loads(Path(args.truth_json).read_text())
        truth = {int(k): {n: (float(v[0]), bool(v[1])) for n, v in vals.items()}
                 for k, vals in raw.items()}
        missing = set(SHEETS) - set(truth)
        if missing:
            raise SystemExit(f"--truth-json is missing trailer ids {sorted(missing)}")
        for tid, vals in truth.items():
            absent = set(OPTION_ROWS) - set(vals)
            if absent:
                raise SystemExit(f"--truth-json tid {tid} missing options {sorted(absent)}")
        print(f"sheet truth from {args.truth_json}")
    else:
        truth = read_sheet_truth()
    with eng.begin() as conn:
        deltas, reports, problems = [], [], []
        for tid, sheet in SHEETS.items():
            tname = conn.execute(sa.text("SELECT name FROM trailer_types WHERE id=:t"),
                                 {"t": tid}).scalar()
            if tname is None:
                problems.append(f"trailer {tid} not found — skipped")
                continue
            rows = conn.execute(sa.text("""
                SELECT b.id, m.name, b.variable_value, b.body_option_default
                FROM bill_of_materials b JOIN materials m ON m.id=b.material_id
                WHERE b.trailer_type_id=:t AND b.is_body_option
                  AND b.body_option_subgroup='INSULATION'"""),
                {"t": tid}).mappings().all()
            by_name = {}
            for r in rows:
                nm = (r["name"] or "").strip().upper()
                by_name.setdefault(nm, []).append(r)

            # which door does the sheet quote?
            sheet_vals = truth[tid]
            doors_yes = [n for n in ("DRD PU", "SRD PU") if sheet_vals[n][1]]
            if len(doors_yes) != 1:
                problems.append(f"{tname!r}: sheet marks {len(doors_yes)} rear doors 'Y' "
                                f"({doors_yes}) — refused, a body is one door or the other")
                continue
            door = doors_yes[0]                      # e.g. 'DRD PU'
            other = "SRD PU" if door == "DRD PU" else "DRD PU"
            thickness = sheet_vals[door][0]
            if thickness <= 0:
                problems.append(f"{tname!r}: sheet marks {door} 'Y' but its thickness is "
                                f"{thickness} — refused")
                continue

            targets = {door: (thickness, True), other: (0.0, False),
                       "DRD EPS": (0.0, False), "SRD EPS": (0.0, False)}

            # --all-pairs: the non-rear-door pairs too (FRONT/SIDES/ROOF/FLOOR).
            # These are not an either/or door choice — each is simply an EPS/PU
            # pair whose 'Y' side the sheet names. Prod's Medium body sat at
            # 0.12 on ROOF+FLOOR where the sheet says 0.145 (~17% under-cost).
            if args.all_pairs:
                for grp in ("FRONT", "SIDES", "ROOF", "FLOOR"):
                    eps_n, pu_n = f"{grp} EPS", f"{grp} PU"
                    yes = [n for n in (eps_n, pu_n) if sheet_vals[n][1]]
                    if len(yes) != 1:
                        problems.append(f"{tname!r} {grp}: sheet marks {len(yes)} sides 'Y' "
                                        f"({yes}) — refused, left untouched")
                        continue
                    chosen = yes[0]
                    unchosen = pu_n if chosen == eps_n else eps_n
                    want = sheet_vals[chosen][0]
                    if want <= 0:
                        problems.append(f"{tname!r} {grp}: sheet marks {chosen} 'Y' but its "
                                        f"thickness is {want} — refused, left untouched")
                        continue
                    targets[chosen] = (want, True)
                    targets[unchosen] = (0.0, False)
            for nm, (want_v, want_d) in targets.items():
                cands = by_name.get(nm, [])
                if len(cands) != 1:
                    problems.append(f"{tname!r}: {len(cands)} {nm!r} option rows — refused")
                    continue
                r = cands[0]
                cur_v = float(r["variable_value"] or 0.0)
                cur_d = bool(r["body_option_default"])
                if abs(cur_v - want_v) <= TOL and cur_d == want_d:
                    continue
                deltas.append({
                    "tid": tid, "tname": tname, "name": nm, "bom_id": r["id"],
                    "before_v": r["variable_value"], "after_v": want_v,
                    "before_d": cur_d, "after_d": want_d,
                    "sheet_door": door, "sheet_thickness": thickness,
                })
            # non-rear-door pairs: check + report only (skipped when --all-pairs
            # is syncing them for real)
            for nm, (want_v, is_yes) in sheet_vals.items():
                if args.all_pairs or nm in REAR_DOOR_NAMES or not nm.endswith(" PU"):
                    continue
                cands = by_name.get(nm, [])
                if len(cands) == 1:
                    cur = float(cands[0]["variable_value"] or 0.0)
                    if abs(cur - want_v) > TOL:
                        reports.append(f"{tname!r} {nm}: MES {cur} vs sheet {want_v} "
                                       f"— reported only, NOT changed (not a rear door)")

        print(f"rear-door thickness sync: {len(deltas)} deltas, "
              f"{len(reports)} other-pair notes, {len(problems)} refusals")
        for d in deltas:
            bits = []
            if abs(float(d["before_v"] or 0) - d["after_v"]) > TOL:
                bits.append(f"thickness {d['before_v']} -> {d['after_v']}")
            if d["before_d"] != d["after_d"]:
                bits.append(f"default {d['before_d']} -> {d['after_d']}")
            print(f"  bom={d['bom_id']:<6} {d['tname']!r} {{{d['name']}}}: " + ", ".join(bits)
                  + f"   (sheet quotes {d['sheet_door']} @ {d['sheet_thickness']})")
        for r in reports:
            print(f"  NOTE: {r}")
        for p in problems:
            print(f"  REFUSED: {p}")

        if not args.apply:
            print("(DRY RUN — nothing written. --apply to commit.)")
            return 0
        if not deltas:
            print("nothing to apply.")
            return 0

        batch = datetime.now(timezone.utc)
        journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE, "rows": []}
        for d in deltas:
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET variable_value=:v, body_option_default=:d "
                "WHERE id=:i"),
                {"v": d["after_v"], "d": d["after_d"], "i": d["bom_id"]})
            journal["rows"].append({
                "bom_id": d["bom_id"], "trailer": d["tname"], "name": d["name"],
                "before": {"variable_value": d["before_v"],
                           "body_option_default": d["before_d"]},
                "after": {"variable_value": d["after_v"],
                          "body_option_default": d["after_d"]}})
        ts = batch.strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"reardoor_thickness_journal_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str))
        print(f"APPLIED. rows={len(journal['rows'])}, journal: {jpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
