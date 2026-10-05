# RT4 B.6 — the five Mannis against Burt's Manni sheets (report only)

**Fix nothing from this.** It is the input for the next job (RT4 dispatch B.6).

## Basis

- **Excel:** Burt's 21 Sep zip (`nuwepryslyste.zip`, sha256 `ee8e2159…`), with Burt's two written corrections applied on a copy, exactly as the costing audit's golden is (GRP `04c774e2…`). Neither correction touches a Manni sheet's own cells: the PU price they change is not referenced by any Manni sheet, and the 1.0 MM galv plate correction was made on seven other sheets only.
  - Four sheets (`Manni RIGIDS CB`, `Manni Bakkie Rigids`, `Manni RIGIDS FB`, `Manni TRAILERS`) through the audit's own oracle (LibreOffice recalculation of a copy). **Prove-then-trust passed on all four**: a recalculated copy at the saved inputs reproduces Burt's cached totals.
  - `Manni DF` is Burt's dry-freight template (inputs B3:B5, Y/N options, no insulation block). The audit cannot read it, so `manni_gap.py df` reads it directly. At its saved size the gated section totals add up to the sheet's GRAND TOTAL exactly (105 381.45 = 105 381.45).
- **MES:** prod's rows for the five Mannis, as exported read-only on 4 Oct (RT4 discovery). They were loaded into the prod mirror inside one transaction that was rolled back, and priced on the calculator path by the audit's own probe. Manifest S (5 Oct) only re-pointed section ids, and the mirror proof shows it priced identically to the cent. Material 182 is at prod's 4 Oct price.
- **Size:** each body at **prod's default size**. For the four standard sheets that equals Burt's saved size. MANNI DF's default (12.2 × 2.6 × 3.0) differs from its sheet's (7.2 × 2.6 × 2.7).
- **Variants:** as the audit's packs:
  - `as_sheet` is Burt's saved flags (DRD, PU);
  - `srd` swaps the door;
  - `all_eps` / `all_pu` set every panel;
  - `foam_4g` sets the PU grade.
  No accepted list: every difference shows. The audit report itself (HTML with the line drill-down) is `report/manni_gap.html`.

## Summary at the default size

| body | size | Burt (as sheet, DRD) | MES (DRD) | Δ | Burt SRD | MES SRD | sections FLAG / PRESENCE |
|---|---|---:|---:|---:|---:|---:|---|
| 3 MANNI RIGIDS CB | 7.5 × 2.6 × 2.6 | 117 183.64 | 112 379.32 | -4 804.32 (-4.1 %) | 113 351.55 | 112 612.34 | 6 / 0 |
| 4 MANNI BAKKI RIGIDS | 2.3 × 1.8 × 1.6 | 44 325.54 | 80 753.48 | 36 427.94 (+82.2 %) | 43 455.33 | 80 182.49 | 8 / 0 |
| 5 MANNI RIGIDS FB | 7.5 × 2.6 × 2.6 | 131 278.82 | 125 082.51 | -6 196.31 (-4.7 %) | 127 280.27 | 124 250.15 | 7 / 0 |
| 6 MANNI TRAILERS | 15.5 × 2.6 × 2.85 | 291 413.10 | 597 904.00 | 306 490.90 (+105.2 %) | 286 874.37 | 595 779.05 | 7 / 1 |
| 7 MANNI DF | 12.2 × 2.6 × 3.0 | 166 213.76 | 7 168 862.47 | 7 002 648.71 (+4213.0 %) | (no SRD on the sheet) | 7 150 772.55 | see its own section |

