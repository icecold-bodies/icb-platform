# Rule coverage — Part 14 (81 rules) → new costing UI

**Purpose:** prove no business rule is lost by accident (spec Part 36.2 "silent rule loss"). Every RULE-* in spec Part 14 is mapped to exactly one primary class; none is unmapped.
**Spec:** `docs/handoffs/MES_COSTING_CURRENT_STATE_AND_NEW_UI_REQUIREMENTS.md` (§14; ratified decisions §34.1 D1–D6). Design elements refer to `IA.md` regions (R1–R6) and the mockup (`index.html`).

## Classes

| Class | Meaning |
|---|---|
| **DESIGN** | The rule is carried by a visible design element (named). Where the spec sanctions a behaviour change, the row says *changed with sanction* and cites it. Where a rule's *mechanism* disappears because the design makes it structurally unnecessary, the row says *subsumed by* the element that now guarantees the same outcome. |
| **ENGINE** | Engine-side, invisible to the user, preserved exactly as today; the new UI neither displays nor alters it (may reference it in a tooltip). |
| **FLAG** | Needs a BA decision or a conscious build-time choice (inherited defect, or a semantic the design proposes to change without spec sanction). Default stated. |

## Summary

| Family | Rules | DESIGN | ENGINE | FLAG |
|---|---|---|---|---|
| CALC | 16 | 8 | 4 | 4 |
| INS | 8 | 6 | 1 | 1 |
| DOOR | 8 | 6 | 2 | 0 |
| SEC | 12 | 7 | 4 | 1 |
| PRICE | 6 | 4 | 2 | 0 |
| MONEY | 5 | 3 | 2 | 0 |
| SAVE | 6 | 3 | 3 | 0 |
| EDIT | 8 | 5 | 2 | 1 |
| REF | 6 | 5 | 1 | 0 |
| SPEC | 3 | 1 | 0 | 2 |
| PERM | 3 | 1 | 0 | 2 |
| **Total** | **81** | **49** | **21** | **11** |

Zero unmapped. Every FLAG has a stated default so the build is never blocked on it. (SAVE-003 is DESIGN with one embedded sub-flag for R-04 — listed in the register for completeness, not counted twice.)

---

## 14.1 Calculation engine — RULE-CALC

| Rule | Class | Mapping |
|---|---|---|
| CALC-001 Quantity pipeline | **DESIGN** | Engine unchanged. Qty cell shows the **final** quantity (post multiplier + waste — D2); hover tooltip shows the formula, `× N` and the result (mockup: every qty cell title). |
| CALC-002 Empty formula = 1 | **ENGINE** | Unchanged; tooltip would read "formula: (empty) → 1". Not surfaced further. |
| CALC-003 Negative clamp (pure-number hole, R-19) | **FLAG** | Carry as-is or close the hole at build. *Default: close the hole server-side (clamp pure numbers too) — behaviour change only for literally negative constant formulas, which cannot be intentional.* |
| CALC-004 Token resolution + `formula_error` | **DESIGN** | Row state *formula-error*: red qty "— err —", tag "formula error · unknown {TOKEN}", red left stripe, counted in the R1 attention pill; save requires acknowledgement (D3). The line no longer *silently* costs the zero-substituted result. |
| CALC-005 Body vars beat globals | **ENGINE** | Unchanged. |
| CALC-006 Body variables selection-independent | **ENGINE** | Unchanged; the design makes its precondition structural — the unselected insulation side is 0 by construction (see INS-002). |
| CALC-007 Geometry variables (R-09 `num_doors` 1 vs 2) | **FLAG** | Engine unchanged. *Default: the new page sends `num_doors` explicitly = 2 for DRD, 1 for SRD (derived from the door choice) and the build documents it — removes the caller-dependence.* |
| CALC-008 Excluded rows still compute | **DESIGN** | Excluded / gated rows stay visible, dimmed, with their real quantity and total `—` (row grammar, IA §3). |
| CALC-009 Banker's rounding | **ENGINE** | Unchanged; Excel audit keeps "rounding drift". |
| CALC-010 Category totals unrounded (R-01) | **FLAG** | *Default: keep engine as-is; the card subtotal displays the server's category total (never a client sum of rounded lines) so the two never disagree on screen.* BA may prefer summing rounded lines — a numbers change. |
| CALC-011 cost/m² | **DESIGN** | R1 Materials stage sub-line "R x / m² floor" (pre-chassis ÷ floor area) — mockup. |
| CALC-012 Chassis inside grand_total | **DESIGN** | R1 Materials sub-line "incl. chassis R…"; drift basis includes chassis (REF-004). |
| CALC-013 Chassis quantities | **DESIGN** | CHASSIS card: axles/lift/tyre-style/suspension/brake/tyre/rim; derived tyre & kit counts printed under the card ("Derived: 16 tyres/rims · 3 kits · 1 lifting axle"); lift only at 3 axles. |
| CALC-014 Recipe pricing (4 engines, regions, op-chain) | **DESIGN** | Price cell `ƒ` glyph → read-only breakdown drawer with "edit recipe →" deep link; engine untouched (client re-implementation R-18 retired). |
| CALC-015 Live vs save asymmetry | **DESIGN** — *changed with sanction (Part 24.9)* | One server path computes materials → margin → ratio → discount for both live and save; R1 always shows the server's numbers. `verifyEditBalance` survives only as the edit-load balance gate (EDIT-004). |
| CALC-016 30 s cache divergence (R-07) | **FLAG** | *Default: `/calculate` and `/approve` read the formula library through the same loader (or approve re-uses the calculate result bound by the hash — see EDIT-008) so preview ≡ saved by construction.* |

