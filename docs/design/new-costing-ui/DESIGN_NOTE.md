# Design note — the new ICB costing page (§3.4)

**What this is:** the record of decisions behind the design concept in this folder — what was chosen, what it cost, what was rejected and why. Companion to `IA.md` (structure), `index.html` (behaviour), `RULE_COVERAGE.md` (81/81 rules), `DATA_MODEL_DELTA.md` (storage/contract).
**Spec of record:** `docs/handoffs/MES_COSTING_CURRENT_STATE_AND_NEW_UI_REQUIREMENTS.md` (#132 + #133). Ratified design-phase decisions are cited as **D1–D6** (spec §34.1) and OQ-numbers.
**Persona:** Nadie. The test applied to every element: *what would the spreadsheet user expect?*

---

## 1. The idea in one paragraph

The workbook had one sheet per body, sections down column B, a row per material, and one number that mattered at the bottom. The new page keeps that mental model and removes everything the app had put between Nadie and it: **one page, one vocabulary (categories), one row grammar, one truthful Save.** Categories are the organising unit and carry their own choices (insulation, plywood, kick plates…) — because the data already says so (`body_option_group == section name`). Everything the engine decides is *shown as state with a reason*, never as absence. Everything the user types is *blue*, everything the system computes is *black*, everything that needs attention is *red* — the same three colours a financial-modelling spreadsheet uses. The rules do not change; where they see the light changes.

## 2. Decisions and their trade-offs

### 2.1 Categories carry their choices (IA §2) — instead of a body-options panel
- **Chosen:** each card renders the option families whose group name equals the section name; radio siblings and orphan groups go to one page-level Body-choices strip (**D5**).
- **Why:** three renderers for one concept was pain point #3; the data already groups options by category on all 17 v2 bodies; Nadie thinks "the floor is PU 100" not "FLOOR PU flag = Y".
- **Cost:** legacy bodies (9/26) get a strip family labelled by group name — honest but less pretty; per-item gating reasons must be derived server-side (2,087 legacy links) — derived, not authored (guard-rail 1).
- **Rejected:** a single "Options" side panel (recreates today's panel, keeps options away from what they affect); a wizard/step flow (kills the one-page directness the brief demands).

### 2.2 Exclusion is a *state with a reason*, never a vanished card (IA §2.2)
- **Chosen:** five current mechanisms + the new user excludes map to visible card/row states: `included · optional-off · excluded-by-user · excluded-by-rule · not-quoted-sibling`, `costed · excluded-by-user · gated · zero-by-rule · unpriced · formula-error`.
- **Why:** consequence-blind exclusion was a spec finding; hard-drop semantics (RULE-SEC-004) stay server-side but the user must *see* the sibling that isn't quoted (guard-rail 2).
- **Cost:** longer pages (collapsed cards still take a row). Accepted — collapsed cards are one line.
- **Rejected:** hiding rule-excluded categories with a "show hidden (3)" link — puts the invisible-rules problem back one click away.

### 2.3 Insulation lives inside the category, per costing (IA §4.3; **D1**, OQ-02)
- **Chosen:** `[EPS|PU] [mm]` on the card; the unselected side is 0 by construction; template writes only through an explicit, listed, gated drawer; "≠ template" marker; apply-to-all as an inline chip.
- **Why:** pain point #2 (costing gestures rewriting the template); RULE-INS-002/005 and DOOR-004/005/006 become structural rather than healed — three healing layers retire.
- **Cost:** a comms line at rollout ("your gesture no longer updates the template — use Save to template"); mm-vs-m display (**D1**: mm in the control, metres in the tooltip and on the wire).
- **Rejected:** a thickness field per side (lets both-zero back in); a modal for switch-all (the current modal interrupts; the chip suggests).

### 2.4 Provenance grammar: blue / black / red + one glyph + one dot (IA §5)
- **Chosen:** Excel modelling convention for text colour; `ƒ` recipe, pin permanent, `*` quote override; a price-age dot; row tags `stock` / `manual`; grey-italic "R0 by rule".
- **Why:** six value origins had six unrelated conventions (red text, badges, tooltips, modals, tours). One grammar Nadie already knows beats a legend she has to learn.
- **Cost:** colour alone is not enough for accessibility → every colour is paired with a glyph or tag and a tooltip; a Legend link sits in the header.
- **Rejected:** per-origin coloured backgrounds (noisy on a 50-row page); icons only (need a legend to decode).

### 2.5 Quantity override replaces the final quantity, sticky, with a moved-formula chip (**D2**, OQ-03 provisional)
- **Chosen:** click a qty, type, Enter → blue + ↺; the engine already returns the post-multiplier quantity so "final" is the existing semantic (**D2**); sticky across recomputes with an amber "formula now N" chip when the formula moves.
- **Why:** pain point #1 — quantity changes should never mean a permanent formula edit; sticky matches Excel (a typed cell stays typed); the chip prevents the "stale override" silent trap.
- **Cost:** OQ-03 remains provisional (BA-coordinator to confirm with Michael on the mockup); the formula editor stays available only from the row menu, labelled "changes the body template".
- **Rejected:** derived-wins (dims change silently discards what Nadie typed — the opposite of a spreadsheet); a per-line "lock" toggle (extra affordance for the same outcome).

### 2.6 One price gesture, scope chosen at apply time (IA §3; RULE-PRICE-002/003)
- **Chosen:** click a price → drawer with current value + source, new value, scope radio (*this costing* → reason ≥ 5 chars; *permanently for this section* → gated), Clear override; recipe prices open a read-only breakdown with an admin deep link.
- **Why:** five price surfaces collapse to one experience without touching the precedence chain (RULE-PRICE-001).
- **Cost:** a drawer, not a cell edit — a value + reason + scope don't fit in a cell (raised in §3.1; ratified on default).
- **Rejected:** editing recipe ingredient prices from the costing page (RULE-CALC-014 admin surface; R-18 client re-implementation retired on purpose).

### 2.7 Loud zeros: cell → row → page, warn-and-acknowledge at save (**D3**)
- **Chosen:** red cell + red stripe + attention pill that jumps to the first offender; the picker shows "no price" *before* adding; Save requires an acknowledgement recorded on the record; rule-zeros are grey-italic and not counted.
- **Why:** R-20 was rated High; five perennial unpriced extras on prod cost R0 silently.
- **Cost:** one extra tick at save when zeros exist. Accepted — Excel would let you quote; the app makes you say you meant to.
- **Rejected:** blocking save (Nadie may legitimately quote a line "TBC"); a warning toast (evaporates).

### 2.8 The truthful Save (IA §6; RULE-SAVE-001..003, R-05)
- **Chosen:** dup check runs as soon as customer + type are set; the button names its outcome; a compact mode selector (New · Revision N+1 ☐ reuse quote no. · Overwrite pending); Replace in ⋯ with typed confirmation; "Save without customer" inline; result-hash binding (Part 24.9).
- **Why:** three chained modals became one honest button; R-05 (bulk delete, no confirm) is closed by the typed word; RULE-EDIT-008 (stale approve) is closed by binding, not by waiting.
- **Cost:** EDIT-005 semantic proposal — after any save the page stays bound to the pending record (Overwrite offered) — flagged for BA confirmation (RULE_COVERAGE FLAG register).
- **Rejected:** keeping the modal chain "because users know it" (they know it as friction).

### 2.9 REPAIR is a subtraction, not a second page (IA §7; OQ-08/09 ratified, **D4**)
- **Chosen:** same chrome; header swaps L/W/H for *Type of repair* (required, admin list, name snapshotted) + optional *Work description* (**D4**); one flat list with the identical row grammar; margin default 0, ratio 55 %; same Save with duplicate detection by customer + costing type.
- **Why:** repairs are quoted in Excel today because the app had only a flag; a flat list is what those Excel repair quotes are.
- **Cost:** `trailer_type_id` NULL for repairs (verified nullable — no schema fight); references and Excel paste don't apply (hidden).
- **Rejected:** repair "categories" (parts/labour) — labour is out of scope and grouping adds nothing to a 3–10-line quote; a separate repair page (the brief's one-flow rule).

### 2.10 OPTIONAL EXTRAS is a picker, not a table (**D6**)
- **Chosen:** only chosen extras appear as rows; "+ Add extra" opens the picker pre-filtered to the extras list with "show all"; adding an extra includes the category; unpriced extras are flagged in the picker.
- **Why:** 134–136 rows per body verified on dev — a ticked table is unusable; today's inverted controls (checked = excluded) go away.
- **Rejected:** a searchable ticked table inside the card (still a wall; still per-browser state).

### 2.11 Category-exclude warning is generic and inline (OQ-12), `× N` badge tooltip replaces the single-side view (OQ-10)
- Generic text names the category, line count and subtotal removed; per-category consequence text can arrive later as data. The admin single-side display mode is dropped; the multiplier badge's tooltip shows the per-side amount.

### 2.12 References: recall as copy, drift as banner, mark after save (RULE-REF-*, OQ-15)
- **Chosen:** header link "Validated references (N)" → drawer → Recall (copy, chip "balances ✓"); drift banner with % and top-3 category deltas; Mark appears only after a save and binds to that record; extras + user-excludes + category state re-enter identity with a one-shot fingerprint v2 recompute (no dual definitions).
- **Rejected:** a permanent references sidebar (rarely used; steals width from the rows).

## 3. What was mined from v4.37 (OQ-01) and what was not
- **Mined (plumbing):** `CalcRequest`/`CalcResult` typing, `/api/check-duplicate` usage, `/api/calculations/{id}` etag → 412 optimistic lock, `revisionLabel` display mapping, sequence-guarded live calc.
- **Not inherited:** its layout, iframe-parity flow, single-form interaction model, flat rendering of v2 bodies.

## 4. Deliberate omissions from the mockup (specified in RULE_COVERAGE, not clickable)
DOOR-007 (NO REAR DOORS + side doors) as a third Rear-door option; EDIT-001/002/004 entry via `?from=`/`?edit=` (post-save edit state *is* mocked); Print / Full report / Export / Excel paste (stubs); RICE GRAIN ⇄ KICK auto-coupling (SPEC-002 flag); admin surfaces (repair types CRUD, template authoring) — outside the costing flow by design.

## 5. Open questions carried to the build (all with defaults — none blocked design)
- OQ-03 sticky qty override + moved-formula chip (provisional, to Michael with the mockup).
- RULE_COVERAGE FLAG register (11 + 1 sub-flag): CALC-003/007/010/016, INS-008, SEC-002, SAVE-003(R-04), EDIT-005, SPEC-002/003, PERM-002/003.
- Spec OQs still open and untouched by design: OQ-04 (promote free-hand to catalogue later), OQ-05 (`calc2_default_excluded` seeds → recommend: migrate as initial `user_excluded_bom_ids` on first open of a body, then retire the flag), OQ-06 (price source policy), OQ-07 (per-item selling price — picker exposes the seam, nothing more), OQ-11, OQ-13, OQ-14.

## 6. What the build phase should decide first
1. Branch target (main vs backport) — BA-coordinator at ratification.
2. Alembic numbers for §DATA_MODEL_DELTA §9 (parallel-lane check).
3. Whether the new page replaces `/costings/new`'s iframe embed in the React shell or ships as a new route beside it during transition (design assumes: new route, then cut over).
4. Journey coverage: both Part-32 journeys as browser journeys from day one, with the CPU-throttle repro rig for the debounce-free save path.

---
*Design phase closes with: PR (docs/mockup only), the mockup served on a side port with a click guide, this note, RULE_COVERAGE 81/81, DATA_MODEL_DELTA. Build-phase WO follows ratification.*
