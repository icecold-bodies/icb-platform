# New Costing UI — Information Architecture (§3.1)

**Status:** design-phase artefact, for ratification before hi-fi. Spec of record: `docs/handoffs/MES_COSTING_CURRENT_STATE_AND_NEW_UI_REQUIREMENTS.md` (#132, `c76579c`; ratified design decisions D1–D6 / OQ-10 / OQ-12 in its §34.1 via #133).
**Companion:** `wireframe-lofi.html` (greybox, both variants). Not a visual design.
**Persona:** Nadie — the person who lived in the Excel workbook. Test for every element: *what would the spreadsheet user expect?*

---

## 0. The one sentence

**One page. One vocabulary (categories). One row grammar. One truthful Save.**
The old app's rules and data flow through unchanged; only where the user *sees* and *touches* them changes.

---

## 1. Page regions (both variants)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ R1  TOTALS BAR (sticky top)  Materials │ +Margin │ ÷Ratio = TOTAL │ −Disc = NET │
│     + attention pill  ⚠ 2 unpriced · 1 formula error     + edit/copy/ref chip │
├─────────────────────────────────────────────────────────────────────────────┤
│ R2  COSTING HEADER   [Costing type / Body ▾]  L W H  Margin  Ratio           │
│                      Customer ▾  Contact ▾   (repair: Type of repair ▾, Work) │
│                      Validated references (N) ▾   Legend                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ R3  BODY CHOICES STRIP  (body variant only)  Rear door: [DRD|SRD]  …          │
├─────────────────────────────────────────────────────────────────────────────┤
│ R4  CATEGORY CARDS  (body)         │  R4' REPAIR LINES  (repair)              │
│     ▸ FRONT        [✓ Include] R … │      one flat list, same row grammar     │
│       Insulation [EPS|PU] [60 mm]  │                                          │
│       rows …                        │                                          │
│     ▸ SIDES  ×2 …                   │                                          │
│     ▸ OPTIONAL EXTRAS (picker-style)│                                          │
│     ▸ CHASSIS       [ ] Include     │                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ R5  SAVE BAR (sticky bottom)  Discount [ ]  [Save as new costing ▾]  ⋯ more   │
└─────────────────────────────────────────────────────────────────────────────┘
      R6  DRAWER (right, on demand): stock picker · free-hand line · price edit
                                     · reference recall · save-to-template diff
```

| Region | Purpose | Always visible? |
|---|---|---|
| R1 Totals bar | The four money stages (Part 24.1), permission-masked `••••`; the attention pill (D3); mode chip ("Editing Q-… rev 2" / "Copied from Q-…" / "Loaded from reference 'X' · balances ✓") | Yes — sticky |
| R2 Header | What is being costed and for whom. Body variant: body ▾, L/W/H, margin, ratio, customer, contact, references. Repair variant: REPAIR ▾, customer, contact, type of repair (required), work description (optional, D4), margin, ratio | Yes |
| R3 Body choices strip | Page-level choices that select *between* categories or don't belong to one: rear door DRD/SRD (radio-sibling categories, RULE-SEC-005), legacy groups whose name matches no category (D5) | Body variant only; hidden when empty |
| R4 Category cards | The organising unit (Part 25). Order = `bom_sections.sort_order`. Includes OPTIONAL EXTRAS (picker-style, D6) and CHASSIS as cards | Body variant |
| R4' Repair lines | One flat list; same row grammar as a category's rows | Repair variant |
| R5 Save bar | Discount (percent ⇄ amount, one clears the other), the truthful Save button + mode selector, overflow (Replace, Print, Full report, Export, Excel paste, Save insulation to template) | Yes — sticky |
| R6 Drawer | Everything that needs more than a cell: stock picker, free-hand entry, price-edit scope, reference recall, save-to-template diff. Never a modal for data entry; confirmations only for destructive/irreversible acts | On demand |

**No navigation.** Admin surfaces (Body Templates, Configurator, Formulas, Materials, recipe engines, Repair types) are reachable only from deep links inside provenance popovers ("edit recipe →", "template →") — never from the costing chrome.

---

## 2. The vocabulary: category

A **category** on the page = one `bom_sections` row (global registry, identity by name) as it applies to the selected body:

- **rows** = the body's `bill_of_materials` rows in that section;
- **choices** = the body's `is_body_option` rows whose `body_option_group == section name`, grouped by `body_option_subgroup` into *families* (INSULATION, PLYWOOD, KICK, SURFACE …), each family rendered by its `selection_mode`: `single` → segmented control (pick one), `multi` → chips (tick any);
- **state** (§4) = included / excluded-by-user / excluded-by-rule / not-quoted-sibling / optional-off, plus multiplier and subtotal.

Two special cards:
- **OPTIONAL EXTRAS** (any section optional by flag or `OPTIONAL` prefix, RULE-SEC-001): renders picker-style — only chosen extras appear as rows; "+ Add extra" opens the drawer picker pre-filtered to that section (D6). Default excluded (RULE-SEC-002).
- **CHASSIS**: not a BOM section but presented as the last card (Include toggle + length · axles · lift axles · tyre style · suspension · lift type · brake · tyre · rim; derived counts shown, RULE-CALC-013). Its subtotal joins Materials exactly as today (RULE-CALC-012).

### 2.1 Option → category mapping rule (both worlds)

```text
for each is_body_option row of the body:
  if row is a "master" row (a section's body_option_master_id resolves to it BY NAME)
        → it is a page-level choice in R3 (e.g. DOOR TYPE: DRD | SRD)
  elif body_option_group == some section name of this body
        → it is a choice family INSIDE that category card          (v2 bodies: always)
  else  → it lands in R3 "Body choices" as its own family          (D5; legacy bodies)
```

- The mapping is **derived at render time from existing columns** — no new authoring, no data-entry project.
- v2 bodies (17/26): every option group on the dev DB matches a section (FRONT/FLOOR/ROOF/SIDES/DRD/SRD) → all choices sit in-card except DOOR TYPE.
- Legacy bodies (9/26): messy groups (e.g. TAUT LINER RIGID group `DRD` = floors + tail board + reflexite tape, `multi`) → those families sit in R3, labelled by group; the gating they drive (`body_option_linked`, DRD*/SRD* prefix) still fires server-side and surfaces as row/card state (§4).

### 2.2 Gating becomes visible state — never absence

All five current exclusion mechanisms (spec §6.1) map to **visible** states with a reason string:

| Mechanism today | Visible as | Reason string |
|---|---|---|
| Optional section not ticked | Card state *optional-off* (collapsed, grey, "Include" unticked) | — |
| Radio-sibling not selected (SEC-005) | Card state *not-quoted-sibling*: card stays in place, collapsed, header reads **"SRD — not quoted (DRD chosen)"**; rows hidden behind "show 10 rows" | "not quoted — DRD chosen" |
| Masterless tickbox / ancestor folder off | Card state *excluded-by-rule* | "excluded — {folder/tickbox name} off" |
| v2 master gate / archived section (SEC-006) | Card state *excluded-by-rule* | "excluded — needs {master name}" / "archived" |
| Per-item `bom_conditions` (SEC-007) | Row state *gated*, greyed, reason chip | today's server reason ("FRONT PU = Y") |
| Legacy `body_option_linked(_id)` (SEC-009) | Row state *gated*, greyed, reason chip | **DERIVED** by the server from `body_option_linked` / `_id`: "linked to {option name}" — *not authored, not a data-entry project* (2,087 rows) |
| Legacy DRD*/SRD* prefix (SEC-008) | Card state *not-quoted-sibling* (same as radio-sibling) | "not quoted — SRD chosen" |
| User excludes a category (new, Part 25) | Card state *excluded-by-user* | "excluded by you" |
| User excludes a line (Calc-2 model generalised) | Row state *excluded-by-user* | "excluded by you" |

**Hard-drop semantics preserved:** rows in a *not-quoted-sibling* or *excluded-by-rule* card are still not costed and still not in category totals (RULE-SEC-004) — the card is simply *there*, collapsed, saying why. This is guard-rail 2 from the BA: the excluded sibling is a visible card, never a vanished one.

---

## 3. The row grammar (one, everywhere)

Every costed line — template row, stock pick, free-hand line, repair line — renders in the same columns:

```text
 [◉] Description                 Qty      Unit    Price      Total     ⋯
     tags: stock | manual        (blue if  (m² /   (blue if   (grey if
     reason chip if gated         override) each)   quote-ovr) excluded)
```

| Column | Content | Interaction |
|---|---|---|
| Include cell `◉` | per-line include (normal polarity: checked = included) | click toggles; excluded rows stay visible, greyed, total `—` (RULE-CALC-008 / SEC-012 — no "eye" toggle needed: excluded rows are always visible, dimmed) |
| Description | material / free-hand text; row tag `stock` / `manual`; reason chip when gated | free-hand description editable in place |
| Qty | **final** quantity (post multiplier + waste — D2, existing engine semantics) | click → type → override (blue) + `↺` revert; hover shows "formula gives N"; amber delta chip when formula's value moves under a sticky override (OQ-03 provisional) |
| Unit | material UoM | read-only |
| Price | unit price; provenance glyph (§5) | click → drawer: new value + scope {this costing (reason ≥ 5 chars) · permanent (needs `costings.price_master_edit`; per-ROW, RULE-PRICE-003)}; recipe-priced rows open the read-only breakdown instead |
| Total | qty × price | read-only |
| `⋯` | row menu: exclude/include · revert qty · price… · formula (ƒ, power users; labelled "changes the body template") · remove (stock/free-hand lines only) | — |

Repair lines use exactly this grammar (no gating states, no formula menu).

---

## 4. State model

### 4.1 Category card state
```text
included            header normal, rows shown, subtotal counted
optional-off        collapsed, grey, Include unticked (OPTIONAL sections only, default)
excluded-by-user    collapsed, amber left edge, "excluded by you · N lines · R … removed"  [Include ticks it back]
excluded-by-rule    collapsed, grey, reason "excluded — needs DRD" (Include control disabled, tooltip names the choice that would enable it)
not-quoted-sibling  collapsed, grey, "SRD — not quoted (DRD chosen)"; the R3 choice is the only way to flip it
```
Consequence warning on **excluding a non-optional category** (OQ-12, generic): inline in the card, not a modal — "Excluding FLOOR removes 15 lines (R 48 300) from this costing. [Exclude anyway] [Keep]". Optional categories toggle without warning.

### 4.2 Line state
```text
costed              normal
excluded-by-user    greyed, total —, include cell empty
gated               greyed, reason chip, include cell disabled
zero-by-rule        grey italic, "R0 by rule" tag (RULE-SPEC-001) — NOT counted in the attention pill (D3)
unpriced            red cell "no price", red left stripe, counted in pill
formula-error       red qty cell "— err — {TOKEN}", red left stripe, counted in pill
```

### 4.3 Insulation state (per insulated category)
`{ side: EPS|PU, thickness_mm }` per pair, **per costing** (Part 26 / OQ-02). The unselected side is 0 by construction (RULE-INS-002 becomes structural). Rear door: the chosen door card carries the control; the other door card is *not-quoted-sibling*. Divergence from the template shows a small "≠ template" marker on the control; "Save insulation to template…" lives in the R5 overflow, gated `{admin, full}` (`costings.template_save`), opens the R6 diff drawer. Edit pins (RULE-INS-007) are subsumed: the per-costing values are the pins.

### 4.4 Costing-level state
```text
mode:            new | edit(record, rev, etag) | copy(from) | recall(reference)
costing_type:    body(trailer_type_id) | repair(repair_type_id, work_description)
money:           margin%, ratio (0.30–0.70 step 0.025, default 0.55), discount {percent|amount}
customer/contact
acknowledged_zeros: bool (D3 — recorded on the saved record)
result_hash:     from the last server result; Save submits it; server refuses on mismatch (Part 24.9)
```

---

## 5. Provenance grammar (Part 24.6)

Excel modelling convention, which the persona already reads fluently: **blue = you typed it, black = the system**. Plus one glyph and one dot.

| Value origin | Text | Glyph / mark | Tooltip |
|---|---|---|---|
| Formula quantity | black | — | "formula: (length+{Waste})×… → 73.44 · ×2 sides · waste 0%" |
| Quantity override (this costing) | **blue** | `↺` revert | "you set 80 · formula gives 73.44" |
| Catalogue price | black | price-age dot: green ≤ 7 d, amber ≥ 90 d (RULE-PRICE-004) | "Catalogue · updated 3 Aug" |
| Recipe price (skin/taping/floor/cleat) | black | `ƒ` | "Computed price — skin formula 'X' (standard region)" → breakdown popover, link "edit recipe →" |
| Permanent row override | black | pin | "Permanent price for this section (set 12 Jul by …)" |
| Quote price override (this costing) | **blue** | `*` | reason text |
| Stock-pick line | row tag `stock` | — | "added from stock list" |
| Free-hand line | row tag `manual`; all cells blue | — | "manually entered" |
| Zero by rule | grey italic | `R0 by rule` tag | rule text (3.2 m plywood/glue) |
| Unpriced / formula error | **red** | red left stripe | "no price on catalogue item" / "unknown token {X}" |

Legend: a "Legend" link in R2 opens a one-screen key. Price-age badges suppressed under a quote override (as today).

---

## 6. Interaction inventory ↔ Part 32 journeys

**Standard costing**
1. Pick body → page costs at defaults (dims from body, margin from markup, ratio 55%, choices from `body_option_default`, OPTIONAL EXTRAS off).
2. Review cards; untick Include on a structural card → inline warning → Exclude anyway / Keep.
3. Insulation inside FLOOR: `[EPS|PU] [60 mm]`; flip → assist chip "Apply PU to all 6 insulated categories?".
4. Change L/W/H in R2 → totals bar updates (server recompute; single authority).
5. Click a qty → type → blue + revert. Click a price → drawer → value + scope.
6. "+ Add item" in any card → drawer: stock search (name / SAP code / category / sub-category; unit, price, price age; "no price" shown before adding) or free-hand (description, qty, price, note).
7. OPTIONAL EXTRAS "+ Add extra" → picker pre-filtered; unpriced extras show "no price" in the picker and land red.
8. Customer + contact (add contact inline) → discount in R5.
9. Save button reads its outcome ("Save as new costing" / "Save revision 3 of Q-…" / "Overwrite rev 2") — mode selector beside it; no-customer → "Save without customer"; unpriced present → acknowledgement checkbox appears in the button's confirm popover (D3).
10. After save: "Mark as validated reference" appears in R2 next to references, bound to the saved record.

**Repair costing**
1. Dropdown → REPAIR → R3/R4 replaced by R4'; header shows Type of repair (required) + Work description (optional).
2. "+ from stock" / "+ free-hand" → drawer → lines.
3. Margin defaults 0, ratio 55%; totals bar identical.
4. Save → same truthful button; duplicate detection = customer + REPAIR type (independent revision sequence).

**Price maintenance (Nadie)**: amber dot on a price → click → drawer → new value → scope permanent (permission) → done, no navigation.

**Recall a baseline**: R2 "Validated references (3) ▾" → pick → page loads as copy; R1 chip "Loaded from reference 'X' · balances ✓"; drift banner under R1 when identity matches and totals differ ("Matches 'X' · +2.4% · FLOOR +R1 200 · ROOF −R300").

**Edit / copy**: `?edit=` → R1 chip "Editing Q-… rev 2"; balance drift → amber banner with saved figures (RULE-EDIT-004 semantics unchanged); `?from=` → chip "Copied from Q-…", clean prices (RULE-EDIT-001).

---

## 7. Repair variant = body variant minus

Removed: L/W/H, R3 strip, category cards, insulation, chassis, references (references are body-typed), Excel paste.
Added: Type of repair ▾ (required, admin-maintained list, name snapshotted at save), Work description (optional).
Unchanged: totals bar, customer/contact, margin/ratio/discount, row grammar, add-item drawer (both methods), truthful Save, print/report/export, accept/decline lifecycle downstream.

---

## 8. What is deliberately NOT on the page

- Any template/configurator/formula authoring (deep links only from provenance popovers).
- Modals for data entry (drawer instead); modals only for destructive confirmations (Replace, typed).
- The "eye" toggle for hidden rows (excluded rows are always visible, dimmed).
- Inverted controls (checked = excluded) — gone.
- The single-side (`× N` display-mode) toggle (OQ-10 dropped; tooltip shows per-side amount).
- A second calculator, a second page, a second application.

---

## 9. Open for ratification with the wireframe

- OQ-03 (sticky qty override + amber delta chip) — provisionally accepted by BA-coordinator; to Michael with this wireframe.
- Drawer vs inline for price-edit scope: I propose the drawer (reason text + scope radio don't fit a cell); flag if Michael prefers a popover.
- Whether the attention pill blocks *export* (not save): default no — exports show the same red lines.