## 14.2 Insulation — RULE-INS

| Rule | Class | Mapping |
|---|---|---|
| INS-001 Pair identity is structural (name-substring, R-14) | **ENGINE** | Unchanged (carried consciously). The card's Insulation control is rendered *from* the pair rows; no new identity mechanism. |
| INS-002 Checked radio owns the thickness (+ template write) | **DESIGN** — *changed with sanction (OQ-02)* | One control per insulated card `[EPS\|PU] [mm]`: state = (side, thickness); the other side is 0 by construction; **no template write** — per-costing values, explicit "Save insulation to template…" drawer gated `{admin, full}`. |
| INS-003 Copy-on-switch | **DESIGN** | Flipping the side keeps the thickness (mockup: mm value persists across EPS⇄PU); a rear door with nothing set defaults 60 mm. |
| INS-004 Switch-ALL modal | **DESIGN** | Inline assist chip in the card after a flip: "Apply PU to all N insulated categories? [Apply] [✕]" (non-modal). |
| INS-005 Both-zero warning | **DESIGN** — *subsumed by* the Insulation control | Thickness is required > 0 while the category is included; both-zero cannot be entered, so cannot be saved silently (Part 26). |
| INS-006 Manual thickness edit hits the template | **DESIGN** — *changed with sanction (OQ-02)* | The mm field edits **this costing**; "≠ template" marker appears; template write only via the explicit drawer. |
| INS-007 Edit pinning (`body_variable_overrides`) | **DESIGN** — *subsumed by* per-costing insulation values | The saved costing carries every category's (side, mm); reopening reproduces them regardless of template drift — the values *are* the pins. `body_variable_overrides` remains the wire/storage shape (DATA_MODEL_DELTA §3). |
| INS-008 Flip releases stuck exclusions | **FLAG** | With per-line excludes now on the record, does a side flip clear the user-excludes on that pair's rows? *Default: yes, scoped to the flipped pair's rows only (today's semantic), never in edit-replay.* |

## 14.3 Rear doors — RULE-DOOR

| Rule | Class | Mapping |
|---|---|---|
| DOOR-001 Either DRD or SRD | **DESIGN** | R3 Body choices → "Rear door [DRD\|SRD]" segmented control (shown only when both door sections exist). |
| DOOR-002 Only `{SRD *}` tokens exist | **ENGINE** | Unchanged (formula authoring concern). |
| DOOR-003 Carry on click | **DESIGN** | Switching the door carries (side, mm) to the chosen door card; the other door's pair goes to 0 in the payload — per-costing, no template write. |
| DOOR-004 Heal on render | **DESIGN** — *subsumed by* structural state | No healing needed: the state can't be inconsistent. |
| DOOR-005 Zero the inactive door on load | **DESIGN** — *subsumed by* structural state | Not-quoted door pair is 0 by construction in every payload; no template write on load. |
| DOOR-006 Door off = zero both cells | **DESIGN** — *subsumed by* the *not-quoted-sibling* card state | The unchosen door card is visible, collapsed, "not quoted (DRD chosen)", contributes nothing, warns nothing. |
| DOOR-007 NO REAR DOORS + side doors | **DESIGN** (mocked — EXPLOSIVE 2.7 TO 4.8) | Bodies that carry a NO REAR DOORS control (EXPLOSIVE types — Michael, 17 Aug) get a third option in the Rear-door control (`DRD \| SRD \| None — side doors only`); adding a SIDE DOOR extra while a rear door is quoted shows the inline prompt "remove the rear doors? [Remove] [Keep both]"; "None" with no side-door extra shows the amber "No doors quoted" note. Same outcomes as today, inline instead of modal. |
| DOOR-008 Doors resolve for display from saved data (R-16) | **ENGINE** | New records store the door choice explicitly (DATA_MODEL_DELTA §3) so the display fallback is only ever needed for legacy records. |

## 14.4 Sections & categories — RULE-SEC

| Rule | Class | Mapping |
|---|---|---|
| SEC-001 OPTIONAL prefix | **ENGINE** | Derivation unchanged; the UI reads the derived flag: optional cards are red-named and default off. |
| SEC-002 Optional gate (R-13 NULL-section row) | **FLAG** | *Default: build heals R-13 by treating a NULL-section row inside an optional-named section as belonging to that section (data fix script), so every optional row can be enabled.* |
| SEC-003 Optional state is per-browser | **DESIGN** — *changed with sanction (OQ-15 / §33.2)* | Category include state and per-line excludes live on the saved costing; a costing re-opens identically on any browser. localStorage keeps only unsaved-draft convenience. |
| SEC-004 `excluded_categories` is a hard drop | **DESIGN** | Server semantics unchanged (rows never enter the response); the UI renders the dropped category as a visible card in state *not-quoted-sibling* / *excluded-by-rule* with a reason — never as absence (guard-rail 2). |
| SEC-005 Radio categories | **DESIGN** | Radio siblings collapse to one visible choice in R3 (Rear door); each sibling's card stays in place. |
| SEC-006 v2 gating chain | **ENGINE** | Unchanged; its outcomes render as reason chips on rows and *excluded-by-rule* on cards ("excluded — needs {master}"). |
| SEC-007 `bom_conditions` shapes | **ENGINE** | Unchanged; the server's human reason ("FRONT PU = Y") is the row's reason chip. |
| SEC-008 Legacy DRD/SRD prefix filter | **DESIGN** | Same *not-quoted-sibling* card state via the mapping rule (IA §2.1). |
| SEC-009 Legacy per-item link gate | **DESIGN** | Row state *gated* with a **derived** reason "linked to {option}" — computed by the server from `body_option_linked(_id)`, not authored (guard-rail 1; 2,087 rows). |
| SEC-010 Section multiplier | **DESIGN** | `× N` badge on the card header; tooltip "R x per side". Admin single-side display toggle **dropped** (OQ-10 ratified). |
| SEC-011 flag_overrides alias union | **ENGINE** | Unchanged. |
| SEC-012 Hidden-row eye | **DESIGN** — *replaced* | Excluded rows are always visible, dimmed (no eye toggle); exports still strip excluded items (unchanged). |

## 14.5 Pricing — RULE-PRICE

| Rule | Class | Mapping |
|---|---|---|
| PRICE-001 Precedence | **ENGINE** | Unchanged; the winning source is what the provenance glyph shows (`ƒ` recipe · pin permanent · `*` quote override · dot catalogue). |
| PRICE-002 Quote override needs a reason | **DESIGN** | Price drawer, scope "This costing only": reason ≥ 5 chars required, blue + `*`, tooltip = reason; entering the original price clears the override without a reason. |
| PRICE-003 Permanent price is per-ROW | **DESIGN** | Same drawer, scope "Permanently for this section" — gated `costings.price_master_edit`, journalled, clears the quote override; recipe rows read-only here. |
| PRICE-004 Price-age badges | **DESIGN** | Corner dot: green ≤ 7 d, amber ≥ 90 d; suppressed under a quote override; also shown in the stock picker before adding. |
| PRICE-005 Zero price is silent (R-20) | **DESIGN** — *changed with sanction (Part 24.8)* | Row state *unpriced*: red "no price", stripe, attention pill, acknowledgement at save (D3); shown in the picker before adding. |
| PRICE-006 Bulk updates capped & journalled | **ENGINE** | Admin surface unchanged; a permanent single save from the drawer journals its own 1-row batch as today. |

## 14.6 Money — RULE-MONEY

| Rule | Class | Mapping |
|---|---|---|
| MONEY-001 Margin | **DESIGN** | R1 "+ Margin n%" stage; header field seeded from body markup; repair defaults 0 (OQ-08). |
| MONEY-002 Ratio is a divisor | **DESIGN** | Header ratio select 30–70 % step 2.5, default 55 % on new costings only; R1 "÷ Ratio = Total". |
| MONEY-003 Discount | **DESIGN** | R5 discount `% ⇄ R` — one clears the other, clamped; R1 "− Discount = Net". |
| MONEY-004 List headline totals | **ENGINE** | Downstream lists unchanged; the record still carries `net_total`. |
| MONEY-005 Multi-ratio exports | **ENGINE** | Export dialog (⋯ → Export…) unchanged in semantics. |

## 14.7 Saving & versioning — RULE-SAVE

| Rule | Class | Mapping |
|---|---|---|
| SAVE-001 Duplicate detection | **DESIGN** | Truthful Save: dup check runs as soon as customer + costing type (+ body) are set; button names the outcome. Client sends the costing type → **fixes R-03**. |
| SAVE-002 Version actions (`replace` bulk-delete, R-05) | **DESIGN** | Mode selector (New · Revision N+1 · Overwrite pending). **Replace** moves to ⋯ with typed "REPLACE" confirmation naming the count and any validated references — **this is the R-05 fix.** Overwrite offered only for a pending record. |
| SAVE-003 Quote numbers | **DESIGN** | "reuse quote no." tick — defaults ON in the edit flow, OFF in the duplicate flow (as today; mockup); numbers immutable. R-04 (assignment failure swallowed) → **FLAG** inside this row: *default: surface a visible warning chip "no quote number" on the saved record instead of silence.* |
| SAVE-004 Contact snapshot | **ENGINE** | Unchanged; header contact select is bound to the chosen customer (mockup). |
| SAVE-005 `input_state` + `ui_snapshot` | **ENGINE** | Shape extended, not replaced (DATA_MODEL_DELTA §3: qty overrides, category state, per-line excludes, free-hand lines, insulation values, acknowledgement, door choice). |
| SAVE-006 Status flow | **ENGINE** | Downstream unchanged; repair records read "Repair" from `costing_type`. |

## 14.8 Edit & copy — RULE-EDIT

| Rule | Class | Mapping |
|---|---|---|
| EDIT-001 Copy (`?from=`) | **DESIGN** (specified, not mocked) | R1 chip "Copied from Q-…"; overrides/optional/chassis/discount not carried — "a copied quote starts with clean prices". |
| EDIT-002 Edit hydration order | **ENGINE** | Build concern; unchanged semantics. R1 chip "Editing Q-… rev n". |
| EDIT-003 Replay mode (legacy records) | **ENGINE** | Must be preserved as the compatibility guarantee for old records (DATA_MODEL_DELTA §6). |
| EDIT-004 Balance gate | **DESIGN** (specified, not mocked) | Amber banner under R1 on edit-load drift: saved figures shown with the explanation; next edit switches to current numbers. Semantics unchanged. |
| EDIT-005 Post-save exit | **FLAG** | Today a successful edit-save drops edit mode. The design proposes: after **any** save the page stays bound to the pending record just saved (chip "Saved Q-… rev n"), and the next Save offers *Overwrite rev n* / *Revision n+1* (mockup). Same modes as today's edit flow, one click earlier. *Default: adopt; BA to confirm.* |
| EDIT-006 Body-switch reset | **DESIGN** | Choosing another body (or REPAIR) resets overrides, selections, discount, record binding; customer/contact are kept (mockup). |
| EDIT-007 Return-trip state | **DESIGN** — *subsumed* | No trip to the Materials editor is needed for price maintenance (in-place drawer). Keep the 30-min snapshot only behind admin deep links from provenance popovers. |
| EDIT-008 700 ms debounce → stale approve (R-11) | **DESIGN** — *changed with sanction (Part 24.9)* | The last server result carries a hash; Save submits it; the server refuses a mismatch. **Replaces** the debounce hazard rather than working around it. |

## 14.9 Validated references — RULE-REF

| Rule | Class | Mapping |
|---|---|---|
| REF-001 Identity contents | **DESIGN** — *changed with sanction (OQ-15)* | Identity = body + dims + door + insulation (side/mm per category) + **extras + user-excludes + category include state**; migration in DATA_MODEL_DELTA §5 (fingerprint v2, recompute from stored `input_state`). |
| REF-002 Marking guards | **DESIGN** | "Mark as validated reference" appears only after a save; drawer binds to the record on screen; refusals name the reason (dims moved / different body / unsaved) — text unchanged. |
| REF-003 Recall is a copy | **DESIGN** | R2 "Validated references (N)" → drawer → Recall; R1 chip "Loaded from reference … balances ✓"; never edit-bound. |
| REF-004 Drift basis | **DESIGN** | Banner under R1: "% vs baseline (materials incl. chassis) · top-3 category deltas"; tolerance from admin setting (2 %). |
| REF-005 Banner is display-only | **DESIGN** | Banner never blocks or writes; recomputed after every server result. |
| REF-006 Retire is soft | **ENGINE** | Admin action unchanged; the R2 link is disabled at zero references (mockup). |

## 14.10 Special rules — RULE-SPEC

| Rule | Class | Mapping |
|---|---|---|
| SPEC-001 3.2 m plywood + glue rule | **DESIGN** | Banner under R1 when in force; affected rows grey-italic "R0 by rule (3.2 m)"; not counted as attention (D3); one line in every export (unchanged). |
| SPEC-002 RICE GRAIN ⇄ KICKPLATES | **FLAG** | The coupling survives as behaviour (ticking RICE GRAIN auto-ticks 1ST ROW KICK; warns on removal) — the mockup shows both as FLOOR family chips without the auto-coupling. *Default: keep the behaviour at build; move the coupling from a hardcoded name pair to data (R-15) in the same change.* |
| SPEC-003 Excel paste | **FLAG** (OQ-13) | Kept as a ⋯ menu entry (mockup stub) per the matrix's [PROPOSAL]. *Default: keep through the transition; retire on BA word.* |

## 14.11 Access — RULE-PERM

| Rule | Class | Mapping |
|---|---|---|
| PERM-001 Grants | **DESIGN** | Money masked `••••` without `bom.view_prices/view_full_cost` (mockup role toggle); permanent price scope gated; Mark-reference gated; exports gated. New keys `costings.freehand_items`, `costings.qty_override`, `costings.template_save` default `{admin, full}` (DATA_MODEL_DELTA §7). |
| PERM-002 `menu.calculator` unenforced | **FLAG** (OQ-11) | *Default: the new page enforces it.* |
| PERM-003 React shell permissive by design | **FLAG** | Enforcement stays on the API; the new page reads its capability flags from the same permission endpoint the shell uses. *Default: no change to the shell's model.* |

---

## FLAG register (11 primary + 1 sub-flag — each with a default; none blocks design or build)

| Rule | Question | Default |
|---|---|---|
| CALC-003 | close the negative-clamp pure-number hole? | close it |
| CALC-007 | who fixes `num_doors`? | page derives it from the door choice |
| CALC-010 | keep unrounded category totals? | keep engine; show server totals only |
| CALC-016 | 30 s cache divergence | same loader for calculate/approve |
| INS-008 | flip clears pair-row user-excludes on the record? | yes, pair-scoped |
| SEC-002 | heal R-13 NULL-section optional rows? | data-fix script at build |
| SAVE-003 (R-04, sub-flag) | numberless record | visible "no quote number" chip |
| EDIT-005 | stay bound to the record after any save (Overwrite offered)? | adopt |
| SPEC-002 | RICE GRAIN ⇄ KICK coupling as data | keep behaviour, move to data |
| SPEC-003 | Excel paste keep/retire | keep through transition |
| PERM-002 / PERM-003 | enforce `menu.calculator`; shell model | enforce; shell unchanged |
