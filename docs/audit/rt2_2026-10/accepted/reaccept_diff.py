"""RT2 Part 2 — prove an accepted-list change cell by cell (the RT1 "prune #5 alone, then reaccept" pattern).

    (PYTHONPATH = backend/)  python reaccept_diff.py <before.yaml> <after.yaml> <report.json>...

Re-applies BOTH lists to the same saved audit reports (no MES, no database: tools.costing_audit's own
reapply_accepted) and prints every cell whose status or accepted reason differs. An entry that is removed
must change 0 cells; an entry that is added must change exactly the cells it was written for.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from tools.costing_audit.accepted import load_accepted
from tools.costing_audit.compare import reapply_accepted


def statuses(doc: dict, accepted_path: Path) -> dict:
    rep = reapply_accepted(json.loads(json.dumps(doc)), load_accepted(accepted_path), note=accepted_path.name)
    cells = rep.cells if hasattr(rep, "cells") else rep["cells"]
    out = {}
    for c in cells:
        c = c if isinstance(c, dict) else c.__dict__
        acc = c.get("accepted")
        reason = (acc.get("reason") if isinstance(acc, dict) else getattr(acc, "reason", None)) if acc else None
        out[(c["scenario_id"], c.get("section_excel") or c.get("section_mes"))] = (c["status"], (reason or "")[:70])
    return out


def main(before: str, after: str, *reports: str) -> int:
    total = Counter()
    changed_all = []
    for rp in reports:
        doc = json.loads(Path(rp).read_text(encoding="utf-8"))
        a, b = statuses(doc, Path(before)), statuses(doc, Path(after))
        changed = [(k, a[k], b[k]) for k in sorted(a) if a[k] != b[k]]
        total.update(f"{x[0]} -> {y[0]}" for _k, x, y in changed)
        changed_all += [(Path(rp).name, *x) for x in changed]
        print(f"   {Path(rp).name:<28} cells {len(a):>5}  changed {len(changed)}")
    for name, k, x, y in changed_all:
        print(f"      {name}: {k[0]} | {k[1]}: {x[0]} -> {y[0]}  ({y[1] or x[1]})")
    print(f"== {sum(total.values())} cell(s) changed: {dict(total) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
