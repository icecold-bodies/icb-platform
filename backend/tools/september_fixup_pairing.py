r"""
tools/september_fixup_pairing.py
────────────────────────────────
Post-apply correction for the v1.52 September import's pairing shift (prod,
4 Sep 2026). Self-contained: reads the manifest + the live DB, re-derives the
SECTION-TRUE pairing for every (sheet, old-name) group, and emits only the
DELTAS between what each line holds now and what its own manifest row says.

What went wrong in the main import: when a group had fewer name-matching lines
than manifest rows (prod's FRONT skins carry legacy variant names like
"EXT GRP SKIN 2*300 GLOSS CRYSTEX V2"), rows were zip-paired in order, shifting
every pairing one section down. Values were right wherever the group was
homogeneous; the audit found 3 name-swaps + 1 price error, and ~21 variant-named
lines got nothing at all.

This tool:
  * pairs each manifest row to lines by EXACT section, matching a line when its
    current name is the row's OLD name, its NEW name (already updated), or a
    VARIANT that contains the old name (the CRYSTEX class);
  * computes the required (name, price) per line from ITS OWN row — never a
    neighbour's;
  * `--crystex-mode price-only` (recommended) keeps a variant line's prod name
    and applies only the September price; `--crystex-mode rename` gives variant
    lines the manifest's new name too (Burt's sheet literally);
  * anything that does not resolve to exactly one line per row (or one row per
    line) is REPORTED, never guessed;
  * delta-driven, so a second run is a no-op; --apply is one transaction,
    journaled, and --revert replays the journal byte-exact (0046 pattern).

Usage (on the VM, same env pattern as the import):
    ... python tools/september_fixup_pairing.py --manifest ../docs/audit/september_price_update/september_change_manifest.csv --out-dir /var/backups/icb-september-2026/fixup [--crystex-mode price-only] [--apply | --revert J.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

BATCH_NOTE = "September 2026 price update — pairing fixup"
PRICE_TOL = 0.01
PU_NAMES = {"PU", "PU FOAM"}

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
REFUSED_SHEETS = {"Manni RIGIDS CB", "Manni RIGIDS FB", "Manni Bakkie Rigids",
                  "Manni TRAILERS", "Manni DF", "Sheet1"}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").upper().strip())


def fnum(s):
    s = (s or "").strip() if isinstance(s, str) else s
    if s in (None, ""):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=False)
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--crystex-mode", choices=["price-only", "rename"], default="price-only")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="JOURNAL_JSON")
    args = ap.parse_args()
    if not args.db:
        raise SystemExit("no DATABASE_URL — refusing to guess a database.")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    eng = sa.create_engine(args.db)

    if args.revert:
        with eng.begin() as conn:
            j = json.loads(Path(args.revert).read_text())
            for ln in j["lines"]:
                conn.execute(sa.text(
                    "UPDATE bill_of_materials SET material_id=:m, unit_price_override=:o, "
                    "price_updated_at=:t WHERE id=:i"),
                    {"m": ln["before"]["material_id"], "o": ln["before"]["unit_price_override"],
                     "t": ln["before"]["price_updated_at"], "i": ln["bom_id"]})
            for oh in j["override_history_ids"]:
                conn.execute(sa.text("DELETE FROM bom_override_history WHERE id=:i"), {"i": oh})
            for mc in j["materials_created"]:
                n = conn.execute(sa.text(
                    "SELECT COUNT(*) FROM bill_of_materials WHERE material_id=:i"),
                    {"i": mc["id"]}).scalar()
                if n:
                    raise SystemExit(f"revert: created material {mc['id']} still referenced ({n}) — abort")
                conn.execute(sa.text("DELETE FROM materials WHERE id=:i"), {"i": mc["id"]})
        print(f"reverted {args.revert}")
        return 0

    if not args.manifest:
        raise SystemExit("--manifest required")

    man = [r for r in csv.DictReader(open(args.manifest, encoding="utf-8-sig"))
           if r["sheet"] not in REFUSED_SHEETS and r["sheet"] in SHEET_TO_TRAILER
           and (r["price_changed"] == "True" or r["desc_changed"] == "True")]
    groups = defaultdict(list)
    for r in man:
        groups[(r["sheet"], norm(r["desc_old"]))].append(r)

    with eng.begin() as conn:
        mats = {r.id: dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT id, name, category_id, unit_of_measure, price_per_unit, supplier, "
            "material_code, sap_code, size, manufacture_sub_category, is_active FROM materials"))}
        bom = [dict(r._mapping) for r in conn.execute(sa.text(
            "SELECT b.id, b.trailer_type_id, b.material_id, b.bom_section, b.sort_order, "
            "b.unit_price_override, b.price_updated_at "
            "FROM bill_of_materials b WHERE NOT COALESCE(b.is_body_option, FALSE)"))]
        by_tt = defaultdict(list)
        for b in bom:
            by_tt[b["trailer_type_id"]].append(b)

        def eff(b):
            return b["unit_price_override"] if b["unit_price_override"] is not None \
                else mats[b["material_id"]]["price_per_unit"]

        deltas, reports = [], []
        for (sheet, gname), rows in sorted(groups.items()):
            if gname in PU_NAMES:
                continue  # PU pairing was per-line-rule-driven and audited clean
            tid = SHEET_TO_TRAILER[sheet]
            tlines = by_tt.get(tid, [])
            # candidate lines for this group: exact old name, any of the new
            # names, or a variant containing the old name
            new_names = {norm(r["desc_new"]) for r in rows if r["desc_new"].strip()}
            cands = [b for b in tlines
                     if norm(mats[b["material_id"]]["name"]) == gname
                     or norm(mats[b["material_id"]]["name"]) in new_names
                     or gname in norm(mats[b["material_id"]]["name"])]
            # pair per section, in row/sort order within a section
            rows_by_sec = defaultdict(list)
            for r in sorted(rows, key=lambda r: int(r["row"])):
                rows_by_sec[norm(r["section"])].append(r)
            cands_by_sec = defaultdict(list)
            for b in sorted(cands, key=lambda b: (b["sort_order"] or 0, b["id"])):
                cands_by_sec[norm(b["bom_section"] or "")].append(b)
            for sec, srows in rows_by_sec.items():
                slines = cands_by_sec.get(sec, [])
                if len(slines) != len(srows):
                    reports.append(f"{sheet!r} {gname!r} section {sec!r}: "
                                   f"{len(srows)} manifest rows vs {len(slines)} lines — skipped")
                    continue
                for r, b in zip(srows, slines):
                    cur_name = mats[b["material_id"]]["name"]
                    is_variant = (norm(cur_name) != gname
                                  and norm(cur_name) not in new_names)
                    want_name = (r["desc_new"].strip() or r["desc_old"].strip())
                    if is_variant and args.crystex_mode == "price-only":
                        want_name = cur_name
                    # price_changed rows carry the September price; desc-only
                    # rows keep the line's effective price (override survives,
                    # exactly like the main import's desc-only path)
                    want_price = fnum(r["price_new"]) if r["price_changed"] == "True" else None
                    name_ok = norm(cur_name) == norm(want_name)
                    price_ok = want_price is None or abs(eff(b) - want_price) <= PRICE_TOL
                    if name_ok and price_ok:
                        continue
                    deltas.append({
                        "sheet": sheet, "row": int(r["row"]), "section": sec,
                        "bom_id": b["id"], "trailer_id": tid,
                        "cur_name": cur_name, "want_name": want_name,
                        "cur_eff": eff(b), "want_price": want_price,
                        "override_before": b["unit_price_override"],
                        "variant": is_variant,
                        "b": b,
                    })

        print(f"fixup deltas: {len(deltas)}  (crystex-mode={args.crystex_mode}); "
              f"skipped/reported: {len(reports)}")
        for d in deltas:
            print(f"  bom={d['bom_id']:>5} {d['sheet'][:28]!r} {d['section']:<6} "
                  f"{d['cur_name'][:36]!r}@{round(d['cur_eff'], 2)} -> "
                  f"{d['want_name'][:36]!r}@{d['want_price']}"
                  f"{'  [VARIANT]' if d['variant'] else ''}")
        for msg in reports:
            print(f"  REPORT: {msg}")
        with open(out_dir / "fixup_plan.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["sheet", "row", "section", "bom_id", "cur_name", "want_name",
                        "cur_eff", "want_price", "variant"])
            for d in deltas:
                w.writerow([d["sheet"], d["row"], d["section"], d["bom_id"], d["cur_name"],
                            d["want_name"], d["cur_eff"], d["want_price"], d["variant"]])

        if not args.apply:
            print("(DRY RUN — nothing written. Re-run with --apply to commit.)")
            return 0
        if not deltas:
            print("nothing to apply.")
            return 0

        batch = datetime.now(timezone.utc)
        journal = {"batch_at": batch.isoformat(), "note": BATCH_NOTE,
                   "materials_created": [], "lines": [], "override_history_ids": []}
        pool = {}
        for mid in sorted(mats):
            m = mats[mid]
            key = (norm(m["name"]), round(m["price_per_unit"], 4) if m["price_per_unit"] is not None else None)
            if m["is_active"] and key not in pool:
                pool[key] = mid

        for d in deltas:
            b = d["b"]
            # desc-only delta: target material carries the CURRENT material's
            # price (the kept override still wins at read time) — importer parity
            want_price = d["want_price"] if d["want_price"] is not None \
                else mats[b["material_id"]]["price_per_unit"]
            key = (norm(d["want_name"]), round(want_price, 4))
            mid = pool.get(key)
            if mid is None:
                tpl = mats[b["material_id"]]
                mid = conn.execute(sa.text("""
                    INSERT INTO materials (name, category_id, unit_of_measure, price_per_unit,
                                           supplier, material_code, sap_code, size,
                                           manufacture_sub_category, is_active, last_updated,
                                           last_bulk_update_at, last_bulk_update_note)
                    VALUES (:n, :c, :u, :p, :s, :mc, :sc, :sz, :ms, TRUE, :now, :now, :note)
                    RETURNING id"""),
                    {"n": d["want_name"].strip(), "c": tpl["category_id"],
                     "u": tpl["unit_of_measure"], "p": want_price, "s": tpl["supplier"],
                     "mc": tpl["material_code"], "sc": tpl["sap_code"], "sz": tpl["size"],
                     "ms": tpl["manufacture_sub_category"], "now": batch,
                     "note": BATCH_NOTE}).scalar()
                pool[key] = mid
                journal["materials_created"].append({"id": mid, "name": d["want_name"],
                                                     "price": want_price})
            before = {"material_id": b["material_id"],
                      "unit_price_override": b["unit_price_override"],
                      "price_updated_at": (b["price_updated_at"].isoformat()
                                           if b["price_updated_at"] else None)}
            # a supplied September price replaces any standing override (default 3)
            new_override = None if d["want_price"] is not None else b["unit_price_override"]
            conn.execute(sa.text(
                "UPDATE bill_of_materials SET material_id=:m, unit_price_override=:o, "
                "price_updated_at=:now WHERE id=:i"),
                {"m": mid, "o": new_override, "now": batch, "i": d["bom_id"]})
            if b["unit_price_override"] is not None and new_override is None:
                ohid = conn.execute(sa.text("""
                    INSERT INTO bom_override_history
                        (bom_id, material_id, trailer_type_id, trailer_type_name,
                         material_name, old_price, new_price, changed_at, batch_at)
                    SELECT :b, :m, :t, t.name, :mn, :o, NULL, :now, :now
                      FROM trailer_types t WHERE t.id = :t RETURNING id"""),
                    {"b": d["bom_id"], "m": mid, "t": d["trailer_id"],
                     "mn": d["want_name"], "o": b["unit_price_override"],
                     "now": batch}).scalar()
                journal["override_history_ids"].append(ohid)
            journal["lines"].append({"bom_id": d["bom_id"], "before": before,
                                     "after": {"material_id": mid,
                                               "unit_price_override": new_override}})

        ts = batch.strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"fixup_journal_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str))
        print(f"APPLIED fixup. lines={len(journal['lines'])}, "
              f"created materials={len(journal['materials_created'])}, journal: {jpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
