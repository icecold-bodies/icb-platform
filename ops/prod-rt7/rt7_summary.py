"""RT7 §3.0 — every unaccepted and accepted cell of a set of audit reports, grouped: body, section, likely cause,
cell count, the cells' difference range (MES - Excel) and the variants. Cells only — the reports carry no customer.

    python rt7_summary.py <reports-dir>          (reads prod_<pack>.json)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

d = Path(sys.argv[1])
ALL = ("chillers", "freezers", "icecream", "explosive")
tot: dict[str, int] = defaultdict(int)
for p in ("chillers", "freezers", "icecream", "explosive", "smoke"):
    f = d / f"prod_{p}.json"
    if not f.is_file():
        print(f"{p}: no report")
        continue
    r = json.loads(f.read_text(encoding="utf-8"))
    counts: dict[str, int] = defaultdict(int)
    for c in r["cells"]:
        counts[c["status"]] += 1
        if p in ALL:
            tot[c["status"]] += 1
    print(f"\n{p}: {len(r['cells'])} cells  {dict(sorted(counts.items()))}")
    groups = defaultdict(list)
    for c in r["cells"]:
        if c["status"] in ("FLAG", "PRESENCE", "UNMAPPED", "EXPIRED", "NO_GOLDEN", "ACCEPTED"):
            lc = c.get("likely_cause") or c.get("reason") or "?"
            cause = " ".join(lc.split(" (")[0].split())
            groups[(c["status"], c["trailer_name"], c["section_mes"] or c["section_excel"] or "?", cause)].append(c)
    for (st, body, sec, cause), cells in sorted(groups.items()):
        nets = [round((c["mes_total"] or 0) - (c["excel_total"] or 0), 2) for c in cells]
        print(f"  {st:<9}{len(cells):>4}  {body:<24} {sec:<26} {cause:<46} {min(nets):+10.2f} .. {max(nets):+10.2f}"
              f"  {','.join(sorted({c['variant'] for c in cells}))}")
print(f"\nAll (chillers + freezers + icecream + explosive): {sum(tot.values())} cells  {dict(sorted(tot.items()))}")
