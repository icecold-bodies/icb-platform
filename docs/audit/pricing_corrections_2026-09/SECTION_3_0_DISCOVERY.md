# §3.0 Discovery + impact — v1.58 audit pricing corrections

**Lane:** `fix/v1.58-audit-pricing-corrections` (from `b10a7cf`) · **Dispatch:** CA_DISPATCH_2 v3 (28 Sep)
**Written:** 27 Sep (first pass, prod impact query run by Michael 15:08 SAST), updated 28 Sep against the committed
prod snapshot (`mes_snapshot/all.json`, exported 28 Sep 07:29 SAST) and the 28 Sep prod reference reports.
**Nothing has been applied anywhere.** Quote numbers only — no customer names.

---

## 1. Synthesis

1. **Saved quotes: the damage is small — 8 quotes** (§2, 27 Sep run). F1 4 quotes (−R150 to +R180 cost), F3 2 quotes
   (+R866 cost / +R1 653 selling each, under-quoted), F4 3 quotes (+R486 to +R703, one accepted), F2 none. **No saved
   quote carries the R24.4k single-door PU.** The list is refreshed (customer-free query, `impact/impact_refresh.sql`)
   just before the prod apply, so the BA's list is current when Burt is told.
2. **F1 onset: 7 Sep 2026 15:38 UTC.** During the ICECREAM 4.8 rear-door work the shared SRD `PU` material was set to
   R4 100 at the material level. Every body whose SRD PU formula counts 2 *sheets* (`1.22*2.44*2`) jumped to R24.4k.
   Before that the line had carried `*0` (R0) since the 29 Apr import; the `*0` was removed by hand between 8 May and
   31 Aug.
3. **⚠ F1 is still live on CHILLER MEDIUM and CHILLER LARGE** (lines 3179, 3319: `2 sheets × R4 100` in the 28 Sep
   snapshot). The 28 Sep reference run looked clean on the chillers only because the audit's `srd` scenario keeps the
   sheet's own insulation — EPS on every chiller — so it never priced that line. Michael (28 Sep): fix them at the rate
   their own front/DRD PU lines use (R3 090) and **add a chiller single-door-PU audit scenario** (`srd_pu`, 14 cells),
   so the audit proves it. CHILLER 2.3 (line 3699) was hand-fixed on 26 Sep to within 0.11 % of Burt; it moves to
   Burt's exact shape.
4. **⚠ Burt's September workbook on this PC was saved again on 27 Sep 07:43** (sha `af64176d…`; the committed
   golden was built on 25 Sep from `d87a5731…`, no copy of which survives). A full chiller golden rebuild from it would
   move ~375 existing cells (CHILLER MEDIUM's saved SIDES flag is now PU, CHILLER 2.3's FRONT PU unit price reads 0,
   picture-frame prices moved). Michael (28 Sep): keep the 84 committed chiller scenarios untouched and **add only the
   14 new ones**, with their panels pinned to the committed `srd` states; outside SRD they equal the committed `srd`
   scenarios within 0.55 % (123 cells). The source is recorded in `golden/chillers/_manifest.json` → `additions`.
   **Please keep a pristine copy of Burt's workbooks** — they are the audit's truth.
5. **The systemic cause — shared PU materials edited as if they were one body's price.** One global `PU` material per
   section (FRONT 207, DRD 209, SIDES 211, ROOF 213, FLOOR 236, SRD 292 on prod). 31 edits since 1 Jun; each silently
   re-prices every line in that section without a price of its own. Several F5 items are this mechanism (FREEZER 2.3
   roof/floor, ICECREAM 4.8 DRD). Ruling 28 Sep: every line this lane fixes carries its **own** price. A UI warning
   before a shared material's price is edited is a code change → separate lane (recommended).
6. **F2 (ALU floor):** no saved quote carried it and the calculator already starts these multi-select masters OFF;
   the default flip aligns the audit probe and the template with Michael's ruling. ICECREAM 4.8's `12MM PF PLYWOOD` is
   not missing — line 5653 exists, gated on a draft choice beside `9MM BIRCH` (11203) and `12MM FINN` (11207), which
   the audit probe cannot tick. Ruling 28 Sep: a narrowed accepted entry (tool limit), no data change.
