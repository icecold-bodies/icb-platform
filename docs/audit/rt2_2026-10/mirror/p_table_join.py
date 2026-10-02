"""RT2 Manifest P — join the table: old -> new -> Burt, per line, at each body's default size and default foam.

    python p_table_join.py <p_old.json> <p_new.json> <burt golden dir> <out.md>

old / new: p_table.py on the mirror before P, and after P + D. Burt: his corrected 21 Sep sheet (the golden's
oracle, LibreOffice) at the same size: the `all_pu` scenario (every panel PU at his saved PU thickness), or `srd`
for a single-rear-door line; his foam is the body's R6 default (foam_default 4G on the four 4G bodies). Burt's
value is the sheet's PU row in that section; his thickness is the scenario's panel thickness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "manifest_p" / "manifest_p.yaml"
SHEET = {34: "explosive_up_to_2_7", 37: "explosive_2_7_to_4_8", 24: "explosive_4_9_and_up", 19: "up_to_2_3_mtr_freezer",
         21: "4_9_up_freezer_body_2", 16: "icecream_up_to_3_2", 17: "icecream_up_to_4_8", 18: "icecream_4_9_up",
         36: "small_meat_body_up_to_5_2", 15: "rhinorange_trailer"}


def burt_line(gdir: Path, tid: int, sec: str) -> tuple[float | None, float | None, str]:
    d = json.loads((gdir / f"{SHEET[tid]}.json").read_text(encoding="utf-8"))
    want = "srd" if sec == "SRD" else "all_pu"
    sc = next(s for s in d["scenarios"] if s["scenario"]["variant"] == want)
    section = sc["sections"].get(sec)
    if section is None:
        return None, None, f"no {sec} section on the sheet"
    pu = [ln for ln in section["lines"] if (ln["desc"] or "").strip().upper() in ("PU", "PU FOAM")]
    t = (sc["scenario"]["panels"].get(sec) or {}).get("thickness")
    if not pu:
        return None, t, "no PU row"
    note = "" if section.get("status") == "OK" else f"section {section.get('status')}"
    return round(sum(ln["total"] for ln in pu) * (section.get("multiplier") or 1.0), 2), t, note


def main(old: str, new: str, gdir: str, out: str) -> int:
    O = {r["bom_id"]: r for r in json.loads(Path(old).read_text(encoding="utf-8"))["lines"]}
    N = {r["bom_id"]: r for r in json.loads(Path(new).read_text(encoding="utf-8"))["lines"]}
    kind = {}
    for e in yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["changes"]:
        kind[int(e["bom_id"])] = e["finding"]
    rows, gaps = [], []
    for bid, n in N.items():
        o = O[bid]
        b, tb, note = burt_line(Path(gdir), n["body_id"], n["section"])
        d = None if (b is None or n["total"] is None) else round(n["total"] - b, 2)
        ok = d is not None and abs(d) <= max(1.0, 0.0005 * abs(b))        # to the rand (Burt rounds his panel areas)
        if not ok:
            gaps.append((n, b, d, tb))
        rows.append(f"| {n['body']} | {n['section']} | {bid} | {kind[bid]} | {'×'.join(str(x) for x in n['size'])} | {n['foam']} "
                    f"| {n['thickness']}{' ↩ ' + n['carried'] if n.get('carried') else ''} | {tb} "
                    f"| {o['total']:,.2f} | {n['total']:,.2f} | {'' if b is None else f'{b:,.2f}'} "
                    f"| {'' if d is None else f'{d:+,.2f}'} | {'= Burt' if ok else '**gap**'}{' · ' + note if note else ''} |")
    head = ("| body | section | bom | P | size (L×W×H) | foam | MES t | Burt t | old | new | Burt | new − Burt | |\n"
            "|---|---|---:|---|---|---|---|---|---:|---:|---:|---:|---|")
    total_old = sum(O[b]["total"] or 0 for b in N); total_new = sum(N[b]["total"] or 0 for b in N)
    text = (f"{head}\n" + "\n".join(rows) +
            f"\n\n**{len(rows)} lines; {len(rows) - len(gaps)} equal Burt to the rand; {len(gaps)} gap(s).** "
            f"Sum of the 39 lines at these sizes: old R{total_old:,.2f} → new R{total_new:,.2f}.\n")
    Path(out).write_text(text, encoding="utf-8")
    print(text)
    for n, b, d, tb in gaps:
        print(f"GAP {n['body']} {n['section']} bom {n['bom_id']}: new {n['total']} vs Burt {b} ({d}); MES t {n['thickness']} vs Burt t {tb}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
