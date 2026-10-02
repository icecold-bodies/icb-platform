"""RT3 — the body-family swatches: the PR's Click-to-verify reference (RT3_RULING_1 addition 3, 1a item 6).

    python backend/tools/rt3_swatches.py            writes docs/rt3/body_family_swatches.html
    python backend/tools/rt3_swatches.py --check    exits 1 if the committed file is not what this writes

STATIC HTML on the light MES skin only (theme-mes.css: #FFFFFF inputs on a #F5F7FB page) — no script, so it
renders anywhere, including viewers that block JavaScript. Every number and every ink comes from
app/services/body_family.py (loaded by path: no database, no settings), so the reference cannot drift from what
the app draws; tests/test_rt3_body_families.py pins the committed file to this generator. The selects are real
native <select>s: the closed box with its family bar, and the open list as a listbox (optgroups + coloured options).
"""
from __future__ import annotations

import html
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "rt3" / "body_family_swatches.html"

# Michael's six families, as approved (RT3_RETURN_1 §5), with prod's ACTIVE bodies (the 2 Oct discovery)
FAMILIES = [
    ("EXPLOSIVE", "red", "#E03131", ["EXPLOSIVE 2.7 TO 4.8", "EXPLOSIVE 4.9 AND UP", "EXPLOSIVE UP TO 2.7"]),
    ("CHILLER", "light blue", "#168ED9", ["CHILLER 2.3 METER", "CHILLER LARGE", "CHILLER MEDIUM"]),
    ("FREEZER", "dark blue", "#4263EB", ["FREEZER 2.3 METER", "FREEZER LARGE", "FREEZER MEDIUM"]),
    ("MEAT", "orange", "#D66A0B", ["MEAT HANGER LARGE", "MEAT HANGER SMALL-MEDIUM"]),
    ("ICE CREAM", "dark pink", "#D63384", ["ICECREAM BODY LARGE", "ICECREAM BODY MEDIUM", "ICECREAM BODY SMALL"]),
    ("OTHER", "grey", "#7D858C", ["Manni RIGIDS CB", "RHINORANGE TRAILER"]),
]


def _bf():
    spec = importlib.util.spec_from_file_location("rt3_body_family", ROOT / "backend" / "app" / "services" / "body_family.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render() -> str:
    bf = _bf()
    e = html.escape
    rows = []
    for name, word, colour, bodies in FAMILIES:
        k = bf.colour_check(colour)
        rows.append((name, word, colour, bodies, k))

    def chip(name, colour, ink):
        return (f'<span class="chip" style="color:{ink}"><i style="background:{colour}"></i>{e(name)}</span>')

    closed = "".join(
        f'<div class="field"><span class="wrap" style="--fam:{c}"><select title="Family: {e(n)}">'
        f'<option>{e(b[0])}</option></select></span>{chip(n, c, k["ink"])}</div>'
        for n, w, c, b, k in rows)
    listbox = "".join(
        f'<optgroup label="{e(n)}">' + "".join(f'<option style="color:{k["ink"]}">{e(x)}</option>' for x in b) + "</optgroup>"
        for n, w, c, b, k in rows)
    chips = "".join(chip(n, c, k["ink"]) for n, w, c, b, k in rows)
    table = "".join(
        f'<tr><td>{e(n)} <span class="dim">({e(w)})</span></td>'
        f'<td><span class="sw" style="background:{c}"></span>{c}</td>'
        f'<td>{bf.contrast(c, "#ffffff"):.2f}</td><td>{bf.contrast(c, "#f5f7fb"):.2f}</td>'
        f'<td style="color:{k["ink"]};font-weight:700">{k["ink"]}</td>'
        f'<td>{bf.contrast(k["ink"], "#ffffff"):.2f}</td><td>{bf.contrast(k["ink"], "#f5f7fb"):.2f}</td>'
        f'<td>{"pass" if k["ok"] else "WARN"}</td></tr>'
        for n, w, c, b, k in rows)
    n_opts = sum(len(b) for *_, b, _k in rows) + len(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Body Family Swatches</title>
<style>
  body {{ margin: 0; background: #F5F7FB; color: #23303A; font: 13px/1.45 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 18px 16px 28px; }}
  h1 {{ font-size: 17px; color: #0F172A; margin: 0 0 4px; }}
  .sub {{ color: #6B7280; margin: 0 0 16px; max-width: 760px; }}
  .lbl {{ color: #6B7280; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; margin: 16px 0 6px; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 28px; align-items: flex-start; }}
  .card {{ background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px 14px; }}
  select {{ font: inherit; color: #23303A; background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 8px; }}
  .field {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .wrap {{ position: relative; display: inline-block; }}
  .wrap::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; border-radius: 6px 0 0 6px; background: var(--fam); }}
  .wrap select {{ width: 220px; padding-left: 13px; }}
  .list select {{ width: 250px; }}
  optgroup {{ font-style: normal; font-weight: 700; color: #23303A; }}
  .chip {{ display: inline-flex; align-items: center; gap: 5px; margin: 0 8px 6px 0; padding: 1px 7px 1px 6px; border-radius: 999px;
          background: #FFFFFF; border: 1px solid #E5E7EB; font-size: 10.5px; font-weight: 700; letter-spacing: .02em; white-space: nowrap; }}
  .chip i {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .tbl {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; background: #FFFFFF; }}
  th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid #E5E7EB; white-space: nowrap; }}
  th {{ color: #6B7280; font-weight: 600; font-size: 12px; }}
  .sw {{ display: inline-block; width: 26px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 6px; }}
  .dim {{ color: #6B7280; font-size: 11px; }}
  .note {{ color: #6B7280; font-size: 12px; margin-top: 12px; max-width: 760px; }}
</style>
</head>
<body>
<main>
<h1>Body families: the six approved colours on the MES screens</h1>
<p class="sub">One stored colour per family colours the bars, dots and borders. The family-name text uses one ink
derived from it, at least 4.6:1 on both MES backgrounds. Built for the light MES skin only (RT3_RULING_1a). The
selects below are real native &lt;select&gt;s drawn by this browser.</p>
<div class="row">
  <div class="card"><div class="lbl">The closed BODY TYPE box (one per family)</div>{closed}</div>
  <div class="card list"><div class="lbl">The open list (optgroups + coloured options)</div>
    <select size="{n_opts}" aria-label="Body type, open">{listbox}</select></div>
</div>
<div class="lbl">Chips (lists and headers): colour dot + family name</div>
<div class="card">{chips}</div>
<div class="lbl">Contrast (WCAG): bar at least 3:1, text ink at least 4.6:1</div>
<div class="tbl"><table>
<tr><th>family</th><th>stored colour</th><th>bar on #FFFFFF</th><th>bar on #F5F7FB</th><th>text ink</th>
<th>ink on #FFFFFF</th><th>ink on #F5F7FB</th><th>check</th></tr>
{table}
</table></div>
<p class="note">Coloured options in the open list render in Chrome, Edge and Firefox on Windows. On a Mac and on phones the
system list ignores option colours; the family headings still group the list. The closed box's bar and the chips render in
every browser.</p>
</main>
</body>
</html>
"""


def main(argv) -> int:
    doc = render()
    if "--check" in argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == doc
        print("swatches up to date" if ok else f"STALE: re-run python backend/tools/rt3_swatches.py ({OUT})")
        return 0 if ok else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