7. **F3:** 14 lines on ICECREAM 4.9 UP carry the literal 6.7 / 6.75 (29 Apr import). The manifest substitutes
   `length` / `(length+{Waste})` and the tool refuses any substitution that does not equal the old formula at exactly
   6.7 m.
8. **F4:** CHILLER MEDIUM DRD `2317 DOOR RUBBER` ends in `* 0`; the fix is exactly the sibling 2316 line's formula (as
   on CHILLER 2.3 / LARGE). The `*0` has been toggled by hand twice (July quotes had it, 12 Aug–16 Sep did not).
9. **Precondition met:** CHILLER 2.3's DRD fittings are back to hinges 4 / door set 2 (the 27 Sep STOP item) and its
   SRD DOOR FITTINGS PASS in the 28 Sep reference run.

## 2. Impact on saved prod quotes (27 Sep run; refreshed before the apply)

"Corrected" = the corrected BOM applied to the saved quote. Selling Δ = cost Δ × (1 + margin) ÷ ratio, per quote.
`+` = the quote was **under** the corrected price. F1 is compared with Burt's September sheet.

| F | quote | body | length | SRD | saved | status | affected line(s) as saved | cost Δ if corrected | selling Δ |
|---|---|---|---:|---|---|---|---:|---:|---:|
| F1 | N9945/07/2026 | ICECREAM 4.8 (MEDIUM) | 5.3 | yes | 2026-07-15 | pending | R3,075.87 | -149.84 | -286.07 |
| F1 | N9947/07/2026 | ICECREAM 4.8 (MEDIUM) | 5.5 | yes | 2026-07-15 | pending | R3,075.87 | -149.84 | -286.07 |
| F1 | N9981/08/2026 | ICECREAM 4.8 (MEDIUM) | 4.2 | yes | 2026-08-31 | pending | R3,075.87 | -149.84 | -286.07 |
| F1 | N9983/08/2026 | ICECREAM 4.9 UP (LARGE) | 6.8 | yes | 2026-08-31 | pending | R2,746.18 | +179.85 | +343.34 |
| F3 | N9982/08/2026 | ICECREAM 4.9 UP (LARGE) | 6.8 | no | 2026-08-31 | pending | R60,044.98 | +865.86 | +1,653.01 |
| F3 | N9983/08/2026 | ICECREAM 4.9 UP (LARGE) | 6.8 | yes | 2026-08-31 | pending | R60,044.98 | +865.86 | +1,653.01 |
| F4 | A9929/07/2026 | CHILLER MEDIUM | 2.3 | no | 2026-07-05 | accepted | R0.00 | +485.89 | +971.79 |
| F4 | N9937/07/2026 | CHILLER MEDIUM | 5.2 | no | 2026-07-14 | pending | R0.00 | +702.54 | +1,341.22 |
| F4 | N9952/07/2026 | CHILLER MEDIUM | 3.2 | no | 2026-07-24 | pending | R0.00 | +582.18 | +1,111.44 |

