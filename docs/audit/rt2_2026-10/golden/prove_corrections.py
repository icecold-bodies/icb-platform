"""RT2 Part 2 (RT2_RULING_1 R1) — the two-step proof of the corrected workbook set.

    (PYTHONPATH = backend/)  python prove_corrections.py <dir written by build_corrected_set.py>

  1. PROVE-THEN-TRUST on Burt's ORIGINAL set: every pack sheet's null scenario (his saved inputs)
     recalculated by LibreOffice reproduces his own Excel's cached section totals.
  2. MOVE-ONLY, per correction, on the same null scenarios:
       c1 (PRICE PU!C17 4095 -> 4100) against the original: every PU line priced off [1]PU!$C$17
       moves by exactly x4100/4095; every other line, and every section without such a line, by 0.
       corrected (c1 + the SUB FRAME galv repoint) against c1: every repointed GALV PLATE line moves
       by exactly x D27/D28 (= (D27 - D28)/2.98 x its quantity x its gates); everything else by 0.
  A failure is a non-zero exit. The prove step is NOT run on the corrected set: Burt's cached
  results were computed at 4095 and on $D$28, so it cannot pass there by design — this file is
  what replaces it.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

from tools.costing_audit.excel_oracle import ExcelOracle, PRICE_FILE, GRP_FILE
from tools.costing_audit.mapping import norm_name

PACK_SHEETS = ["UP TO 2.3 CHILLER BODY", "UP TO 5.5 CHILLER AND 2.3 WIDE", " 4.9 & UP CHILLER AND 2.5 WIDE ",
               " UP TO 2,3 MTR FREEZER ", " UP TO 4.8 MT FREEZER  (2", " 4.9 & UP FREEZER BODY (2",
               "icecream up to 3,2", "icecream up to 4.8", " icecream 4.9 up",
               "EXPLOSIVE UP TO 2.7", "EXPLOSIVE 2.7 TO 4.8", "EXPLOSIVE 4.9 AND UP"]
TOL = 1e-9
COUNTS: dict[str, dict] = {}


def null_results(d: Path, label: str) -> tuple[ExcelOracle, dict]:
    work = Path(tempfile.mkdtemp(prefix=f"rt2_prove_{label}_"))
    o = ExcelOracle(d, work_dir=work, log=lambda m: print(f"   [{label}] {m}", flush=True))
    scs = [o.null_scenario(s) for s in PACK_SHEETS]
    res = o.run(scs)
    return o, {sc.sheet: res[sc.id] for sc in scs}


def price_refs(o: ExcelOracle) -> dict[tuple[str, str, int], str]:
    """(sheet, section, line row) -> the price cell's formula text, from the formulas view."""
    out = {}
    for s in PACK_SHEETS:
        sm = o.maps[s]
        ws = o.wb[s]
        for sec in sm.sections:
            for ln in sec.lines:
                out[(s, sec.name, ln.row)] = str(ws[ln.price_cell].value or "") if ln.price_cell else ""
    return out


def compare(o_before, before: dict, after: dict, expect, label: str) -> list[str]:
    """`expect(sheet, section, line_before, line_after, price_formula)` -> (expected total after, note)
    for a line that MUST move, or None for a line that must not move at all."""
    refs = price_refs(o_before)
    problems, moved, lines_moved = [], [], []
    for s in PACK_SHEETS:
        sm = o_before.maps[s]
        for sec in sm.sections:
            a, b = before[s].sections[sec.name], after[s].sections[sec.name]
            want_delta = 0.0
            for la, lb, ln in zip(a.lines, b.lines, sec.lines):
                ta, tb = la.total or 0.0, lb.total or 0.0
                e = expect(s, sec.name, la, lb, refs[(s, sec.name, ln.row)])
                want = ta if e is None else e[0]
                if abs(tb - want) > max(abs(want), 1.0) * TOL:
                    problems.append(f"{label} {s.strip()!r} {sec.name} row {ln.row} {la.desc!r}: {ta:.6f} -> {tb:.6f}, "
                                    f"expected {want:.6f}")
                if e is not None and abs(tb - ta) > 1e-12:
                    lines_moved.append(f"   row {ln.row:>3} {s.strip():<32} {sec.name:<26} {la.desc!r}: {ta:.4f} -> {tb:.4f}  {e[1]}")
                want_delta += (want - ta) * (a.multiplier or 1.0)
            da = (b.total or 0.0) - (a.total or 0.0)
            if abs(da - want_delta) > max(abs(a.total or 0.0), 1.0) * 1e-7:
                problems.append(f"{label} {s.strip()!r} {sec.name}: section moved {da:+.6f}, the moving lines account for {want_delta:+.6f}")
            if abs(da) > 1e-9:
                moved.append((s.strip(), sec.name, a.total, b.total, da))
    print(f"\n== {label}: {len(lines_moved)} line(s) moved, {len(moved)} section(s) moved; every other line and "
          f"section of the 12 pack sheets moved 0")
    print("\n".join(lines_moved))
    for s, n, ta, tb, da in moved:
        print(f"   section {s:<32} {n:<26} {ta:>12.4f} -> {tb:>12.4f}  ({da:+.4f})")
    COUNTS[label] = {"lines_moved": len(lines_moved), "sections_moved": len(moved)}
    return problems


