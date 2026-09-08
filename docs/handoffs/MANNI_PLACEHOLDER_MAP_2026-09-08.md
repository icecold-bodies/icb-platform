# Manni RIGIDS CB — insulation/waste placeholder wiring (8 Sep 2026)

Michael's instruction: every hardcoded insulation-thickness and waste constant in the body's BOM formulas becomes a placeholder ({SECTION EPS}/{SECTION PU} pairs + the built-in {Waste} global, value 0.05). Applied on dev (trailer 106) via the admin API with an exact-match guard; **equivalence proven: 104/104 items identical (qty + cost)** with seeds FRONT PU .062 / DRD PU .038 / SIDES PU .038 / ROOF PU .038 / FLOOR PU .076, EPS + SRD unset, Waste 0.05.

## Semantic conventions used (RATIFY: the values are proven equivalent; the PAIR LABELS below are my geometric reading — correct any row and the fix is a one-line formula edit)

- P1 `(2.6-0.038-0.076)` → `(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})`
- P2 `(height-0.038)` → `(height-{ROOF EPS}-{ROOF PU})`
- P3 `(height-0.038-0-0.038+0.05)` → `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})`
- P4 `(2.6-0-0.038-0.05)` → `(2.6-{SIDES EPS}-{SIDES PU}-{Waste})`
- P5 `(2.6-0-0-0.038+0.05)` → `(2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})`
- Insulation factors `{X PU}` → `({X EPS}+{X PU})` (copy-zero keeps exactly one side non-zero)
- Leading `0*` quantity gates and `*1.1` factors left as-is (not insulation/waste). `2.6` dimension literals left as-is (out of instructed scope).

| bom_id | material | before | after |
|---|---|---|---|
| 11395 | RHINOTEX SKINS 1375 BIOSHIELD | `(height-0.038-0-0.038+0.05)*(2.6-0-0.038-0.05)` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SIDES EPS}-{SIDES PU}-{Waste})` |
| 11396 | R250820/1A | `height*(2.6-0.038-0.076)*{FRONT PU}*50*1.1` | `height*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*({FRONT EPS}+{FRONT PU})*50*1.1` |
| 11399 | RHINO PANEL Gloss Crystex V2 | `(height-0.038-0-0.038+0.05)*(2.6-0-0.038-0.05)` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SIDES EPS}-{SIDES PU}-{Waste})` |
| 11400 | RHINOTEX SKINS 1375 BIOSHIELD | `(height-0.038-0-0.038+0.05)*(2.6-0-0-0.038+0.05)` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})` |
| 11401 | R250820/1A | `(height-0.038-0-0.038+0.05)*(2.6-0-0-0.038+0.05)*{SRD PU}*40*1.1` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})*({SRD EPS}+{SRD PU})*40*1.1` |
| 11402 | RHINO PANEL Gloss Crystex V2 | `(height-0.038-0-0.038+0.05)*(2.6-0-0-0.038+0.05)` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})` |
| 11405 | SB 51111 DOOR SET | `(height+0.05)*1` | `(height+{Waste})*1` |
| 11406 | 28779 DOOR CAPPING | `0*((2.6-0-0-0.038+0.05)*2+0.85+0.85)` | `0*((2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})*2+0.85+0.85)` |
| 11407 | 28777 DOOR CAPPING | `0*((2.6-0-0-0.038+0.05)*2+0.85)` | `0*((2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})*2+0.85)` |
| 11408 | 2316 DOOR RUBBER | `2.6*((2.6-0-0-0.038+0.05)*2+0.85+0.85)` | `2.6*((2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})*2+0.85+0.85)` |
| 11409 | 2317 DOOR RUBBER | `0*((2.6-0-0-0.038+0.05)*2+0.85+0.85)` | `0*((2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})*2+0.85+0.85)` |
| 11420 | D-RUBBER | `(height-0.038-0-0.038+0.05)*(2.6-0-0.038-0.05)*1` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SIDES EPS}-{SIDES PU}-{Waste})*1` |
| 11421 | RHINOTEX SKINS 1375 BIOSHIELD | `(height-0.038)*(2.6-0.038-0.076)` | `(height-{ROOF EPS}-{ROOF PU})*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})` |
| 11422 | R250820/1A | `(height-0.038)*(2.6-0.038-0.076)*{DRD PU}*50*1.1` | `(height-{ROOF EPS}-{ROOF PU})*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*({DRD EPS}+{DRD PU})*50*1.1` |
| 11423 | RHINO PANEL Gloss Crystex V2 | `(height-0.038)*(2.6-0.038-0.076)` | `(height-{ROOF EPS}-{ROOF PU})*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})` |
| 11427 | 28779 DOOR CAPPING | `0*((2.6-0.038-0.076)*3+(height-0.038)*2)` | `0*((2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*3+(height-{ROOF EPS}-{ROOF PU})*2)` |
| 11428 | 28777 DOOR CAPPING | `0*(2.6-0.038-0.076)` | `0*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})` |
| 11429 | 2316 DOOR RUBBER | `2.6*((2.6-0.038-0.076)*3+(height-0.038)*2)` | `2.6*((2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*3+(height-{ROOF EPS}-{ROOF PU})*2)` |
| 11430 | 2317 DOOR RUBBER | `0*((2.6-0.038-0.076)*3+(height-0.038)*2)` | `0*((2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*3+(height-{ROOF EPS}-{ROOF PU})*2)` |
| 11437 | D-RUBBER | `(height-0.038-0-0.038+0.05)*(2.6-0-0.038-0.05)*2` | `(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})*(2.6-{SIDES EPS}-{SIDES PU}-{Waste})*2` |
| 11438 | RHINOTEX SKINS 1375 BIOSHIELD | `width*(2.6-0.038-0.076)` | `width*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})` |
| 11439 | R250820/1A | `width*(2.6-0.038-0.076)*{SIDES PU}*50*1.1` | `width*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*({SIDES EPS}+{SIDES PU})*50*1.1` |
| 11441 | RHINO PANEL Gloss Crystex V2 | `width*(2.6-0.038-0.076)` | `width*(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})` |
| 11442 | 3MM MILD STEEL PLATE | `(2.6-0.038-0.076)*2*0.1` | `(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})*2*0.1` |
| 11444 | R250820/1A | `width*height*{ROOF PU}*50*1.1` | `width*height*({ROOF EPS}+{ROOF PU})*50*1.1` |
| 11448 | R250820/1A | `width*height*{FLOOR PU}*75` | `width*height*({FLOOR EPS}+{FLOOR PU})*75` |

## Prod sequencing (NOT yet applied)

1. Prod runs v1.52.x and does NOT have the v1.53 draft-flag code (#176/#177/#178 + the copy-zero PR) — applying these formulas on prod before that release would compute every insulation row at 0 with no way to set values. **Code release first, then this data change.**
2. The prod apply script must locate rows by trailer NAME + current formula text (prod row ids differ) and verify the Waste global exists there.
