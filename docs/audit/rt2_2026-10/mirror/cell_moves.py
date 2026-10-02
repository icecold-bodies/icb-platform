"""RT2 window rehearsal — which audit cells move between two "All" steps (the runbook's "only P's / D's cells move").

    python cell_moves.py <reports-before-dir> <reports-after-dir>      (prod_<pack>.json from the CLI)

Compares every cell by (pack, scenario, section) on status and both totals (to the cent), and prints the moved cells
grouped by pack / body / section / variant, with the status change and the MES total before -> after.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PACKS = ("smoke", "chillers", "freezers", "icecream", "explosive")


def cells(d: Path) -> dict:
    out = {}
    for p in PACKS:
        for c in json.loads((d / f"prod_{p}.json").read_text(encoding="utf-8"))["cells"]:
            out[(p, c["scenario_id"], c.get("section_excel") or c.get("section_mes") or "")] = c


    return out


def r2(v):
    return None if v is None else round(float(v), 2)


def main(a: str, b: str) -> int:
    A, B = cells(Path(a)), cells(Path(b))
    assert set(A) == set(B), f"cell sets differ: {len(set(A) ^ set(B))}"
    moved = [k for k in sorted(A) if (A[k]["status"], r2(A[k]["excel_total"]), r2(A[k]["mes_total"]))
             != (B[k]["status"], r2(B[k]["excel_total"]), r2(B[k]["mes_total"]))]
    groups = defaultdict(list)
    for k in moved:
        x, y = A[k], B[k]
        groups[(k[0], x["trailer_name"], k[2], x["variant"], x["status"], y["status"])].append((x, y))
    print(f"cells {len(A)}; moved {len(moved)}; unchanged {len(A) - len(moved)}")
    for (pack, body, sec, var, s0, s1), xs in sorted(groups.items()):
        m0 = sorted({r2(x["mes_total"]) for x, _ in xs}); m1 = sorted({r2(y["mes_total"]) for _, y in xs})
        ex = sorted({r2(x["excel_total"]) for x, _ in xs})
        print(f"   {pack:<9} {body:<24} {sec:<26} {var:<9} {s0:>10} -> {s1:<10} x{len(xs):<2} "
              f"MES {m0[0] if len(m0) == 1 else m0} -> {m1[0] if len(m1) == 1 else m1}   Excel {ex[0] if len(ex) == 1 else ex}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
