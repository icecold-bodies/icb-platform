"""Prod's window reports (after) against the mirror's final run (19 Oct, same golden + list) — and the window's
'before' against the build paste's reports — cell by cell: status, MES and Excel totals to the cent. Read-only."""
import json
import sys
from pathlib import Path


def cells(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(c["scenario_id"], c["section_mes"] or c["section_excel"]): c for c in d["cells"]}


def cmp(label, a_dir, a_stem, b_dir, b_stem):
    tot = same = 0
    diffs = []
    for p in ("smoke", "chillers", "freezers", "icecream", "explosive"):
        a = cells(Path(a_dir) / f"{a_stem}_{p}.json")
        b = cells(Path(b_dir) / f"{b_stem}_{p}.json")
        for k in sorted(set(a) | set(b)):
            tot += 1
            x, y = a.get(k), b.get(k)
            if x is None or y is None:
                diffs.append((p, k, "only one side"))
                continue
            if (x["status"], round(x["mes_total"] or 0, 2), round(x["excel_total"] or 0, 2)) == \
               (y["status"], round(y["mes_total"] or 0, 2), round(y["excel_total"] or 0, 2)):
                same += 1
            else:
                diffs.append((p, k, (x["status"], x["mes_total"], x["excel_total"]), (y["status"], y["mes_total"], y["excel_total"])))
    print(f"{label}: {same} of {tot} cells identical; {len(diffs)} differ")
    for d in diffs[:10]:
        print("   ", d)


sp = Path(sys.argv[1])
wb = sp / "windowback/icb-rt2-all"
post = next(wb.glob("out-post-*/reports"))
pre = next(wb.glob("out-pre-*/reports"))
cmp("prod AFTER vs mirror final (19 Oct)", post, "prod", sp / "mirror_final", "prod")
exp = sp / "exportback"
bp = next(exp.glob("**/out-20261019-151523/reports"), None)
if bp:
    cmp("prod BEFORE vs the 19 Oct build paste", pre, "prod", bp, "prod")
else:
    print("build-paste reports not found under exportback/")
