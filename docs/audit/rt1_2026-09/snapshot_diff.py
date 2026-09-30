"""RT1 — what moved in prod's pricing between two costing-audit snapshots (no database).

    python snapshot_diff.py <old all.json> <new all.json> [--ignore-col price_updated_at ...]

Per table: rows added / removed / changed (by primary key `id`, or the whole row for id-less tables), and for each
changed row the columns that changed, old -> new. Pricing definitions only (the snapshots carry nothing else).
"""
import argparse
import json
from pathlib import Path


def rows_by_key(rows):
    out = {}
    for r in rows:
        k = r.get("id")
        if k is None:
            k = json.dumps(r, sort_keys=True)
        out[k] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--ignore-col", action="append", default=[])
    a = ap.parse_args()
    old = json.loads(Path(a.old).read_text(encoding="utf-8"))
    new = json.loads(Path(a.new).read_text(encoding="utf-8"))
    print(f"old {Path(a.old).name} generated {old.get('generated_at')} · new {Path(a.new).name} generated {new.get('generated_at')}")
    if old.get("trailer_ids") != new.get("trailer_ids"):
        print(f"!! trailer ids differ: {old.get('trailer_ids')} -> {new.get('trailer_ids')}")
    names = {r["id"]: r["name"] for r in new["tables"].get("trailer_types", []) + old["tables"].get("trailer_types", [])}
    mats = {r["id"]: r["name"] for r in new["tables"].get("materials", []) + old["tables"].get("materials", [])}
    total = 0
    for t in sorted(set(old["tables"]) | set(new["tables"])):
        o, n = rows_by_key(old["tables"].get(t, [])), rows_by_key(new["tables"].get(t, []))
        added, removed = sorted(set(n) - set(o), key=str), sorted(set(o) - set(n), key=str)
        changed = []
        for k in sorted(set(o) & set(n), key=str):
            cols = [c for c in sorted(set(o[k]) | set(n[k])) if c not in a.ignore_col and o[k].get(c) != n[k].get(c)]
            if cols:
                changed.append((k, cols))
        if not (added or removed or changed):
            continue
        total += len(added) + len(removed) + len(changed)
        print(f"\n## {t}: +{len(added)} added, -{len(removed)} removed, ~{len(changed)} changed")
        for k in added[:20]:
            print(f"   + {k}")
        for k in removed[:20]:
            print(f"   - {k}")
        for k, cols in changed:
            r = n[k]
            where = ""
            if t == "bill_of_materials":
                where = f" [{names.get(r.get('trailer_type_id'))} / {r.get('bom_section')} / {mats.get(r.get('material_id'))}]"
            elif t in ("materials", "trailer_types"):
                where = f" [{r.get('name')}]"
            print(f"   ~ {k}{where}: " + "; ".join(f"{c} {o[k].get(c)!r} -> {r.get(c)!r}" for c in cols))
    print(f"\n{total} row-level differences")


if __name__ == "__main__":
    main()
