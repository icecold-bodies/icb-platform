"""RT1 — compare two sets of costing-audit report JSONs cell by cell (no database).

A cell is keyed by (pack, scenario_id, section_excel, section_mes). Two cells are IDENTICAL when status, Excel total,
MES total (both to the cent) and the accepted entry's reason agree. Used for:

  mirror = prod     the mirror's five packs (v1.59.2 engine, 1b snapshot) vs prod's 1b reference run (v1.59.0 engine)
  proof A           the mirror before vs after Manifest A: the SRD REAR FRAME cells move, every other cell must not
  proof B           after A vs after B: only the cells that price Manifest B's lines may move

    python compare_reports.py <dir-before> <dir-after> [--moved-ok srd-rear-frame|b-lines] [--list N]

Report files: <dir>/*<pack>.json for the packs smoke chillers freezers icecream explosive (one per pack per dir).
"""
import argparse
import json
import sys
from pathlib import Path

PACKS = ("smoke", "chillers", "freezers", "icecream", "explosive")
RF = {"REAR FRAME + FLOOR PLATE", "REAR FRAME & FLOOR PLATE"}
SRD_VARIANTS = {"srd", "srd_pu"}


def load(d: Path) -> dict:
    cells = {}
    for p in PACKS:
        files = sorted(f for f in d.glob(f"*{p}.json") if not f.name.endswith(".prov.json"))
        if len(files) != 1:
            raise SystemExit(f"{d}: expected exactly one *{p}.json, found {[f.name for f in files]}")
        doc = json.loads(files[0].read_text(encoding="utf-8"))
        for c in doc["cells"]:
            # keyed by the EXCEL section (the golden side never moves); the MES section only when Excel has none.
            # A section whose every line is excluded drops out of MES's totals, so its cell's section_mes goes
            # from the name to None (status SKIP when Burt is R0): the same cell, not a new one.
            se = c.get("section_excel")
            k = (p, c["scenario_id"], se, None if se is not None else c.get("section_mes"))
            if k in cells:
                raise SystemExit(f"{files[0].name}: duplicate cell key {k}")
            cells[k] = c
    return cells


def cents(v):
    return None if v is None else round(float(v), 2)


def same(a: dict, b: dict) -> list[str]:
    diff = []
    for f in ("status", "section_mes"):
        if a.get(f) != b.get(f):
            diff.append(f"{f} {a.get(f)} -> {b.get(f)}")
    for f in ("excel_total", "mes_total"):
        if cents(a.get(f)) != cents(b.get(f)):
            diff.append(f"{f} {cents(a.get(f))} -> {cents(b.get(f))}")
    ra = (a.get("accepted") or {}).get("reason")
    rb = (b.get("accepted") or {}).get("reason")
    if ra != rb:
        diff.append("accepted reason changed" if ra and rb else f"accepted {'added' if rb else 'dropped'}")
    return diff


def is_srd_rear_frame(c: dict) -> bool:
    return c.get("variant") in SRD_VARIANTS and ({c.get("section_excel"), c.get("section_mes")} & RF)


B_BODIES = {19: "FREEZER 2.3 METER", 20: "FREEZER MEDIUM", 17: "ICECREAM BODY MEDIUM"}   # Manifest B lines in a pack


def is_b_line_cell(c: dict) -> bool:
    """A cell that prices one of Manifest B's lines: the SRD section of a B body under an SRD PU variant."""
    return c.get("trailer_id") in B_BODIES and "SRD" in {c.get("section_excel"), c.get("section_mes")} \
        and c.get("variant") in ("srd_pu", "all_pu", "srd")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--moved-ok", choices=("srd-rear-frame", "b-lines"), default=None)
    ap.add_argument("--list", type=int, default=40)
    a = ap.parse_args()
    b4, af = load(Path(a.before)), load(Path(a.after))
    only_b4, only_af = sorted(set(b4) - set(af)), sorted(set(af) - set(b4))
    moved, unexpected, identical = [], [], 0
    allowed = {"srd-rear-frame": is_srd_rear_frame, "b-lines": is_b_line_cell}.get(a.moved_ok, lambda c: False)
    in_scope = 0
    for k in sorted(set(b4) & set(af)):
        d = same(b4[k], af[k])
        scope = allowed(af[k])
        in_scope += bool(scope)
        if not d:
            identical += 1
        elif scope:
            moved.append((k, d, b4[k], af[k]))
        else:
            unexpected.append((k, d, b4[k], af[k]))
    total = len(set(b4) & set(af))
    print(f"before {a.before}: {len(b4)} cells · after {a.after}: {len(af)} cells · common {total}")
    print(f"identical {identical} · moved in scope ({a.moved_ok or 'none allowed'}) {len(moved)} of {in_scope} in scope · "
          f"UNEXPECTED {len(unexpected)} · only before {len(only_b4)} · only after {len(only_af)}")
    out_of_scope = total - in_scope
    print(f"cells outside the allowed scope: {out_of_scope}, identical to the cent: {out_of_scope - len(unexpected)}")
    for title, rows in (("MOVED (allowed)", moved), ("UNEXPECTED", unexpected)):
        if rows:
            print(f"\n{title}:")
            for (p, sid, se, sm), d, x, y in rows[: a.list]:
                print(f"  {p:<9} {sid:<44} {se or sm or '-':<26} {'; '.join(d)}")
            if len(rows) > a.list:
                print(f"  … {len(rows) - a.list} more")
    for title, ks in (("ONLY BEFORE", only_b4), ("ONLY AFTER", only_af)):
        if ks:
            print(f"\n{title}: {len(ks)}", ks[:10])
    ok = not unexpected and not only_b4 and not only_af
    print("\nRESULT:", "OK" if ok else "!! DIFFERENCES OUTSIDE THE ALLOWED SCOPE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