Not affected: N9946 (4.9 UP at exactly 6.7 m), A9992 (SRD PU already Burt's shape; deleted), the six CHILLER MEDIUM
quotes from 12 Aug onward (door rubber priced), every icecream quote for F2 (ALU floor R0). No chiller single-door PU
quote has been saved. Saved quotes are frozen; re-quoting is the BA's call with Burt.

## 3. Onset — timeline (UTC)

| when | what | source |
|---|---|---|
| 29 Apr | bodies imported; 4.9 UP formulas carry the literal 6.7; every SRD PU line `…*0*2` (R0) | `trailer_types`, snapshots 6–8 May |
| 8 May → 31 Aug | SRD PU `*0` removed by hand (unlogged) | last `*0` snapshot 8 May; N9983 (31 Aug) saved `1.22*2.44*2` |
| ≤ 24 Jul | CHILLER MEDIUM DRD 2317 door rubber `×0` (3 July quotes) | saved quotes |
| 12 Aug → 16 Sep | door rubber priced | saved quotes |
| 7 Sep 15:19 | DRD `PU` material: R352.12 → R4 100 | `price_history` 296 |
| **7 Sep 15:38** | **SRD `PU` material: R516.64 → R4 100 (F1 onset)** | `price_history` 297 |
| 18–25 Sep | shared PU materials edited to today's values (FRONT 334.50, DRD 490.87, SIDES 345.65, ROOF/FLOOR 557.50) | `price_history` 299–319 |
| 22 Sep 13:09 | EXPLOSIVE 4.9 AND UP PU lines: R172.02 (Burt) → R234.15 | `bom_override_history` 221–224 |
| 26–27 Sep | CHILLER 2.3 SRD PU + SRD fittings fixed by hand; SRD hinge / silicone / capping materials repriced | audits 26–28 Sep |
| 27 Sep 07:43 | Burt's September workbook on this PC saved again (see §1.4) | file mtime + sha |

## 4. The corrections (manifest.yaml — 36 entries on 27 lines)

bom ids are shared by dev and prod; **material ids are not**. Guards = prod on 28 Sep 07:29.

| F | body (id) | line(s) | now | new |
|---|---|---|---|---|
| F1 | FREEZER 2.3 (19) · MEDIUM (20) · LARGE (21) · ICECREAM 4.9 UP (18) · EXPLOSIVE UP TO 2.7 (34) · 2.7–4.8 (37) · 4.9 AND UP (24) | SRD PU 3576 · 2415 · 2560 · 5306 · 5184 · 6345 · 3948 | `1.22*2.44*2` (2 sheets) × shared R4 100 | `(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2`, own price R4 100 |
| F1c | CHILLER MEDIUM (26) · LARGE (27) | 3179 · 3319 | 2 sheets × shared R4 100 | same shape, own price R3 090 (the body's front/DRD rate) |
| F1c | CHILLER 2.3 (25) | 3699 | `(1.22*2.44*{SRD PU})` @ own R3 090 | `(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)` (Burt's 2.3 row has no ×2) |
| F2 | ICECREAM 3,2 (16) · 4.8 (17) | masters 5835 · 5713 | ALU EXTRUTION FLOOR default ON | OFF |
| F3 | ICECREAM 4.9 UP (18) | 5364 · 5375 · 5377–5383 · 5384 · 5386 · 5387 · 5389 · 5422 | literal 6.7 / 6.75 | `length` / `(length+{Waste})` (equal at 6.7 m, tool-checked) |
| F4 | CHILLER MEDIUM (26) | DRD 2317 DOOR RUBBER 3216 | `(…) * 0` | the 2316 line's formula |

Burt's rows, read from the live blocks of his September sheets: freezers / icecream / explosive
`D*E*C13*[1]PU!$C$17/2.98 × F × I × 2` (32D R4 100); CHILLER MEDIUM and LARGE `D*E*C13*3090/2.98 × F × I × 2`;
CHILLER 2.3 `… × F × I` (no ×2). (The LARGE sheet's left-hand block reads 1600 — it is the dead block the sheet map
skips.)

Not in this lane: ICECREAM 4.9 UP ALU floor master 5435 (Michael said yes to flipping it too on 27 Sep; the dispatch
rules 3,2 + 4.8 only, and 5435 gates nothing — its ALU line is wired to the RICE GRAIN master, F5 #19). MEAT HANGER
LARGE / SMALL-MEDIUM SRD PU (5851, 6159) are still R4 100 on prod — not in any pack or the snapshot, so the mirror
cannot prove them; recommend they join the chiller-rate follow-on lane with a pack.

## 5. F5 triage — refreshed on 28 Sep prod (for BA ratification; nothing applies before it)

Evidence: the 28 Sep prod reference reports; Burt's sheet as truth. `+` = MES above Burt.

| # | item | 28 Sep evidence | bucket | proposed change |
|---|---|---|---|---|
| 1 | Icecream `3MM ALU BUFFER PLATE` in the rear door | ICECREAM 3,2 SRD +R236, 4.9 UP DRD +R260; 4.8 DRD nets R0 against Burt's lump-sum tapping row | 4.8 **ACCEPT** (`burt_description_not_updated`); 3,2 / 4.9 UP **BURT** | none |
| 2 | Explosive `6MM PF PLYWOOD` vs Burt `4MM` | EXPLOSIVE 2.7–4.8 SIDES +R110–194, ROOF +R59–103; price R95.64/m² (pre-September) vs Burt R86.58 | **FIX** price · **ACCEPT** name | own price R86.58/m² |
| 3 | EXPLOSIVE 4.9 AND UP PU at R234.15 | FRONT +R370–487, DRD +R220–337, SIDES +R1.5k–5.9k, ROOF +R869–3.3k; Burt R172.02 = R4 100 × 42 mm, prod held that until a hand edit on 22 Sep | **BURT** (+ who changed it and why) | none |
| 4 | FREEZER 2.3 ROOF / FLOOR PU | +R1.1k–1.4k per panel: lines 3628 / 3636 have no own price and inherit the shared R557.50 | **FIX** | Burt's shape + own price R4 100 |
| 5 | FREEZER LARGE SIDES skins | +R257–423: formulas take the panel height from `width` | **FIX** | `width` → `height` |
| 6–7 | SRD `CSLB HINGES` / `SILPLUS` | **resolved on prod 27 Sep** (materials repriced) — no cell remains | — | prune the entry's names once the mirror proves it |
| 8 | Other SRD fittings | FREEZER 2.3 `28777 DOOR CAPPING` +R132 (Burt hard-codes R0 → #10); EXPLOSIVE UP TO 2.7 `28779 DOOR CAPPING` −R172 (price) | #10 **BURT**; 28779 **FIX** | 28779 Burt's price |
| 9 | EXPLOSIVE UP TO 2.7 SRD `LONG RIVETS` | no longer a cell on 28 Sep | — | — |
| 10 | SRD cells Burt hard-codes R0 | FREEZER 2.3 `28777 DOOR CAPPING`; SRD plywood / glue (held) | **BURT** (with the held item) | none |
| 11 | Tapping-block counts | CHILLER MEDIUM SRD +R945, CHILLER 2.3 SRD −R84, ICECREAM 3,2 DRD +R234 | **BURT** | none |
| 12 | `1MM GALV PLATE` missing | EXPLOSIVE UP TO 2.7 −R157, 4.9 AND UP −R240 | **FIX** (insert Burt's line) | insert ×2 — ⚠ an INSERT, not a field edit: the tool would need an insert action |
| 13 | EXPLOSIVE 2.7 TO 4.8 `MOUNTING CLEATS` | −R240 MISSING_IN_MES on 28 Sep (27 Sep read it as a split line) | re-check | — |
| 14 | FREEZER MEDIUM `SMALL MOUNTING BRACKET` | −R215 (price) | **FIX** | Burt's R68.80 |
| 15 | EXPLOSIVE UP TO 2.7 SRD `0.9 MM ALU PLATE` | −R325, today hidden inside the F1 SRD cell; surfaces once F1 lands | **FIX** | Burt's R312.40 |
| 16 | FREEZER 2.3 `3MM 3CR12 FLOOR PLATE` | +R63 (REAR FRAME — held) | **BURT** | none |
| 17 | ICECREAM 4.8 DRD PU (5612) | +R1.8k–2.4k per double door: formula changed by hand to `(door area)*2`, no own price → shared R490.87 | **FIX** | Burt's shape + own price R4 100 |
| 18 | ICECREAM 4.8 DRD `CSLB HINGES` | +R293: ×6 vs Burt ×4 | **FIX** | 6 → 4 |
| 19 | ICECREAM 4.9 UP floor-option wiring | ALU line gated on the RICE GRAIN master; RICE GRAIN gated on an option the body lacks | report only | follow-on |

## 6. Decisions still open for the BA

1. **Ratify the F5 table** (FIX #2, 4, 5, 8-28779, 12, 14, 15, 17, 18 would join the manifest as a second, guarded
   batch; #12 needs an insert action in the tool).
2. **Shared-material warning** in the UI before a shared PU material's price is edited → a separate code lane.
3. **MEAT HANGER SRD PU** (R4 100 live, no pack) → the chiller-rate follow-on lane?
4. **Edit freeze** on the 12 audited bodies and the six shared PU materials on prod until the apply: every guard is the
   28 Sep 07:29 value, and one moved line aborts the whole apply (safe, but a round trip).
