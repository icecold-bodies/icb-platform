"""RT7 (RT7_RULING_1A) — diff two golden trees cell for cell, and trace every change to PU!C19.

    python diff_golden.py <old golden dir> <new golden dir> [--expect-none | --expect-4g]

Compares every pack's every sheet's every scenario: grand total, each section's total/status, and each line's
qty / price / total (same order; a line added or removed is a change). Prints every change.

  --expect-none   the two trees must agree exactly (the reproduction check: RT2's corrected set, regenerated
                  today, against the committed golden — it proves the toolchain before anything moves)
  --expect-4g     every change must trace to PU!C19 (4G FOAM R5 581 -> R5 400): only lines whose PRICE moved by
                  exactly 5400/5581 with the quantity unchanged, and each section's total moved by exactly the sum
                  of its moved lines (scenario grand totals likewise). Anything else is listed as a STOP.
"""
import json
import sys
from pathlib import Path

RATIO = 5400 / 5581
EPS = 1e-6


def load(d: Path) -> dict:
    out = {}
    for pack in sorted(p for p in d.iterdir() if p.is_dir()):
        for f in sorted(pack.glob("*.json")):
            if f.name == "_manifest.json":
                continue
            for s in json.loads(f.read_text(encoding="utf-8"))["scenarios"]:
                out[(pack.name, f.stem, s["scenario"]["id"])] = s
    return out


def close(a, b, rel=EPS) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= max(abs(a), abs(b), 1.0) * rel


def main(old_dir: str, new_dir: str, mode: str = "--expect-4g") -> int:
    old, new = load(Path(old_dir)), load(Path(new_dir))
    stops, traced, n_sec = [], [], 0
    for k in sorted(set(old) | set(new)):
        if k not in old or k not in new:
            stops.append(f"{k}: scenario only in {'old' if k in old else 'new'}")
            continue
        so, sn = old[k], new[k]
        moved_grand = 0.0
        for sec in sorted(set(so["sections"]) | set(sn["sections"])):
            a, b = so["sections"].get(sec), sn["sections"].get(sec)
            if a is None or b is None:
                stops.append(f"{k} {sec}: section only in {'old' if a else 'new'}")
                continue
            if a.get("status") != b.get("status"):
                stops.append(f"{k} {sec}: status {a.get('status')} -> {b.get('status')}")
            la, lb = a.get("lines") or [], b.get("lines") or []
            if [x["desc"] for x in la] != [x["desc"] for x in lb]:
                stops.append(f"{k} {sec}: the lines differ in name or order")
                continue
            moved = 0.0
            for x, y in zip(la, lb):
                if close(x.get("qty"), y.get("qty")) and close(x.get("price"), y.get("price")) \
                        and close(x.get("total"), y.get("total")):
                    continue
                dt = (y.get("total") or 0.0) - (x.get("total") or 0.0)
                is_4g = (close(x.get("qty"), y.get("qty")) and x.get("price") and
                         close(y["price"] / x["price"], RATIO, 1e-9) and close(y.get("total") or 0.0,
                                                                              (x.get("total") or 0.0) * RATIO, 1e-9))
                line = (f"{k[0]}/{k[2]} {sec} {x['desc']}: qty {x.get('qty')} price {x.get('price')} -> "
                        f"{y.get('price')} total {x.get('total')} -> {y.get('total')} ({dt:+.4f})")
                (traced if is_4g else stops).append(line)
                moved += dt
            if not close(a.get("total") or 0.0, b.get("total") or 0.0):
                n_sec += 1
                mult = b.get("multiplier") or 1.0
                if not close((b.get("total") or 0.0) - (a.get("total") or 0.0), moved * mult, 1e-7):
                    stops.append(f"{k} {sec}: total {a.get('total')} -> {b.get('total')} is not the moved lines "
                                 f"({moved:+.4f} x {mult})")
            moved_grand += (b.get("total") or 0.0) - (a.get("total") or 0.0)
        if not close((sn.get("grand_total") or 0.0) - (so.get("grand_total") or 0.0), moved_grand, 1e-7):
            stops.append(f"{k}: grand total {so.get('grand_total')} -> {sn.get('grand_total')} is not its sections")
    print(f"scenarios {len(set(old) | set(new))}  sections moved {n_sec}  lines traced to PU!C19 {len(traced)}  "
          f"STOP {len(stops)}")
    by_pack: dict[str, int] = {}
    for t in traced:
        by_pack[t.split("/", 1)[0]] = by_pack.get(t.split("/", 1)[0], 0) + 1
    print("   traced lines per pack:", by_pack)
    for t in traced[:12]:
        print("   4G  ", t)
    for s in stops[:60]:
        print("   STOP", s)
    if mode == "--expect-none":
        return 0 if not traced and not stops else 1
    return 0 if not stops else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