Grand totals are **material cost as the sheet computes it** (the audit's measure: the gated J / H column, before margin and ratio).

## What drives the gaps

1. **Prices that are really line TOTALS.**
   - **MANNI DF:** many unit prices equal **Burt's line total at the sheet's saved size**, so the total is multiplied by the quantity again. Examples: 34MM LOCKING POLE R252.00 = 6 × R42; 2316 INNER DOOR RUBBER R391.81; 0661-0631 RIVETS R360.50; TAPE R306.00; 4 MM BEND UP SUB FRAME R3 523.50; 80×50×3 CROSSMEMBERS R8 891.12. This looks like an import that read the dry-freight template's TOTAL column (F) as the price. That template's price is in E.
   - **RICE GRAIN FLOOR on BAKKI RIGIDS and TRAILERS:** **R24 356.25** a unit = Burt's R3 163.15 × 7.7, a line total. Δ +R35 392 and +R328 493.
2. **MANNI DF sums its five floors.** Burt's sheet costs only the floor whose option is Y (24MM WISA as saved). MES costs all five. Together with (1), MES is R7.17 M against Burt's R166 k.
3. **Material choices differ:**
   - **Renames only:** Burt's `RHINO PANEL` = MES `RHINOTEX SKINS 1375 BIOSHIELD`, at the same price.
   - **Different materials:** on TRAILERS, Burt has Rhinotex 2100 Bioshield / Crystex V2 / Rhinotex 1150 BW, where MES has Bioshield 4800 / Rhinopanel V2 / Rhinotex 2400.
   - **Price-list differences:** WOVEX SKIN R272.27 (Burt) vs R221.40 (MES); 18MM FINN PLY R375.84 vs R468.12; LVL R148.73 vs R130.54; BIG ALU CORNERS R43.92 vs **R496.05** (MES has the kick-plate price).
4. **Burt's own R0 prices:**
   - the 1.2MM GALV PLATE on all four standard sheets (§2 below);
   - WOVEX SKIN / Rhinotex Bioshield on **RIGIDS FB** (price cell empty).
   MES prices these where it has the line.
5. **Lines MES zeroes or never costs:**
   - every Manni's **SRD PU INJECTION** (`× 0`);
   - RIGIDS FB's RICE GRAIN FLOOR and ALU KICK PLATES (`× 0`), which Burt costs (flags Y);
   - lines missing in MES, e.g. FRONT `CHINESE EXTERNAL HIGH GLOSS` on MANNI DF, FLOOR `6MM FINN PLY FLOOR` on BAKKI.
6. **PU** is priced by weight on both sides, but with different densities, no 10 % waste in MES, and literal thicknesses (§1 below).
7. **Doors:** MES costs REAR FRAME & FLOOR PLATE on an SRD Manni. Burt does not (§3 below).

## Across the Mannis

### 1. PU: formula shape, and own price vs the shared PU price

**Both sides price PU by weight, thickness-based** (not the standard bodies' sheet-counting). But they differ in density, in waste, and in where the thickness comes from:

| sheet | Burt's PU INJECTION quantity (kg) | Burt's price | MES PU lines (formula · price) |
|---|---|---|---|
| Manni RIGIDS CB | `=D32*E32*C9*50*1.1` … (density 40, 50, 75 kg/m³) | `='[1]RESINS + ADESIVES'!$D$32` (R56.62/kg) | DRD: `(width-0.062)*(height-0.062-0.076)*0.062*40` · R56.62<br>FLOOR: `length*width*0.076*40` · R56.62<br>FRONT: `width*(height-0.062-0.076)*0.062*40` · R56.62<br>ROOF: `length*width*0.062*40` · R56.62<br>SIDES: `length*(height-0.062-0.076)*0.062*40` · R56.62<br>SRD: `(width-0.062-0.062+{Waste})*(height-0.062+{Waste})*0*40` · R56.62 |
| Manni Bakkie Rigids | `=D32*E32*C9*65*1.1` … (density 65, 75 kg/m³) | `='[1]RESINS + ADESIVES'!$D$32` (R56.62/kg) | DRD: `(width-0.062)*(height-0.062-{Waste})*0.062*50` · R56.62<br>FLOOR: `length*width*{Waste}*50` · R56.62<br>FRONT: `width*(height-0.062-{Waste})*0.062*50` · R56.62<br>ROOF: `length*width*0.062*50` · R56.62<br>SIDES: `length*(height-0.062-{Waste})*0.062*50` · R56.62<br>SRD: `(width-0.062-0.062+{Waste})*(height-0.062+{Waste})*0*40` · R56.62 |
| Manni RIGIDS FB | `=D32*E32*C9*65*1.1` … (density 65, 75 kg/m³) | `='[1]RESINS + ADESIVES'!$D$32` (R56.62/kg) | DRD: `(width-0.062)*(height-0.076-0.076)*0.062*65` · R56.62<br>FLOOR: `length*width*0.076*65` · R56.62<br>FRONT: `width*(height-0.076-0.076)*0.062*65` · R56.62<br>ROOF: `length*width*0.076*65` · R56.62<br>SIDES: `length*(height-0.076-0.076)*0.062*65` · R56.62<br>SRD: `(width-0.062-0.062+{Waste})*(height-0.076+{Waste})*0*40` · R56.62 |
| Manni TRAILERS | `=D32*E32*C9*65*1.1` … (density 65, 75 kg/m³) | `='[1]RESINS + ADESIVES'!$D$32` (R56.62/kg) | DRD: `(width-0.062)*(height-0.097-0.076)*0.097*65` · R56.62<br>FLOOR: `length*width*0.076*75` · R56.62<br>FRONT: `width*(height-0.097-0.076)*0.097*65` · R56.62<br>ROOF: `length*width*0.097*65` · R56.62<br>SIDES: `length*(height-0.097-0.076)*0.062*65` · R56.62<br>SRD: `(width-0.062-0.062+{Waste})*(height-0.097+{Waste})*0*40` · R56.62 |
| Manni DF | `=B36*C36*0.032*65*1.1` … (density 65 kg/m³) | `='[1]RESINS + ADESIVES'!$D$32` (R56.62/kg) | DRD: `width*height*0.032*50` · R60.00<br>FRONT: `width*height*0.032*50` · R60.00<br>ROOF: `(length+{Waste})*(width+{Waste})*0.062*50` · R60.00<br>SIDES: `(length+{Waste})*height*0.032*50` · R60.00<br>SRD: `width*height*0.03*40` · R60.00 |

- **The price source:**
  - **Burt:** every Manni sheet reads `'[1]RESINS + ADESIVES'!$D$32`: resin `R250820/1A`, **R56.62 / kg**, its **own price**. It is not the shared PU price (`[1]PU!$C$17`, 32D foam R4 100), so the audit marks every Manni sheet **NO_4G_REFERENCE**: the 4G grade cannot be expressed.
  - **MES:** its `PU INJECTION` lines carry the same R56.62 as their own price (MANNI DF: **R60.00**). So **`foam_4g` = `as_sheet` on both sides**: the 32D / 4G choice does nothing on a Manni.
- **The shape:** both are thickness-based kilograms (area × thickness × density), not the standard bodies' sheet-counting. But the details differ:
  - **Burt:** `width × height × the panel's thickness CELL × density × 1.1`. The density is 65 kg/m³ (RIGIDS CB 50, its SRD 40; floors 75), and the waste is 10 %.
  - **MES:** `area × a LITERAL thickness × density`, with no × 1.1. MES density by body: RIGIDS CB 40; Bakkie Rigids 50; RIGIDS FB 65; TRAILERS 65, 75; DF 40, 50. So:
    - the thickness never follows the quote's own thickness;
    - BAKKIE RIGIDS uses `{Waste}` where a thickness belongs (its FLOOR, and the height deductions);
    - **every Manni's SRD PU line multiplies by `0`** (ZERO_FORMULA): MES never costs PU in an SRD door.

### 2. The 1.2MM GALV PLATE in SUB FRAME + LIGHT BOX ASSY

| sheet | Burt's price cell | Burt's line (m² × R/m²) | MES |
|---|---|---|---|
| Manni RIGIDS CB | `='[1]MILD STEEL'!$D$28/2.98` | 0.7472 × R0.00 = R0.00 (× 2 sides) | **no galv plate line** |
| Manni Bakkie Rigids | `='[1]MILD STEEL'!$D$28/2.98` | 0.7472 × R0.00 = R0.00 (× 2 sides) | **no galv plate line** |
| Manni RIGIDS FB | `='[1]MILD STEEL'!$D$28/2.98` | 0.7472 × R0.00 = R0.00 (× 2 sides) | **no galv plate line** |
| Manni TRAILERS | `='[1]MILD STEEL'!$D$28/2.98` | 0.7472 × R0.00 = R0.00 (× 2 sides) | **no galv plate line** |

- **Burt's sheets:** on all four standard sheets the line reads `'[1]MILD STEEL'!$D$28/2.98`. `D28` (1.2 MM PLATE) **has no price**, so the plate costs **R0**.
- **His correction:** his 7 Sep email ("that should be 1,0mm Galv Plate") re-points it to `D27` (1.0 MM, R478 a sheet → R160.40 / m², ≈ R239.73 per body for this line). That was made on seven other sheets, **not on the Manni sheets**.
- **MES:** it has **no galv plate line** on any Manni. Today both sides are R0. Once Burt's correction reaches the Manni sheets, MES is missing this line.

### 3. Doors

| sheet | Burt SRD | MES SRD | Burt SRD DOOR FITTINGS | MES SRD DOOR FITTINGS | REAR FRAME on SRD: Burt → MES |
|---|---:|---:|---:|---:|---|
| Manni RIGIDS CB | 4 732.73 | 3 443.71 | 7 487.79 | 7 470.21 | 0.00 → **5 313.51** |
| Manni Bakkie Rigids | 2 259.27 | 1 617.15 | 5 782.24 | 5 467.78 | 0.00 → **2 199.68** |
| Manni RIGIDS FB | 2 952.89 | 3 656.93 | 7 455.57 | 7 019.02 | 0.00 → **5 313.51** |
| Manni TRAILERS | 5 894.38 | 3 442.52 | 7 734.66 | 7 270.25 | 0.00 → **5 410.09** |

**REAR FRAME on SRD:**
- **Burt** gates `REAR FRAME + FLOOR PLATE` on the DRD flags, so it is **R0 on a single rear door**, the same rule as the standard bodies (Manifest A).
- **MES** costs it on SRD for every Manni. The Mannis are not v2, so no per-line rule runs, and Manifest A never covered them.

**MANNI DF** has a different door model:
- **Burt:** the sheet has `DRD` and `DRD INTO REAR PANEL`, and **no SRD**.
- **MES:** it has DRD and SRD sections, as the other bodies do.

## 3 MANNI RIGIDS CB — sheet `Manni RIGIDS CB`, 7.5 × 2.6 × 2.6

| variant | Burt | MES | Δ |
|---|---:|---:|---:|
| as_sheet | 117 183.64 | 112 379.32 | -4 804.32 (-4.1 %) |
| drd | 117 183.64 | 112 379.32 | -4 804.32 (-4.1 %) |
| srd | 113 351.55 | 112 612.34 | -739.21 (-0.7 %) |
| all_pu | 117 183.64 | 112 379.32 | -4 804.32 (-4.1 %) |
| all_eps | 103 079.56 | 99 128.13 | -3 951.43 (-3.8 %) |
| foam_4g | 117 183.64 | 112 379.32 | -4 804.32 (-4.1 %) |

**Sections** (as sheet, DRD; the SRD sections from the `srd` scenario):

| Burt section | MES section | Burt | MES | Δ | status | biggest line |
|---|---|---:|---:|---:|---|---|
| FRONT | FRONT | 6 769.66 | 5 843.99 | -925.67 | FLAG | MISSING_IN_MES RHINO PANEL (-1772.59) |
| DRD | DRD | 4 860.49 | 4 601.72 | -258.77 | FLAG | BOTH Rhinotex Bioshield (-350.69) |
| DRD DOOR FITTINGS | DRD DOOR FITTINGS | 6 111.09 | 6 079.85 | -31.24 | PASS |  |
| SIDES | SIDES | 26 818.96 | 25 565.87 | -1 253.09 | FLAG | BOTH WOVEX SKIN (-1976.65) |
| ROOF | ROOF | 11 867.88 | 11 325.81 | -542.07 | FLAG | PRICE_DIFF WOVEX SKIN (-991.97) |
| FLOOR | FLOOR | 31 406.67 | 29 380.72 | -2 025.95 | FLAG | QTY_DIFF PU INJECTION (-2936.83) |
| ALUMINIUM | ALUMINIUM | 13 646.15 | 13 646.15 | 0.00 | PASS |  |
| SUB FRAME + LIGHT BOX ASSY | SUB FRAME + LIGHT BOX ASSY | 9 554.91 | 9 554.91 | -0.00 | PASS |  |
| REAR FRAME + FLOOR PLATE | REAR FRAME & FLOOR PLATE | 5 081.02 | 5 313.51 | 232.49 | FLAG | PRICE_DIFF 3MM 3CR12 FLOOR PLATE (+232.49) |
| SPRAY PAINTING | SPRAY PAINTING | 750.00 | 750.00 | 0.00 | PASS |  |
| REFLEXITE TAPE | REFLEXITE TAPE | 316.80 | 316.80 | 0.00 | PASS |  |
| SRD | SRD | 4 732.73 | 3 443.71 | -1 289.02 | FLAG | QTY_DIFF PU INJECTION (-1004.96) [ZERO_FORMULA] |
| SRD DOOR FITTINGS | SRD DOOR FITTINGS | 7 487.79 | 7 470.21 | -17.58 | PASS |  |

**Lines that differ** (same scope; |Δ| ≥ R1, largest first):

| section | line | class | Burt qty × price | MES qty × price | Δ | MES formula |
|---|---|---|---|---|---:|---|
| FLOOR | PU INJECTION | QTY_DIFF | 111.150 × 56.62 | 59.280 × 56.62 | -2 936.83 | `length*width*0.076*40` |
| SIDES | WOVEX SKIN | BOTH | 37.290 × 272.27 | 36.930 × 221.40 | -1 976.65 | `length*(height-0.062-0.076)` |
| FLOOR | 18MM FINN PLY FLOOR | PRICE_DIFF | 19.500 × 375.84 | 19.500 × 468.12 | 1 799.50 | `length*width` |
| FRONT | RHINO PANEL | MISSING_IN_MES | 6.723 × 263.65 | — | -1 772.59 | `` |
| FRONT | RHINOTEX SKINS 1375 BIOSHIELD | EXTRA_IN_MES | — | 6.723 × 263.65 | 1 772.59 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | PU INJECTION | QTY_DIFF | 17.749 × 56.62 | 0.000 × 56.62 | -1 004.96 | `(width-0.062-0.062+{Waste})*(height-0.062+{Waste})*0*40` |
| ROOF | WOVEX SKIN | PRICE_DIFF | 19.500 × 272.27 | 19.500 × 221.40 | -991.97 | `length*width` |
| FLOOR | 76*50 LVL BEAMS | BOTH | 18.443 × 148.73 | 48.873 × 130.54 | -888.62 | `(length/0.305-7.5/1.22)*2.65` |
| SIDES | PU INJECTION | QTY_DIFF | 77.936 × 56.62 | 91.586 × 56.62 | 772.86 | `length*(height-0.062-0.076)*0.062*40` |
| ROOF | PU INJECTION | QTY_DIFF | 40.755 × 56.62 | 48.360 × 56.62 | 430.59 | `length*width*0.062*40` |
| DRD | Rhinotex Bioshield | BOTH | 6.369 × 272.27 | 6.249 × 221.40 | -350.69 | `(width-0.062)*(height-0.062-0.076)` |
| FRONT | PU INJECTION | QTY_DIFF | 22.041 × 56.62 | 15.875 × 56.62 | -349.10 | `width*(height-0.062-0.076)*0.062*40` |
| FRONT | Rhinotex Bioshield | PRICE_DIFF | 6.723 × 272.27 | 6.723 × 221.40 | -342.01 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | WOVEX SKIN | PRICE_DIFF | 6.723 × 272.27 | 6.723 × 221.40 | -342.01 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SIDES | LVL BOTTOM BEAM | PRICE_DIFF | 15.000 × 148.73 | 15.000 × 130.54 | -272.74 | `length` |
| REAR FRAME + FLOOR PLATE | 3MM 3CR12 FLOOR PLATE | PRICE_DIFF | 3.125 × 965.76 | 3.125 × 1 040.16 | 232.49 | `1.25*2.5` |
| SIDES | WOVEX SKIN | BOTH | 37.290 × 263.65 | 36.930 × 272.27 | 223.42 | `length*(height-0.062-0.076)` |
| FRONT | FRIDGE FRAME LVL | PRICE_DIFF | 10.300 × 148.73 | 10.300 × 130.54 | -187.28 | `(height*2+1.25*2+width)` |
| DRD | PU INJECTION | QTY_DIFF | 13.311 × 56.62 | 15.496 × 56.62 | 123.71 | `(width-0.062)*(height-0.062-0.076)*0.062*40` |
| SRD | WOVEX SKIN | PRICE_DIFF | 6.723 × 263.65 | 6.723 × 272.27 | 57.96 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| FRONT | 58MM PICTURE FRAME | PRICE_DIFF | 2.600 × 148.73 | 2.600 × 130.54 | -47.27 | `(0+width)` |
| DRD | RHINO PANEL | QTY_DIFF | 6.369 × 263.65 | 6.249 × 263.65 | -31.79 | `(width-0.062)*(height-0.062-0.076)` |

## 4 MANNI BAKKI RIGIDS — sheet `Manni Bakkie Rigids`, 2.3 × 1.8 × 1.6

| variant | Burt | MES | Δ |
|---|---:|---:|---:|
| as_sheet | 44 325.54 | 80 753.48 | 36 427.94 (+82.2 %) |
| drd | 44 325.54 | 80 753.48 | 36 427.94 (+82.2 %) |
| srd | 43 455.33 | 80 182.49 | 36 727.16 (+84.5 %) |
| all_pu | 44 325.54 | 80 753.48 | 36 427.94 (+82.2 %) |
| all_eps | 39 764.53 | 77 276.71 | 37 512.18 (+94.3 %) |
| foam_4g | 44 325.54 | 80 753.48 | 36 427.94 (+82.2 %) |

**Sections** (as sheet, DRD; the SRD sections from the `srd` scenario):

| Burt section | MES section | Burt | MES | Δ | status | biggest line |
|---|---|---:|---:|---:|---|---|
| FRONT | FRONT | 3 152.50 | 2 884.90 | -267.60 | FLAG | EXTRA_IN_MES RHINOTEX SKINS 1375 BIOSHIELD (+722.64) |
| DRD | DRD | 2 728.53 | 2 533.34 | -195.19 | FLAG | QTY_DIFF PU INJECTION (-195.18) |
| DRD DOOR FITTINGS | DRD DOOR FITTINGS | 4 599.63 | 5 123.22 | 523.59 | FLAG | PRICE_DIFF 3MM ALU BUFFER PLATE (+329.15) |
| SIDES | SIDES | 6 261.33 | 5 803.73 | -457.60 | FLAG | QTY_DIFF PU INJECTION (-516.60) |
| ROOF | ROOF | 3 184.00 | 3 076.51 | -107.49 | FLAG | QTY_DIFF PU INJECTION (-312.46) |
| FLOOR | FLOOR | 12 686.69 | 46 584.91 | 33 898.22 | FLAG | PRICE_DIFF RICE GRAIN FLOOR (+35392.48) |
| ALUMINIUM | ALUMINIUM | 3 940.00 | 6 357.90 | 2 417.90 | FLAG | PRICE_DIFF BIG ALU CORNERS (+1808.52) |
| SUB FRAME + LIGHT BOX ASSY | SUB FRAME + LIGHT BOX ASSY | 5 324.10 | 5 324.10 | 0.00 | PASS |  |
| REAR FRAME + FLOOR PLATE | REAR FRAME & FLOOR PLATE | 1 583.57 | 2 199.68 | 616.11 | FLAG | PRICE_DIFF 3MM 3CR12 FLOOR PLATE (+364.54) |
| SPRAY PAINTING | SPRAY PAINTING | 750.00 | 750.00 | 0.00 | PASS |  |
| REFLEXITE TAPE | REFLEXITE TAPE | 115.20 | 115.20 | 0.00 | PASS |  |
| SRD | SRD | 2 259.27 | 1 617.15 | -642.12 | FLAG | QTY_DIFF PU INJECTION (-665.75) [ZERO_FORMULA] |
| SRD DOOR FITTINGS | SRD DOOR FITTINGS | 5 782.24 | 5 467.78 | -314.46 | FLAG | PRICE_DIFF 28781 SMALL HORIZ CAPPING (-156.17) |

**Lines that differ** (same scope; |Δ| ≥ R1, largest first):

| section | line | class | Burt qty × price | MES qty × price | Δ | MES formula |
|---|---|---|---|---|---:|---|
| FLOOR | RICE GRAIN FLOOR | PRICE_DIFF | 1.670 × 3 163.15 | 1.670 × 24 356.25 | 35 392.48 | `(width-0.13)` |
| ALUMINIUM | BIG ALU CORNERS | PRICE_DIFF | 4.000 × 43.92 | 4.000 × 496.05 | 1 808.52 | `4` |
| FRONT | RHINOTEX SKINS 1375 BIOSHIELD | EXTRA_IN_MES | — | 2.741 × 263.65 | 722.64 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| FRONT | RHINO PANEL | MISSING_IN_MES | 2.741 × 263.65 | — | -722.64 | `` |
| FLOOR | 6MM FINN PLY FLOOR | MISSING_IN_MES | 4.140 × 171.14 | — | -708.52 | `` |
| SRD | PU INJECTION | QTY_DIFF | 11.758 × 56.62 | 0.000 × 56.62 | -665.75 | `(width-0.062-0.062+{Waste})*(height-0.062+{Waste})*0*40` |
| FLOOR | ALU KICK PLATES | PRICE_DIFF | 6.270 × 496.05 | 6.270 × 406.60 | -560.85 | `(length*2+(width-0.13))` |
| SIDES | PU INJECTION | QTY_DIFF | 30.343 × 56.62 | 21.219 × 56.62 | -516.60 | `length*(height-0.062-{Waste})*0.062*50` |
| ALUMINIUM | 28782 SMALL HORIZONTALE CAP | PRICE_DIFF | 12.400 × 203.25 | 12.400 × 242.90 | 491.66 | `(length*4+height+height)` |
| REAR FRAME + FLOOR PLATE | 3MM 3CR12 FLOOR PLATE | PRICE_DIFF | 1.038 × 614.40 | 1.038 × 965.76 | 364.54 | `0.415*2.5` |
| DRD DOOR FITTINGS | 3MM ALU BUFFER PLATE | PRICE_DIFF | 2.000 × 164.57 | 2.000 × 329.15 | 329.15 | `2` |
| ROOF | PU INJECTION | QTY_DIFF | 18.353 × 56.62 | 12.834 × 56.62 | -312.46 | `length*width*0.062*50` |
| FLOOR | PU INJECTION | QTY_DIFF | 15.525 × 56.62 | 10.350 × 56.62 | -293.00 | `length*width*{Waste}*50` |
| ROOF | WOVEX SKIN | PRICE_DIFF | 4.140 × 222.76 | 4.140 × 272.27 | 204.97 | `length*width` |
| FRONT | PU INJECTION | QTY_DIFF | 11.873 × 56.62 | 8.303 × 56.62 | -202.15 | `width*(height-0.062-{Waste})*0.062*50` |
| DRD | PU INJECTION | QTY_DIFF | 11.464 × 56.62 | 8.017 × 56.62 | -195.18 | `(width-0.062)*(height-0.062-{Waste})*0.062*50` |
| DRD DOOR FITTINGS | D-RUBBER | PRICE_DIFF | 2.000 × 97.22 | 2.000 × 194.44 | 194.43 | `2` |
| SRD DOOR FITTINGS | 28781 SMALL HORIZ CAPPING | PRICE_DIFF | 3.600 × 240.58 | 3.600 × 197.20 | -156.17 | `(width+width)` |
| REAR FRAME + FLOOR PLATE | TOP FRAME RAIN GUTTER | PRICE_DIFF | 0.396 × 614.40 | 0.396 × 965.76 | 139.14 | `0.22*width` |
| SRD DOOR FITTINGS | 28779 DOOR CAPPING | PRICE_DIFF | 4.876 × 149.08 | 4.876 × 122.20 | -131.06 | `((height-0.062+{Waste})*2+0.85+0.85)` |
| ALUMINIUM | 28780 SMALL VERTICAL | PRICE_DIFF | 3.600 × 149.08 | 3.600 × 181.78 | 117.72 | `width*2` |
| REAR FRAME + FLOOR PLATE | 2MM 3CR12 REAR FRAME | PRICE_DIFF | 0.320 × 614.40 | 0.320 × 965.76 | 112.43 | `0.1*height*2` |
| SRD DOOR FITTINGS | 28777 DOOR CAPPING | PRICE_DIFF | 4.026 × 132.13 | 4.026 × 108.30 | -95.94 | `((height-0.062+{Waste})*2+0.85)` |
| SRD DOOR FITTINGS | 28780 SMALL VERTICAL | PRICE_DIFF | 3.200 × 181.78 | 3.200 × 203.25 | 68.70 | `(height+height)` |
| FLOOR | 76(50)*50 LVL BEAMS | BOTH | 4.541 × 106.79 | 12.034 × 112.45 | 68.12 | `(length/0.305-3)*2.65` |
| FRONT | EVAPORATOR LVL BEAMS IN ROOF | PRICE_DIFF | 3.600 × 148.73 | 3.600 × 130.54 | -65.46 | `(0+width*2)` |
| SIDES | WOVEX SKIN | PRICE_DIFF | 6.845 × 263.65 | 6.845 × 272.27 | 59.00 | `length*(height-0.062-{Waste})` |
| SRD | WOVEX SKIN | PRICE_DIFF | 2.741 × 263.65 | 2.741 × 272.27 | 23.62 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |

## 5 MANNI RIGIDS FB — sheet `Manni RIGIDS FB`, 7.5 × 2.6 × 2.6

| variant | Burt | MES | Δ |
|---|---:|---:|---:|
| as_sheet | 131 278.82 | 125 082.51 | -6 196.31 (-4.7 %) |
| drd | 131 278.82 | 125 082.51 | -6 196.31 (-4.7 %) |
| srd | 127 280.27 | 124 250.15 | -3 030.12 (-2.4 %) |
| all_pu | 131 278.82 | 125 082.51 | -6 196.31 (-4.7 %) |
| all_eps | 106 806.01 | 102 837.04 | -3 968.97 (-3.7 %) |
| foam_4g | 131 278.82 | 125 082.51 | -6 196.31 (-4.7 %) |

**Sections** (as sheet, DRD; the SRD sections from the `srd` scenario):

| Burt section | MES section | Burt | MES | Δ | status | biggest line |
|---|---|---:|---:|---:|---|---|
| FRONT | FRONT | 4 378.15 | 6 460.57 | 2 082.42 | FLAG | BOTH Rhinotex Bioshield (+1766.15) |
| DRD | DRD | 3 262.82 | 5 440.80 | 2 177.98 | FLAG | BOTH Rhinotex Bioshield (+1691.62) |
| DRD DOOR FITTINGS | DRD DOOR FITTINGS | 6 063.16 | 6 068.17 | 5.01 | PASS |  |
| SIDES | SIDES | 18 689.30 | 30 795.92 | 12 106.62 | FLAG | BOTH WOVEX SKIN (+9997.75) |
| ROOF | ROOF | 10 334.28 | 16 168.11 | 5 833.83 | FLAG | BOTH WOVEX SKIN (+5309.26) |
| FLOOR | FLOOR | 61 010.74 | 30 567.58 | -30 443.16 | FLAG | BOTH RICE GRAIN FLOOR (-23723.62) [ZERO_FORMULA] |
| ALUMINIUM | ALUMINIUM | 11 837.63 | 13 646.15 | 1 808.52 | FLAG | PRICE_DIFF BIG ALU CORNERS (+1808.52) |
| SUB FRAME + LIGHT BOX ASSY | SUB FRAME + LIGHT BOX ASSY | 9 554.91 | 9 554.91 | -0.00 | PASS |  |
| REAR FRAME + FLOOR PLATE | REAR FRAME & FLOOR PLATE | 5 081.02 | 5 313.51 | 232.49 | FLAG | PRICE_DIFF 3MM 3CR12 FLOOR PLATE (+232.49) |
| SPRAY PAINTING | SPRAY PAINTING | 750.00 | 750.00 | 0.00 | PASS |  |
| REFLEXITE TAPE | REFLEXITE TAPE | 316.80 | 316.80 | 0.00 | PASS |  |
| SRD | SRD | 2 952.89 | 3 656.93 | 704.04 | FLAG | BOTH WOVEX SKIN (+1766.15) |
| SRD DOOR FITTINGS | SRD DOOR FITTINGS | 7 455.57 | 7 019.02 | -436.55 | FLAG | PRICE_DIFF 28781 SMALL HORIZ CAPPING (-225.58) |

**Lines that differ** (same scope; |Δ| ≥ R1, largest first):

| section | line | class | Burt qty × price | MES qty × price | Δ | MES formula |
|---|---|---|---|---|---:|---|
| FLOOR | RICE GRAIN FLOOR | BOTH | 7.500 × 3 163.15 | 0.000 × 24 356.25 | -23 723.62 | `length*0` |
| SIDES | WOVEX SKIN | BOTH | 36.630 × 0.00 | 36.720 × 272.27 | 9 997.75 | `length*(height-0.076-0.076)` |
| FLOOR | ALU KICK PLATES | BOTH | 17.600 × 496.05 | 0.000 × 406.60 | -8 730.48 | `(length*2+width)*0` |
| ROOF | WOVEX SKIN | BOTH | 19.500 × 0.00 | 19.500 × 272.27 | 5 309.26 | `length*width` |
| SIDES | WOVEX SKIN | PRICE_DIFF | 36.630 × 193.11 | 36.720 × 272.27 | 2 924.13 | `length*(height-0.076-0.076)` |
| FLOOR | 2*300 INT LAMINATION | BOTH | 52.140 × 50.15 | 52.140 × 50.15 | 2 615.03 | `(length+0.4)*(width+0.7)*2` |
| ALUMINIUM | BIG ALU CORNERS | PRICE_DIFF | 4.000 × 43.92 | 4.000 × 496.05 | 1 808.52 | `4` |
| FRONT | Rhinotex Bioshield | BOTH | 6.487 × 0.00 | 6.487 × 272.27 | 1 766.15 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | WOVEX SKIN | BOTH | 6.487 × 0.00 | 6.487 × 272.27 | 1 766.15 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| FRONT | RHINOTEX SKINS 1375 BIOSHIELD | EXTRA_IN_MES | — | 6.487 × 263.65 | 1 710.24 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| DRD | Rhinotex Bioshield | BOTH | 6.198 × 0.00 | 6.213 × 272.27 | 1 691.62 | `(width-0.062)*(height-0.076-0.076)` |
| SRD | PU INJECTION | QTY_DIFF | 27.828 × 56.62 | 0.000 × 56.62 | -1 575.61 | `(width-0.062-0.062+{Waste})*(height-0.076+{Waste})*0*40` |
| ROOF | WOVEX SKIN | PRICE_DIFF | 19.500 × 193.11 | 19.500 × 272.27 | 1 543.62 | `length*width` |
| FLOOR | 18MM FINN PLY FLOOR | PRICE_DIFF | 19.500 × 454.70 | 19.500 × 375.84 | -1 537.75 | `length*width` |
| FRONT | RHINO PANEL | MISSING_IN_MES | 6.487 × 193.11 | — | -1 252.66 | `` |
| FLOOR | ANTI-SKID FINAL COAT | BOTH | 26.070 × 45.82 | 26.070 × 45.82 | 1 194.58 | `(length+0.4)*(width+0.7)*2/2` |
| ROOF | PU INJECTION | QTY_DIFF | 114.329 × 56.62 | 96.330 × 56.62 | -1 019.06 | `length*width*0.076*65` |
| FLOOR | PU INJECTION | QTY_DIFF | 111.150 × 56.62 | 96.330 × 56.62 | -839.10 | `length*width*0.076*65` |
| SIDES | PU INJECTION | QTY_DIFF | 162.381 × 56.62 | 147.982 × 56.62 | -815.27 | `length*(height-0.076-0.076)*0.062*65` |
| FLOOR | WOVEX SKIN | PRICE_DIFF | 19.500 × 193.11 | 19.500 × 222.76 | 578.17 | `length*width` |
| SRD | WOVEX SKIN | PRICE_DIFF | 6.487 × 193.11 | 6.487 × 272.27 | 513.49 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| DRD | RHINO PANEL | PRICE_DIFF | 6.198 × 193.11 | 6.213 × 263.65 | 441.20 | `(width-0.062)*(height-0.076-0.076)` |
| REAR FRAME + FLOOR PLATE | 3MM 3CR12 FLOOR PLATE | PRICE_DIFF | 3.125 × 965.76 | 3.125 × 1 040.16 | 232.49 | `1.25*2.5` |
| SRD DOOR FITTINGS | 28781 SMALL HORIZ CAPPING | PRICE_DIFF | 5.200 × 240.58 | 5.200 × 197.20 | -225.58 | `(width+width)` |
| DRD | 8MM TAPPING PLATE | PRICE_DIFF | 4.300 × 118.69 | 4.300 × 161.27 | 183.09 | `(7*0.2*2+3*0.25*2)` |
| SRD DOOR FITTINGS | 28779 DOOR CAPPING | PRICE_DIFF | 6.836 × 149.08 | 6.848 × 122.20 | -182.28 | `((height-0.076+{Waste})*2+0.85+0.85)` |
| SRD DOOR FITTINGS | 28777 DOOR CAPPING | PRICE_DIFF | 5.986 × 132.13 | 5.998 × 108.30 | -141.35 | `((height-0.076+{Waste})*2+0.85)` |
| FRONT | PU INJECTION | QTY_DIFF | 28.146 × 56.62 | 25.650 × 56.62 | -141.31 | `width*(height-0.076-0.076)*0.062*65` |
| DRD | PU INJECTION | QTY_DIFF | 27.475 × 56.62 | 25.038 × 56.62 | -137.94 | `(width-0.062)*(height-0.076-0.076)*0.062*65` |
| SRD DOOR FITTINGS | 28780 SMALL VERTICAL | PRICE_DIFF | 5.200 × 181.78 | 5.200 × 203.25 | 111.64 | `(height+height)` |

## 6 MANNI TRAILERS — sheet `Manni TRAILERS`, 15.5 × 2.6 × 2.85

| variant | Burt | MES | Δ |
|---|---:|---:|---:|
| as_sheet | 291 413.10 | 597 904.00 | 306 490.90 (+105.2 %) |
| drd | 291 413.10 | 597 904.00 | 306 490.90 (+105.2 %) |
| srd | 286 874.37 | 595 779.05 | 308 904.68 (+107.7 %) |
| all_pu | 291 413.10 | 597 904.00 | 306 490.90 (+105.2 %) |
| all_eps | 242 956.72 | 546 589.36 | 303 632.64 (+125.0 %) |
| foam_4g | 291 413.10 | 597 904.00 | 306 490.90 (+105.2 %) |

**Sections** (as sheet, DRD; the SRD sections from the `srd` scenario):

| Burt section | MES section | Burt | MES | Δ | status | biggest line |
|---|---|---:|---:|---:|---|---|
| FRONT | FRONT | 8 044.81 | 7 325.00 | -719.81 | FLAG | MISSING_IN_MES Rhinotex 2100 Bioshield (-2102.67) |
| INT FALSE BULKHEAD | INT FALSE BULKHEAD | 7 507.48 | 6 518.80 | -988.68 | FLAG | PRICE_DIFF 3MM ALU PLATE (-988.68) |
| DRD | DRD | 6 425.03 | 6 285.74 | -139.29 | FLAG | MISSING_IN_MES Rhinitex 2100 Bioshield (-2018.19) |
| DRD DOOR FITTINGS | DRD DOOR FITTINGS | 6 565.14 | 6 552.63 | -12.51 | PASS |  |
| SIDES | SIDES | 73 119.64 | 62 418.08 | -10 701.56 | FLAG | MISSING_IN_MES Rhinotex 2100 Bioshield (-24650.89) |
| ROOF | ROOF | 33 965.90 | 31 781.46 | -2 184.44 | FLAG | MISSING_IN_MES Rhinotex 2100 Bioshield (-11904.22) |
| FLOOR | FLOOR | 125 519.16 | 433 080.93 | 307 561.77 | FLAG | PRICE_DIFF RICE GRAIN FLOOR (+328493.07) |
| ALUMINIUM | ALUMINIUM | 23 733.55 | 23 733.55 | 0.00 | PASS |  |
| SUB FRAME + LIGHT BOX ASSY | SUB FRAME + LIGHT BOX ASSY | 0.00 | 13 442.91 | 13 442.91 | PRESENCE EXTRA_IN_MES |  |
| REAR FRAME + FLOOR PLATE | REAR FRAME & FLOOR PLATE | 5 177.60 | 5 410.09 | 232.49 | FLAG | PRICE_DIFF 3MM 3CR12 FLOOR PLATE (+232.49) |
| SPRAY PAINTING | SPRAY PAINTING | 750.00 | 750.00 | 0.00 | PASS |  |
| REFLEXITE TAPE | REFLEXITE TAPE | 604.80 | 604.80 | 0.00 | PASS |  |
| SRD | SRD | 5 894.38 | 3 442.52 | -2 451.86 | FLAG | MISSING_IN_MES Rhinotex 2100 Bioshield (-2102.67) |
| SRD DOOR FITTINGS | SRD DOOR FITTINGS | 7 734.66 | 7 270.25 | -464.41 | FLAG | PRICE_DIFF 28781 SMALL HORIZ CAPPING (-225.58) |

**Lines that differ** (same scope; |Δ| ≥ R1, largest first):

| section | line | class | Burt qty × price | MES qty × price | Δ | MES formula |
|---|---|---|---|---|---:|---|
| FLOOR | RICE GRAIN FLOOR | PRICE_DIFF | 15.500 × 3 163.15 | 15.500 × 24 356.25 | 328 493.07 | `length` |
| SIDES | Rhinotex 2100 Bioshield | MISSING_IN_MES | 83.452 × 295.39 | — | -24 650.89 | `` |
| SIDES | Crystex V2 | MISSING_IN_MES | 83.452 × 272.27 | — | -22 721.48 | `` |
| SIDES | Bioshield 4800 | EXTRA_IN_MES | — | 82.987 × 243.11 | 20 174.97 | `length*(height-0.097-0.076)` |
| SIDES | Rhinopanel V2 | EXTRA_IN_MES | — | 82.987 × 223.00 | 18 506.10 | `length*(height-0.097-0.076)` |
| FLOOR | 18MM FINN PLY FLOOR | MISSING_IN_MES | 40.300 × 454.70 | — | -18 324.33 | `` |
| ROOF | Rhinotex 2100 Bioshield | MISSING_IN_MES | 40.300 × 295.39 | — | -11 904.22 | `` |
| ROOF | Bioshield 4800 | EXTRA_IN_MES | — | 40.300 × 243.11 | 9 797.33 | `length*width` |
| FLOOR | Rhinotex 2400 | EXTRA_IN_MES | — | 40.300 × 223.00 | 8 986.90 | `length*width` |
| ROOF | Rhinotex 1150 BW | MISSING_IN_MES | 40.300 × 213.11 | — | -8 588.33 | `` |
| FLOOR | Rhinotex 1150 BW | MISSING_IN_MES | 40.300 × 213.11 | — | -8 588.33 | `` |
| ROOF | Rhinotex 2400 | EXTRA_IN_MES | — | 40.300 × 186.16 | 7 502.25 | `length*width` |
| FLOOR | ALU KICK PLATES | PRICE_DIFF | 33.600 × 496.05 | 33.600 × 406.60 | -3 005.52 | `(length*2+width)` |
| FRONT | Rhinotex 2100 Bioshield | MISSING_IN_MES | 7.118 × 295.39 | — | -2 102.67 | `` |
| SRD | Rhinotex 2100 Bioshield | MISSING_IN_MES | 7.118 × 295.39 | — | -2 102.67 | `` |
| DRD | Rhinitex 2100 Bioshield | MISSING_IN_MES | 6.832 × 295.39 | — | -2 018.19 | `` |
| SIDES | PU INJECTION | QTY_DIFF | 369.943 × 56.62 | 334.438 × 56.62 | -2 010.26 | `length*(height-0.097-0.076)*0.062*65` |
| FRONT | Crystex V2 | MISSING_IN_MES | 7.118 × 272.27 | — | -1 938.09 | `` |
| SRD | Crystex V2 | MISSING_IN_MES | 7.118 × 272.27 | — | -1 938.09 | `` |
| DRD | Crystex V2 | MISSING_IN_MES | 6.832 × 272.27 | — | -1 860.23 | `` |
| FRONT | Bioshield 4800 | EXTRA_IN_MES | — | 7.118 × 243.11 | 1 730.52 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | Bioshiled 4800 | EXTRA_IN_MES | — | 7.118 × 243.11 | 1 730.52 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | PU INJECTION | QTY_DIFF | 30.537 × 56.62 | 0.000 × 56.62 | -1 729.00 | `(width-0.062-0.062+{Waste})*(height-0.097+{Waste})*0*40` |
| DRD | Bioshield 4800 | EXTRA_IN_MES | — | 6.794 × 243.11 | 1 651.74 | `(width-0.062)*(height-0.097-0.076)` |
| FRONT | Rhinopanel V2 | EXTRA_IN_MES | — | 7.118 × 223.00 | 1 587.37 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| SRD | Rhinopanel V2 | EXTRA_IN_MES | — | 7.118 × 223.00 | 1 587.37 | `(width-{SIDES EPS}-{SIDES PU}-{SIDES EPS}-{SIDES PU}+{Waste}` |
| DRD | Rhinopanel V2 | EXTRA_IN_MES | — | 6.794 × 223.00 | 1 515.11 | `(width-0.062)*(height-0.097-0.076)` |
| ROOF | PU INJECTION | QTY_DIFF | 236.279 × 56.62 | 254.091 × 56.62 | 1 008.53 | `length*width*0.097*65` |
| INT FALSE BULKHEAD | 3MM ALU PLATE | PRICE_DIFF | 2.000 × 2 848.34 | 2.000 × 2 354.00 | -988.68 | `2` |
| DRD | PU INJECTION | QTY_DIFF | 32.730 × 56.62 | 42.838 × 56.62 | 572.27 | `(width-0.062)*(height-0.097-0.076)*0.097*65` |
| REAR FRAME + FLOOR PLATE | 3MM 3CR12 FLOOR PLATE | PRICE_DIFF | 3.125 × 965.76 | 3.125 × 1 040.16 | 232.49 | `1.25*2.5` |
| SRD DOOR FITTINGS | 28781 SMALL HORIZ CAPPING | PRICE_DIFF | 5.200 × 240.58 | 5.200 × 197.20 | -225.58 | `(width+width)` |
| SRD DOOR FITTINGS | 28779 DOOR CAPPING | PRICE_DIFF | 7.336 × 149.08 | 7.306 × 122.20 | -200.86 | `((height-0.097+{Waste})*2+0.85+0.85)` |
| FRONT | PU INJECTION | QTY_DIFF | 41.036 × 56.62 | 43.884 × 56.62 | 161.23 | `width*(height-0.097-0.076)*0.097*65` |
| FRONT | FRIDGE FRAME | PRICE_DIFF | 8.700 × 148.73 | 8.700 × 130.54 | -158.19 | `(1.7*2+2.65*2)` |
| SRD DOOR FITTINGS | 28777 DOOR CAPPING | PRICE_DIFF | 6.486 × 132.13 | 6.456 × 108.30 | -157.82 | `((height-0.097+{Waste})*2+0.85)` |
| SRD DOOR FITTINGS | 28780 SMALL VERTICAL | PRICE_DIFF | 5.700 × 181.78 | 5.700 × 203.25 | 122.38 | `(height+height)` |

## 7 MANNI DF — sheet `Manni DF` (dry-freight template), 12.2 × 2.6 × 3.0

**Burt's options as saved** (Y): DRD, 24MM WISA TRANS FLOOR, REFLEXITE TAPE.

**Burt's N options:** DRD INTO REAR PANEL, 2MM3CR12 FLOOR, 3MM3CR12 FLOOR, 3MM MILD STEEL FLOOR, 5MM MILD STEEL FLOOR, DRY FREIGHT, 19MM PLYWOOD PANELS, BAKERY BODY, RICE GRAIN FLOOR, 1ST ROW ALU KICK PLATE, 2ND ROW ALU KICK PLATE, 80 DV COMPOSITE PANELS, LOAD LOCK RAIL, TOP HAT SECTION, ESCAPE HATCH, INTERIOR LIGHTS, DRAIN HOLES, NOSE CONE, 2MM3CR12 KICK PLATES.

**The floor is chosen, not summed.** Burt's sheet has five floor sections and costs only the one whose option is **Y** (saved: 24MM WISA TRANS FLOOR). MES costs **all five** at once, with no option to choose between them. That alone is most of MANNI DF's R7.17 M (RT4_RETURN_2: each floor's 80×50×3 crossmembers at R8 891.12 a unit).

| Burt section | option gate | Burt (gated) | MES (DRD) | Δ |
|---|---|---:|---:|---:|
| FRONT |  | 4 616.11 | 10 232.84 | 5 616.73 |
| DRD | on | 4 922.08 | 4 431.60 | -490.48 |
| DRD DOOR FITTINGS | on | 6 687.85 | 31 908.73 | 25 220.88 |
| DRD INTO REAR PANEL | OFF | 0.00 | — (no MES section) | 0.00 |
| DRD INTO REAR PANEL DOOR FITTINGS | OFF | 0.00 | — (no MES section) | 0.00 |
| SIDES |  | 43 609.95 | 234 470.18 | 190 860.23 |
| ROOF |  | 18 830.00 | 23 715.14 | 4 885.14 |
| 2MM 3CR12 S/STEEL FLOOR | OFF | 0.00 | 1 266 815.66 | 1 266 815.66 |
| 3MM 3CR12 S/STEEL FLOOR | OFF | 0.00 | 1 329 181.22 | 1 329 181.22 |
| 3MM MILD STEEL FLOOR | OFF | 0.00 | 1 213 270.33 | 1 213 270.33 |
| 5MM 300 WA PLATE | OFF | 0.00 | 1 277 941.11 | 1 277 941.11 |
| 24MM WISA TRANS FLOOR | on | 64 053.28 | 1 199 624.69 | 1 135 571.41 |
| ALUMINIUM |  | 15 597.88 | 454 871.21 | 439 273.33 |
| SUB FRAME + LIGHT BOX ASSY |  | 3 936.41 | 4 046.12 | 109.71 |
| REFLEXITE TAPE | on | 486.00 | 8 262.00 | 7 776.00 |
| REAR FRAME + FLOOR PLATE | on | 2 224.20 | 2 224.20 | 0.00 |
| SPRAY PAINTING |  | 1 250.00 | 750.00 | -500.00 |
| LOAD LOCK RAILS | OFF | 0.00 | 35 518.59 | 35 518.59 |
| TOPHAT SECTON | OFF | 0.00 | 46 066.42 | 46 066.42 |
| ESCAPE HATCH | OFF | 0.00 | 19 600.00 | 19 600.00 |
| INTERIOR LIGHTS |  | 0.00 | — (no MES section) | 0.00 |
| 2MM 3CR12 KICK PLATES | OFF | 0.00 | — (no MES section) | 0.00 |
| — | — | — | 0.30 (BODY OPTIONS: MES only) | 0.30 |
| — | — | — | 5 932.08 (NOSE CONE: MES only) | 5 932.08 |

**Lines in the sections Burt costs** (`on`, or ungated), matched by name. Burt's quantity and price are read from columns D / E (B when D is empty); his total is the sheet's own F:

| section | line | Burt qty × price = total | MES qty × price = total | Δ |
|---|---|---|---|---:|
| FRONT | CHINESE EXTERNAL HIGH GLOSS | 7.800 × 213.11 = 1 662.26 | not in MES | -1 662.26 |
| FRONT | 30MM PU INJECTION | 17.846 × 56.62 = 1 010.45 | 12.480 × 60.00 = 748.80 | -261.65 |
| FRONT | 100*19mm PICTURE FRAME | 11.200 × 25.10 = 281.15 | 11.200 × 524.93 = 5 879.24 | 5 598.09 |
| FRONT | CHINESE INTERNAL HIGH IMPACT | 7.800 × 213.11 = 1 662.26 | not in MES | -1 662.26 |
| FRONT | WOVEX SKIN | not on Burt's sheet | 8.082 × 223.00 = 1 802.40 | 1 802.40 |
| FRONT | WOVEX SKIN | not on Burt's sheet | 8.082 × 223.00 = 1 802.40 | 1 802.40 |
| DRD | CHINESE EXTERNAL HIGH GLOSS | 7.800 × 213.11 = 1 662.26 | not in MES | -1 662.26 |
| DRD | 30MM PU INJECTION | 17.846 × 56.62 = 1 010.45 | 12.480 × 60.00 = 748.80 | -261.65 |
| DRD | CHINESE INTERNAL HIGH IMPACT | 7.800 × 213.11 = 1 662.26 | not in MES | -1 662.26 |
| DRD | DOOR BLOCKS | 119.119 × 587.12 = 587.12 | 1.000 × 78.00 = 78.00 | -509.12 |
| DRD | WOVEX SKIN | not on Burt's sheet | 8.082 × 223.00 = 1 802.40 | 1 802.40 |
| DRD | WOVEX SKIN | not on Burt's sheet | 8.082 × 223.00 = 1 802.40 | 1 802.40 |
| DRD DOOR FITTINGS | 34MM LOCKING POLE | 6.000 × 42.00 = 252.00 | 6.000 × 252.00 = 1 512.00 | 1 260.00 |
| DRD DOOR FITTINGS | 30258 NEW DOOR CAPPING | 5.050 × 106.14 = 536.01 | 5.050 × 87.00 = 439.35 | -96.66 |
| DRD DOOR FITTINGS | 30258 NEW DOOR CAPPING | 12.000 × 106.14 = 1 273.68 | 12.000 × 87.00 = 1 044.00 | -229.68 |
| DRD DOOR FITTINGS | 2316 INNER DOOR RUBBER | 17.050 × 24.72 = 421.48 | 17.050 × 391.81 = 6 680.39 | 6 258.91 |
| DRD DOOR FITTINGS | 2317 OUTER DOOR RUBBER | 17.050 × 60.18 = 1 026.07 | 17.050 × 953.85 = 16 263.19 | 15 237.12 |
| DRD DOOR FITTINGS | M10*45 *3 FENDER WASHER | 40.000 × 1.47 = 59.00 | 40.000 × 59.00 = 2 359.84 | 2 300.84 |
| DRD DOOR FITTINGS | M 10 NYLOCK NUT | 17.050 × 0.74 = 12.57 | 17.050 × 29.50 = 502.91 | 490.34 |
| SIDES | CHINESE EXTERNAL HIGH GLOSS | 36.750 × 213.11 = 7 831.79 | not in MES | -7 831.79 |
| SIDES | 30MM PU INJECTION | 84.084 × 56.62 = 4 760.76 | 117.600 × 60.00 = 7 056.00 | 2 295.24 |
| SIDES | 100*19 PICTURE FRAME | 55.000 × 25.10 = 1 380.64 | 110.000 × 1 703.55 = 187 390.50 | 186 009.86 |
| SIDES | CHINESE INTERNAL HIGH IMPACT | 36.750 × 213.11 = 7 831.79 | not in MES | -7 831.79 |
| SIDES | WOVEX SKIN | not on Burt's sheet | 73.500 × 272.27 = 20 011.84 | 20 011.84 |
| SIDES | WOVEX SKIN | not on Burt's sheet | 73.500 × 272.27 = 20 011.84 | 20 011.84 |
| ROOF | CHINESE EXTERNAL HIGH GLOSS | 32.462 × 213.11 = 6 918.08 | not in MES | -6 918.08 |
| ROOF | 41MM PU INJECTION | 88.201 × 56.62 = 4 993.83 | not in MES | -4 993.83 |
| ROOF | CHINESE EXTERNAL HIGH GLOSS | 32.462 × 213.11 = 6 918.08 | not in MES | -6 918.08 |
| ROOF | WOVEX SKIN | not on Burt's sheet | 32.462 × 272.27 = 8 838.56 | 8 838.56 |
| ROOF | 45MM PU INJECTION | not on Burt's sheet | 100.634 × 60.00 = 6 038.02 | 6 038.02 |
| ROOF | WOVEX SKIN | not on Burt's sheet | 32.462 × 272.27 = 8 838.56 | 8 838.56 |
| 24MM WISA TRANS FLOOR | 4 MM BEND UP SUB FRAME | 24.500 × 243.00 = 5 953.50 | 24.500 × 3 523.50 = 86 325.75 | 80 372.25 |
| 24MM WISA TRANS FLOOR | 80*50*3 CROSSMEMBERS | 0.450 × 124.68 = 15 022.92 | 120.492 × 8 891.12 = 1 071 307.08 | 1 056 284.16 |
| 24MM WISA TRANS FLOOR | 24 MM WISA TRANS PLYWOOD | 10.000 × 4 295.00 = 42 950.00 | 10.000 × 4 195.00 = 41 950.00 | -1 000.00 |
| 24MM WISA TRANS FLOOR | 3MM GUSSETS | 0.028 × 384.42 = 126.86 | 0.330 × 126.86 = 41.86 | -85.00 |
| ALUMINIUM | SMALL HORIZONTALE | 54.000 × 203.25 = 10 975.50 | 54.000 × 166.60 = 8 996.40 | -1 979.10 |
| ALUMINIUM | SMALL VERTICAL | 6.000 × 149.08 = 894.48 | not in MES | -894.48 |
| ALUMINIUM | 0661-0631 RIVETS | 1 112.000 × 0.52 = 572.68 | 1 112.000 × 360.50 = 400 876.00 | 400 303.32 |
| ALUMINIUM | SILPLUS X-WHITE | 24.400 × 116.15 = 2 834.06 | 24.400 × 1 672.56 = 40 810.46 | 37 976.40 |
| ALUMINIUM | SMALL ALU CORNERS | 4.000 × 54.90 = 219.60 | 4.000 × 45.00 = 180.00 | -39.60 |
| ALUMINIUM | M10*40 CUP SQ BOLTS | 45.394 × 1.50 = 68.09 | 45.394 × 43.09 = 1 956.07 | 1 887.98 |
| ALUMINIUM | M10 NYLOCK NUT | 45.394 × 0.74 = 33.47 | 45.394 × 21.18 = 961.60 | 928.13 |
| ALUMINIUM | 28778 BIG VERTICAL | not on Burt's sheet | 6.000 × 181.78 = 1 090.68 | 1 090.68 |
| SUB FRAME + LIGHT BOX ASSY | 8 MM SMALL FISH PLATE | 2.000 × 54.86 = 109.71 | 2.000 × 109.71 = 219.43 | 109.72 |
| REFLEXITE TAPE | TAPE | 27.000 × 18.00 = 486.00 | 27.000 × 306.00 = 8 262.00 | 7 776.00 |
| SPRAY PAINTING | PAINTING OF SUB FRAME + REAR FRAME | — × — = 1 250.00 | 1.000 × 750.00 = 750.00 | -500.00 |
| INTERIOR LIGHTS | INTERIOR LIGHTS | — × 140.00 = 140.00 | not in MES | -140.00 |