def main(root: str) -> int:
    root = Path(root)
    prov = json.loads((root / "corrections.json").read_text(encoding="utf-8"))
    problems: list[str] = []

    print("== 1. prove-then-trust on Burt's ORIGINAL set (null scenario = his saved inputs)")
    o_orig = ExcelOracle(root / "original", work_dir=Path(tempfile.mkdtemp(prefix="rt2_prove_orig_")),
                         log=lambda m: print(f"   [prove] {m}", flush=True))
    p = o_orig.prove(PACK_SHEETS)
    print(f"   prove-then-trust: {'OK on all 12 pack sheets' if not p else 'FAILED'}")
    problems += [f"prove: {x}" for x in p]

    o0, r0 = null_results(root / "original", "original")
    o1, r1 = null_results(root / "c1", "c1")
    _, r2 = null_results(root / "corrected", "corrected")

    ratio1 = 4100.0 / 4095.0

    def expect1(s, sec, la, lb, f):
        # the null scenario normalises every PU line to the 32D reference (C17), so every PU line that
        # references the price list moves by exactly 4100/4095; a hard-coded rate (the chillers' 3090) cannot
        if norm_name(la.desc) in ("PU", "PU FOAM") and ("PU!$C$17" in f or "PU!$C$19" in f):
            return (la.total or 0.0) * ratio1, "x 4100/4095"
        return None
    problems += compare(o0, r0, r1, expect1, "correction 1 (PU!C17 4095 -> 4100)")

    ms = load_workbook(io.BytesIO((root / "c1" / PRICE_FILE).read_bytes()), data_only=True, read_only=True)["MILD STEEL"]
    d27, d28 = float(ms["D27"].value or 0), float(ms["D28"].value or 0)
    print(f"\n   MILD STEEL D27 (1.0 MM PLATE) = {d27} · D28 (1.2 MM PLATE) = {ms['D28'].value!r} (empty reads 0) "
          f"· the line price moves (D27 - D28)/2.98 = {(d27 - d28) / 2.98:.6f} per unit")
    sheets2 = {c.split("!")[0] for c in prov["corrections"][1]["cells"]}

    def expect2(s, sec, la, lb, f):
        if not (norm_name(sec) == norm_name("SUB FRAME + LIGHT BOX ASSY") and "$D$28" in f
                and "GALV PLATE" in (la.desc or "").upper() and s.strip() in sheets2):
            return None
        pa, pb, q = la.price or 0.0, lb.price or 0.0, lb.qty or 0.0
        if abs(pa - d28 / 2.98) > 1e-9 or abs(pb - d27 / 2.98) > 1e-9:
            return float("nan"), f"price {pa} -> {pb}, expected {d28 / 2.98} -> {d27 / 2.98}"
        g = round((lb.total or 0.0) / (pb * q)) if pb * q else 0       # the line's own gate/multiplier (0, 1, 2 …)
        return (la.total or 0.0) + (d27 - d28) / 2.98 * q * g, \
            f"(D27 - D28)/2.98 x qty {q:g} x gate {g} = {(d27 - d28) / 2.98 * q * g:+.4f}"
    problems += compare(o1, r1, r2, expect2, "correction 2 (SUB FRAME galv $D$28 -> $D$27)")

    print()
    if problems:
        print(f"######## PROOF FAILED — {len(problems)} problem(s):")
        print("\n".join(f"   {x}" for x in problems))
        return 1
    print("######## PROOF OK — the original set reproduces Burt's cached totals, and each correction "
          "moves exactly its own lines by exactly its own factor (0 other lines, 0 other sections)")
    from datetime import datetime, timezone
    prov["proof"] = {"script": "docs/audit/rt2_2026-10/golden/prove_corrections.py",
                     "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "prove_then_trust_on_original": f"OK on all {len(PACK_SHEETS)} pack sheets",
                     "move_only": COUNTS, "result": "OK — 0 other lines, 0 other sections moved"}
    (root / "corrections.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print(f"   recorded the proof in {root / 'corrections.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
