"""RT4 B.6 — render the gap table (MANNI_GAP_TABLE.md) from manni_gap.py's two reports. Report only.

    python gap_table.py <pu_formulas.json>      (the PU / galv-plate cells read from Burt's workbook, see the doc)
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REP = json.loads((HERE / "report" / "manni_gap.json").read_text(encoding="utf-8"))
DF = json.loads((HERE / "report" / "manni_df.json").read_text(encoding="utf-8"))
SNAP = json.loads((HERE.parent / "prod" / "discovery_20261004-080150" / "manni_snapshot.json").read_text(encoding="utf-8"))
ORDER = ["Manni RIGIDS CB", "Manni Bakkie Rigids", "Manni RIGIDS FB", "Manni TRAILERS"]
BODY = {"Manni RIGIDS CB": "3 MANNI RIGIDS CB", "Manni Bakkie Rigids": "4 MANNI BAKKI RIGIDS",
        "Manni RIGIDS FB": "5 MANNI RIGIDS FB", "Manni TRAILERS": "6 MANNI TRAILERS", "Manni DF": "7 MANNI DF"}
VARIANTS = ["as_sheet", "drd", "srd", "all_pu", "all_eps", "foam_4g"]
DOOR_SECTIONS = ("SRD", "SRD DOOR FITTINGS")


def R(v, d=2):
    return "—" if v is None else f"{v:,.{d}f}".replace(",", " ")


def pct(m, e):
    return "—" if not e else f"{(m - e) / e * 100:+.1f} %"


def norm(s):
    s = (s or "").upper().replace("+", "&").replace(" AND ", " & ")
    return " ".join(s.split())


def main(pu_path: str) -> int:
    pu = json.loads(Path(pu_path).read_text(encoding="utf-8"))
    out: list[str] = []
    say = out.append
    scen = {s["scenario"]["id"]: s for s in REP["scenarios"]}
    by_sheet = defaultdict(dict)
    for sid, s in scen.items():
        by_sheet[s["scenario"]["sheet"]][s["scenario"]["variant"]] = s
    cells = defaultdict(list)
    for c in REP["cells"]:
        cells[(c["sheet"], c["variant"])].append(c)
    mats = {m["id"]: m for m in SNAP["tables"]["materials"]}
    bom = SNAP["tables"]["bill_of_materials"]

    say("# RT4 B.6 — the five Mannis against Burt's Manni sheets (report only)")
    say("")
    say("**Fix nothing from this.** It is the input for the next job (RT4 dispatch B.6).")
    say("")
    say("## Basis")
    say("")
    say("- **Excel:** Burt's 21 Sep zip (`nuwepryslyste.zip`, sha256 `ee8e2159…`), with Burt's two written corrections "
        "applied on a copy, exactly as the costing audit's golden is (GRP `04c774e2…`). Neither correction touches a "
        "Manni sheet's own cells: the PU price they change is not referenced by any Manni sheet, and the 1.0 MM galv plate "
        "correction was made on seven other sheets only.")
    say("  - Four sheets (`Manni RIGIDS CB`, `Manni Bakkie Rigids`, `Manni RIGIDS FB`, `Manni TRAILERS`) through the "
        "audit's own oracle (LibreOffice recalculation of a copy). **Prove-then-trust passed on all four**: a recalculated "
        "copy at the saved inputs reproduces Burt's cached totals.")
    say("  - `Manni DF` is Burt's dry-freight template (inputs B3:B5, Y/N options, no insulation block). The audit cannot "
        "read it, so `manni_gap.py df` reads it directly. At its saved size the gated section totals add up to the sheet's "
        f"GRAND TOTAL exactly ({R(DF['excel']['saved']['sum_gated'])} = {R(DF['excel']['saved']['grand'])}).")
    say("- **MES:** prod's rows for the five Mannis, as exported read-only on 4 Oct (RT4 discovery). They were loaded into "
        "the prod mirror inside one transaction that was rolled back, and priced on the calculator path by the audit's "
        "own probe. Manifest S (5 Oct) only re-pointed section ids, and the mirror proof shows it priced identically to "
        "the cent. Material 182 is at prod's 4 Oct price.")
    say("- **Size:** each body at **prod's default size**. For the four standard sheets that equals Burt's saved size. "
        "MANNI DF's default (12.2 × 2.6 × 3.0) differs from its sheet's (7.2 × 2.6 × 2.7).")
    say("- **Variants:** as the audit's packs:")
    say("  - `as_sheet` is Burt's saved flags (DRD, PU);")
    say("  - `srd` swaps the door;")
    say("  - `all_eps` / `all_pu` set every panel;")
    say("  - `foam_4g` sets the PU grade.")
    say("  No accepted list: every difference shows. The audit report itself (HTML with the line drill-down) is "
        "`report/manni_gap.html`.")
    say("")

    # ---- the summary -------------------------------------------------------------------------------------------
    say("## Summary at the default size")
    say("")
    say("| body | size | Burt (as sheet, DRD) | MES (DRD) | Δ | Burt SRD | MES SRD | sections FLAG / PRESENCE |")
    say("|---|---|---:|---:|---:|---:|---:|---|")
    for sh in ORDER:
        a, s = by_sheet[sh]["as_sheet"], by_sheet[sh]["srd"]
        sc = a["scenario"]
        cs = cells[(sh, "as_sheet")]
        nflag = sum(1 for c in cs if c["status"] == "FLAG")
        npres = sum(1 for c in cs if c["status"] == "PRESENCE")
        say(f"| {BODY[sh]} | {sc['length']} × {sc['width']} × {sc['height']} | {R(a['excel_grand'])} | {R(a['mes_grand'])} | "
            f"{R(a['mes_grand'] - a['excel_grand'])} ({pct(a['mes_grand'], a['excel_grand'])}) | {R(s['excel_grand'])} | "
            f"{R(s['mes_grand'])} | {nflag} / {npres} |")
    dx, dm = DF["excel"]["default"], DF["mes"]
    sz = DF["default_size"]
    say(f"| {BODY['Manni DF']} | {sz[0]} × {sz[1]} × {sz[2]} | {R(dx['sum_gated'])} | {R(dm['DRD']['grand_total'])} | "
        f"{R(dm['DRD']['grand_total'] - dx['sum_gated'])} ({pct(dm['DRD']['grand_total'], dx['sum_gated'])}) | "
        f"(no SRD on the sheet) | {R(dm['SRD']['grand_total'])} | see its own section |")
    say("")
    say("Grand totals are **material cost as the sheet computes it** (the audit's measure: the gated J / H column, "
        "before margin and ratio).")
    say("")

    # ---- what drives the gaps (read off the tables below; every number is in them) ------------------------------
    say("## What drives the gaps")
    say("")
    say("1. **Prices that are really line TOTALS.**")
    say("   - **MANNI DF:** many unit prices equal **Burt's line total at the sheet's saved size**, so the total is "
        "multiplied by the quantity again. Examples: 34MM LOCKING POLE R252.00 = 6 × R42; 2316 INNER DOOR RUBBER R391.81; "
        "0661-0631 RIVETS R360.50; TAPE R306.00; 4 MM BEND UP SUB FRAME R3 523.50; 80×50×3 CROSSMEMBERS R8 891.12. "
        "This looks like an import that read the dry-freight template's TOTAL column (F) as the price. That template's "
        "price is in E.")
    say("   - **RICE GRAIN FLOOR on BAKKI RIGIDS and TRAILERS:** **R24 356.25** a unit = Burt's R3 163.15 × 7.7, a line "
        "total. Δ +R35 392 and +R328 493.")
    say("2. **MANNI DF sums its five floors.** Burt's sheet costs only the floor whose option is Y (24MM WISA as saved). "
        "MES costs all five. Together with (1), MES is R7.17 M against Burt's R166 k.")
    say("3. **Material choices differ:**")
    say("   - **Renames only:** Burt's `RHINO PANEL` = MES `RHINOTEX SKINS 1375 BIOSHIELD`, at the same price.")
    say("   - **Different materials:** on TRAILERS, Burt has Rhinotex 2100 Bioshield / Crystex V2 / Rhinotex 1150 BW, "
        "where MES has Bioshield 4800 / Rhinopanel V2 / Rhinotex 2400.")
    say("   - **Price-list differences:** WOVEX SKIN R272.27 (Burt) vs R221.40 (MES); 18MM FINN PLY R375.84 vs R468.12; "
        "LVL R148.73 vs R130.54; BIG ALU CORNERS R43.92 vs **R496.05** (MES has the kick-plate price).")
    say("4. **Burt's own R0 prices:**")
    say("   - the 1.2MM GALV PLATE on all four standard sheets (§2 below);")
    say("   - WOVEX SKIN / Rhinotex Bioshield on **RIGIDS FB** (price cell empty).")
    say("   MES prices these where it has the line.")
    say("5. **Lines MES zeroes or never costs:**")
    say("   - every Manni's **SRD PU INJECTION** (`× 0`);")
    say("   - RIGIDS FB's RICE GRAIN FLOOR and ALU KICK PLATES (`× 0`), which Burt costs (flags Y);")
    say("   - lines missing in MES, e.g. FRONT `CHINESE EXTERNAL HIGH GLOSS` on MANNI DF, FLOOR `6MM FINN PLY FLOOR` on "
        "BAKKI.")
    say("6. **PU** is priced by weight on both sides, but with different densities, no 10 % waste in MES, and literal "
        "thicknesses (§1 below).")
    say("7. **Doors:** MES costs REAR FRAME & FLOOR PLATE on an SRD Manni. Burt does not (§3 below).")
    say("")

    # ---- the cross-cutting findings ----------------------------------------------------------------------------
    say("## Across the Mannis")
    say("")
    say("### 1. PU: formula shape, and own price vs the shared PU price")
    say("")
    say("**Both sides price PU by weight, thickness-based** (not the standard bodies' sheet-counting). But they differ "
        "in density, in waste, and in where the thickness comes from:")
    say("")
    say("| sheet | Burt's PU INJECTION quantity (kg) | Burt's price | MES PU lines (formula · price) |")
    say("|---|---|---|---|")
    pu_lines = defaultdict(set)
    for r in bom:
        m = mats.get(r["material_id"]) or {}
        if "PU" in (m.get("name") or "").upper() and "INJECTION" in (m.get("name") or "").upper():
            pu_lines[r["trailer_type_id"]].add((r.get("bom_section"), r.get("formula_expression"),
                                                 r.get("unit_price_override") if r.get("unit_price_override") is not None
                                                 else m.get("price_per_unit"), m.get("name")))
    mes_dens = {}
    for sh, tid in (("Manni RIGIDS CB", 3), ("Manni Bakkie Rigids", 4), ("Manni RIGIDS FB", 5), ("Manni TRAILERS", 6), ("Manni DF", 7)):
        rows = [r for r in pu.get(sh, []) if "INJECTION" in r["label"].upper()]
        qcol, pcol = ("D", "E") if sh == "Manni DF" else ("F", "G")
        q = [(r["cells"].get(qcol) or ["?"])[0] for r in rows]
        p = sorted({(r["cells"].get(pcol) or ["?"])[0] for r in rows if "[1]" in str((r["cells"].get(pcol) or [""])[0])})
        dens = sorted({m for f in q for m in re.findall(r"\*(\d{2})(?=\*|$)", f)}, key=int)
        mes = sorted(pu_lines.get(tid, set()), key=lambda x: str(x[0]))
        mes_dens[sh] = sorted({m for _, f, _, _ in mes if "*0*" not in (f or "")
                               for m in re.findall(r"\*(\d{2})\s*$", f or "")}, key=int)
        mes_txt = "<br>".join(f"{s or '-'}: `{f}` · R{R(pr)}" for s, f, pr, _ in mes[:7]) or "—"
        say(f"| {sh} | `{q[0] if q else '?'}` … (density {', '.join(dens) or '?'} kg/m³) | `{p[0] if p else '?'}` (R56.62/kg) | {mes_txt} |")
    say("")
    say("- **The price source:**")
    say("  - **Burt:** every Manni sheet reads `'[1]RESINS + ADESIVES'!$D$32`: resin `R250820/1A`, **R56.62 / kg**, "
        "its **own price**. It is not the shared PU price (`[1]PU!$C$17`, 32D foam R4 100), so the audit marks every Manni "
        "sheet **NO_4G_REFERENCE**: the 4G grade cannot be expressed.")
    say("  - **MES:** its `PU INJECTION` lines carry the same R56.62 as their own price (MANNI DF: **R60.00**). So "
        "**`foam_4g` = `as_sheet` on both sides**: the 32D / 4G choice does nothing on a Manni.")
    say("- **The shape:** both are thickness-based kilograms (area × thickness × density), not the standard bodies' "
        "sheet-counting. But the details differ:")
    say("  - **Burt:** `width × height × the panel's thickness CELL × density × 1.1`. The density is 65 kg/m³ (RIGIDS CB "
        "50, its SRD 40; floors 75), and the waste is 10 %.")
    say("  - **MES:** `area × a LITERAL thickness × density`, with no × 1.1. MES density by body: "
        + "; ".join(f"{sh.replace('Manni ', '')} {', '.join(v) or '?'}" for sh, v in mes_dens.items()) + ". So:")
    say("    - the thickness never follows the quote's own thickness;")
    say("    - BAKKIE RIGIDS uses `{Waste}` where a thickness belongs (its FLOOR, and the height deductions);")
    say("    - **every Manni's SRD PU line multiplies by `0`** (ZERO_FORMULA): MES never costs PU in an SRD door.")
    say("")
    say("### 2. The 1.2MM GALV PLATE in SUB FRAME + LIGHT BOX ASSY")
    say("")
    gold = {}
    for f in (HERE / "golden" / "manni_gap").glob("manni_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for s in (d["scenarios"].values() if isinstance(d.get("scenarios"), dict) else d.get("scenarios", [])):
            if s.get("scenario", {}).get("variant", "as_sheet") != "as_sheet" and "as_sheet" not in str(s.get("id", "")):
                continue
            for sec in (s["sections"].values() if isinstance(s["sections"], dict) else s["sections"]):
                for l in sec.get("lines", []):
                    if "GALV PLATE" in str(l.get("desc", "")).upper():
                        gold.setdefault(s.get("scenario", {}).get("sheet") or s.get("sheet"), l)
    mes_galv = {r["trailer_type_id"] for r in bom if "GALV PLATE" in ((mats.get(r["material_id"]) or {}).get("name") or "").upper()}
    say("| sheet | Burt's price cell | Burt's line (m² × R/m²) | MES |")
    say("|---|---|---|---|")
    for sh, tid in zip(ORDER, (3, 4, 5, 6)):
        g = [r for r in pu.get(sh, []) if "GALV PLATE" in r["label"].upper()]
        cell = g[0]["cells"].get("G", ["?"])[0] if g else "?"
        l = gold.get(sh)
        say(f"| {sh} | `{cell}` | " + (f"{R(l['qty'], 4)} × R{R(l['price'])} = R{R(l['total'])} (× 2 sides)" if l else "—")
            + " | " + ("a line exists" if tid in mes_galv else "**no galv plate line**") + " |")
    say("")
    say("- **Burt's sheets:** on all four standard sheets the line reads `'[1]MILD STEEL'!$D$28/2.98`. `D28` (1.2 MM "
        "PLATE) **has no price**, so the plate costs **R0**.")
    say("- **His correction:** his 7 Sep email (\"that should be 1,0mm Galv Plate\") re-points it to `D27` (1.0 MM, "
        "R478 a sheet → R160.40 / m², ≈ R239.73 per body for this line). That was made on seven other sheets, **not on "
        "the Manni sheets**.")
    say("- **MES:** it has **no galv plate line** on any Manni. Today both sides are R0. Once Burt's correction reaches the "
        "Manni sheets, MES is missing this line.")
    say("")
    say("### 3. Doors")
    say("")
    say("| sheet | Burt SRD | MES SRD | Burt SRD DOOR FITTINGS | MES SRD DOOR FITTINGS | REAR FRAME on SRD: Burt → MES |")
    say("|---|---:|---:|---:|---:|---|")
    for sh in ORDER:
        sc = {c["section_excel"] or c["section_mes"]: c for c in cells[(sh, "srd")]}
        rf = next((c for k, c in sc.items() if "REAR FRAME" in norm(k)), None)
        s1, s2 = sc.get("SRD"), sc.get("SRD DOOR FITTINGS")
        say(f"| {sh} | {R(s1 and s1['excel_total'])} | {R(s1 and s1['mes_total'])} | {R(s2 and s2['excel_total'])} | "
            f"{R(s2 and s2['mes_total'])} | {R(rf and rf['excel_total'])} → **{R(rf and rf['mes_total'])}** |")
    say("")
    say("**REAR FRAME on SRD:**")
    say("- **Burt** gates `REAR FRAME + FLOOR PLATE` on the DRD flags, so it is **R0 on a single rear door**, the same rule "
        "as the standard bodies (Manifest A).")
    say("- **MES** costs it on SRD for every Manni. The Mannis are not v2, so no per-line rule runs, and Manifest A never "
        "covered them.")
    say("")
    say("**MANNI DF** has a different door model:")
    say("- **Burt:** the sheet has `DRD` and `DRD INTO REAR PANEL`, and **no SRD**.")
    say("- **MES:** it has DRD and SRD sections, as the other bodies do.")
    say("")

    # ---- per body ----------------------------------------------------------------------------------------------
    for sh in ORDER:
        a = by_sheet[sh]["as_sheet"]
        sc = a["scenario"]
        say(f"## {BODY[sh]} — sheet `{sh}`, {sc['length']} × {sc['width']} × {sc['height']}")
        say("")
        say("| variant | Burt | MES | Δ |")
        say("|---|---:|---:|---:|")
        for v in VARIANTS:
            s = by_sheet[sh].get(v)
            if s:
                say(f"| {v} | {R(s['excel_grand'])} | {R(s['mes_grand'])} | {R(s['mes_grand'] - s['excel_grand'])} ({pct(s['mes_grand'], s['excel_grand'])}) |")
        say("")
        say("**Sections** (as sheet, DRD; the SRD sections from the `srd` scenario):")
        say("")
        say("| Burt section | MES section | Burt | MES | Δ | status | biggest line |")
        say("|---|---|---:|---:|---:|---|---|")
        sec_cells = [c for c in cells[(sh, "as_sheet")] if (c["section_excel"] or c["section_mes"]) not in DOOR_SECTIONS]
        sec_cells += [c for c in cells[(sh, "srd")] if (c["section_excel"] or c["section_mes"]) in DOOR_SECTIONS]
        for c in sec_cells:
            d = None if c["excel_total"] is None or c["mes_total"] is None else c["mes_total"] - c["excel_total"]
            st = c["status"] + (f" {c['reason']}" if c["status"] == "PRESENCE" and c.get("reason") else "")
            say(f"| {c['section_excel'] or '—'} | {c['section_mes'] or '—'} | {R(c['excel_total'])} | {R(c['mes_total'])} | "
                f"{R(d)} | {st} | {c.get('likely_cause') or ''} |")
        say("")
        say("**Lines that differ** (same scope; |Δ| ≥ R1, largest first):")
        say("")
        say("| section | line | class | Burt qty × price | MES qty × price | Δ | MES formula |")
        say("|---|---|---|---|---|---:|---|")
        tri = [(c["section_excel"] or c["section_mes"], t) for c in sec_cells for t in (c["triage"] or [])
               if t["cls"] != "OK" and abs(t.get("delta") or 0) >= 1]
        for sec, t in sorted(tri, key=lambda x: -abs(x[1].get("delta") or 0)):
            ex = "—" if t["excel_qty"] is None else f"{R(t['excel_qty'], 3)} × {R(t['excel_price'])}"
            me = "—" if t["mes_qty"] is None else f"{R(t['mes_qty'], 3)} × {R(t['mes_price'])}"
            say(f"| {sec} | {t['desc']} | {t['cls']} | {ex} | {me} | {R(t['delta'])} | `{(t.get('mes_formula') or '')[:60]}` |")
        say("")

    # ---- Manni DF ----------------------------------------------------------------------------------------------
    say(f"## {BODY['Manni DF']} — sheet `Manni DF` (dry-freight template), {sz[0]} × {sz[1]} × {sz[2]}")
    say("")
    opts = dx["options"]
    say("**Burt's options as saved** (Y): " + ", ".join(k for k, v in opts.items() if v == "Y") + ".")
    say("")
    say("**Burt's N options:** " + ", ".join(k for k, v in opts.items() if v == "N") + ".")
    say("")
    say("**The floor is chosen, not summed.** Burt's sheet has five floor sections and costs only the one whose option is "
        "**Y** (saved: 24MM WISA TRANS FLOOR). MES costs **all five** at once, with no option to choose between them. "
        "That alone is most of MANNI DF's R7.17 M (RT4_RETURN_2: each floor's 80×50×3 crossmembers at R8 891.12 a unit).")
    say("")
    mes_cat = defaultdict(float)
    mes_lines = defaultdict(list)
    for it in dm["DRD"]["items"]:
        mes_cat[norm(it["category"])] += float(it["line_cost"] or 0)
        mes_lines[norm(it["category"])].append(it)
    xs = {norm(s["name"]): s for s in dx["sections"]}
    say("| Burt section | option gate | Burt (gated) | MES (DRD) | Δ |")
    say("|---|---|---:|---:|---:|")
    seen = set()
    for s in dx["sections"]:
        k = norm(s["name"])
        seen.add(k)
        g = "" if s["gate"] is None else ("on" if s["gate"] else "OFF")
        m = mes_cat.get(k)
        say(f"| {s['name']} | {g} | {R(s['gated'])} | {R(m) if m is not None else '— (no MES section)'} | "
            f"{R((m or 0) - (s['gated'] or 0))} |")
    for k, v in sorted(mes_cat.items()):
        if k not in seen and abs(v) >= 0.005:
            say(f"| — | — | — | {R(v)} ({k}: MES only) | {R(v)} |")
    say("")
    say("**Lines in the sections Burt costs** (`on`, or ungated), matched by name. Burt's quantity and price are read "
        "from columns D / E (B when D is empty); his total is the sheet's own F:")
    say("")
    say("| section | line | Burt qty × price = total | MES qty × price = total | Δ |")
    say("|---|---|---|---|---:|")
    for s in dx["sections"]:
        if not s["gate"] and s["gate"] is not None:
            continue
        k = norm(s["name"])
        ml = list(mes_lines.get(k, []))
        for l in s["lines"]:
            if l["total"] is None:
                continue
            j = next((i for i, x in enumerate(ml) if norm(x["material"]) == norm(l["desc"])), None)
            x = ml.pop(j) if j is not None else None
            mt = float(x["line_cost"]) if x else 0.0
            if x is None or abs(mt - (l["total"] or 0)) >= 1:
                say(f"| {s['name']} | {l['desc']} | {R(l['qty'], 3)} × {R(l['price'])} = {R(l['total'])} | "
                    + (f"{R(x['quantity'], 3)} × {R(x['unit_price'])} = {R(mt)}" if x else "not in MES") + f" | {R(mt - (l['total'] or 0))} |")
        for x in ml:
            if abs(float(x["line_cost"] or 0)) >= 1:
                say(f"| {s['name']} | {x['material']} | not on Burt's sheet | {R(x['quantity'], 3)} × {R(x['unit_price'])} = "
                    f"{R(float(x['line_cost']))} | {R(float(x['line_cost']))} |")
    say("")
    (HERE / "MANNI_GAP_TABLE.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {HERE / 'MANNI_GAP_TABLE.md'} ({len(out)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
