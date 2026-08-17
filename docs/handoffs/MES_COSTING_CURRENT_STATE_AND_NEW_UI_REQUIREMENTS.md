# MES Costing — Current State & New UI Requirements

**Document type:** Business Analyst specification (reverse-engineering + design brief)
**Author:** BA-coordinator (CA), interviewing Michael (BA) — 17 Aug 2026
**Codebase evidence:** branch `backport/v1.39-base` @ `5bed400` (v1.46.4 — the code on production)
**Audience:** the CA who will design and build the completely new ICB Costing UI

> **How to read this document.** Parts 1–22 describe what the existing system *does* — every screen, rule, calculation and dependency, with `file:line` evidence. Parts 23 onward describe what the new costing experience *must achieve*. Statements are labelled **[FACT]** (verified in code/DB/workbook), **[INFERENCE]** (derived, with reasoning), or **[PROPOSAL]** (not yet a ratified requirement). The governing principle, ratified by the BA:
> **Simplify the user experience. Do not simplify the business logic.**

---

## 1. Executive Summary

The ICB costing system prices refrigerated/specialised truck bodies. It began life as one Excel workbook per body-type family (`GRP Costings 2018.xlsx`, 33 sheets), priced from a price-list workbook (`PRICE 2017 MARCH.xlsx`) and a recipe workbook (`FORMULAS 2018.xls`). The current MES application faithfully reproduces that model in a database: worksheets became **body types**, worksheet sections became **BOM sections/categories**, price-list rows became **materials**, and the recipe sheets became four computed-pricing engines (skin formulas, taping blocks, floor plates, mounting cleats).

The application is functionally complete and numerically trustworthy — it has an Excel-audit tool that reconciles a live costing against the original workbook line-by-line, and a "validated references" feature that locks known-good costings as baselines. But the *experience* is spread across two calculators, a Body Templates admin page, a Body Configurator, a formula library, and seven pricing admin screens. The primary user (**Nadie**, the person who previously lived in the Excel workbook) must navigate template configuration, body-option trees, and formula tokens to do what used to be "open the sheet, change a number".

The BA's core complaint, verbatim: *"the current way formulas are implemented are complicated for the user to update the prices and need to be simplified."*

**The redesign mandate (ratified in BA interview, 17 Aug 2026):**

1. One primary costing page. Select an existing body type → cost it. No Template page in the costing flow.
2. Categories become the organising unit: include/exclude any category (with a warning), insulation configured *inside* the category, items editable in place.
3. **Calculator 2 is eliminated entirely.** Its two unique features (repair flag, per-line excludes) are re-homed into the new design.
4. **Repair costing becomes a first-class costing type**: chosen from the same dropdown as body types; built from stock-list picks and free-hand lines; records customer and type of repair. (Today repairs are quoted manually in Excel — the app has only a flag.)
5. Totals always visible at the top: Materials → +Margin → ÷Ratio = TOTAL → −Discount = NET.
6. Rules apply automatically. The user works with the costing; the application decides what applies.
7. All existing business rules survive. This document catalogues them (Part 14: 71 rules) precisely so none is lost by accident.

---

## 2. Existing System Overview

### 2.1 Two glued stacks [FACT]

| Stack | Location | Role |
|---|---|---|
| Legacy FastAPI + Jinja | `backend/app/` | **All** costing capture and **all** costing configuration. Server-rendered pages + three large vanilla-JS files (`calculator.js` ~8,000 lines) |
| React MES shell | `frontend/src/` | List/detail/KPI layer over the same `/api/*`. Does **not** reimplement the calculator: `/costings/new` embeds `/mes/calculator` in a same-origin iframe, wired by `postMessage` |

The "MES look" is one conditional in `base.html:5` — any legacy page loaded with `?skin=mes` gets the light theme. Same templates, same JS, same controls. There is no separate MES calculator.

### 2.2 The costing engine in one diagram [FACT]

```text
Body Type (trailer_types)
   ↓ owns
BOM rows (bill_of_materials) ──── grouped by ──── Sections (bom_sections)
   │  formula_expression  (quantity formula, e.g. "wall_area * 1.05")
   │  waste_percentage
   │  price: skin_formula | taping_block | floor_plate | mounting_cleat
   │         | unit_price_override | material.price_per_unit
   ↓
POST /api/calculate  (server)
   qty  = eval(formula) × section_multiplier × (1 + waste%)
   line = qty × price
   category_totals, grand_total (+ chassis if enabled)
   ↓ client adds (display only until save)
   + Margin%  → ÷ Ratio  → − Discount  = what the user sees
   ↓
POST /api/approve  (server recomputes WITH ratio+discount)
   calculations row: dimensions_json + result_json(version, input_state, ui_snapshot)
   quote_number assigned (global counter, immutable)
```

### 2.3 Excel lineage [FACT — workbook verified 17 Aug 2026]

| Workbook | Structure | Became |
|---|---|---|
| `GRP Costings 2018.xlsx` (still LIVE — modified 13 Aug 2026) | 33 sheets, one per body family, size-banded (e.g. icecream ≤3.2 / ≤4.8 / 4.9+) | `trailer_types` + their BOMs. The size bands survive as separate body types and as data rules (e.g. the 3.2 m plywood rule) |
| `PRICE 2017 MARCH.xlsx` | 20 sheets by material family; columns `ITEM · SIZE · DATE · PRICE · … · SAP CODE` | `materials` (+ `manufacture_sub_category` = source sheet name). The DATE column is the ancestor of the app's price-age badges; SAP CODE became `materials.sap_code` |
| `FORMULAS 2018.xls` | 6 sheets: FORMULA SKINS, SAP ITEM CODES (5,147 codes), TAPING BLOCKS, MOUNTING CLEATS, SRD FLOOR PLATE, TRAILER FITTINGS | The four recipe-pricing engines + the `sap_item_codes` table |
| `PRICE 20.04.2004.xls` | **discovered during this investigation** — 29 formulas in the live workbook still reference a 2004 price list (concentrated in TAUT LINER RIGID) | nothing — see Open Questions OQ-14 |

Workbook-wide external-reference census (17 Aug 2026): **1,494** formulas reference PRICE 2017 MARCH, **312** reference FORMULAS 2018, **29** reference PRICE 20.04.2004.

### 2.4 What the system deliberately is NOT [FACT]

- **Not a stock system.** No on-hand quantity, availability, warehouse or reorder concept anywhere in the costing domain (Part 10).
- **Not a free-form estimator.** A costing can only contain lines that exist on the body's template. There is no way for a non-admin user to add an arbitrary item (Part 12 — this changes in the new UI).
- **Not a repair coster.** `is_repair` is a badge with its own revision sequence, nothing more (Part 13 / §21).

---

## 3. Existing Screens

Full route map with gates in Appendix A. The screens that matter, with what the user can and cannot do:

### 3.1 Cost Calculator (Calculator 1) — `/calculator`, embedded as `/mes/calculator`

**The** costing surface. `calculator.html` + `calculator.js` (~8,000 lines).

**The user CAN:**
- Select a body type (active types only; inactive appear only when editing an old quote, labelled "(inactive)")
- Enter Length/Width/Height (defaults from the body type, else 13.6 × 2.5 × 2.7), Margin % (default = body's markup), Ratio (default **55%** on a new costing)
- Toggle body options: three different renderers depending on the body's configuration state (§3.1.1)
- Choose insulation per pair (EPS ⇄ PU radio; thickness follows the selection — Part 7)
- Enable/disable optional ("EXTRAS") sections and individual rows within them — **checked = excluded** (inverted!)
- Enable a chassis and configure axles/suspension/brakes/tyres (counts auto-derived)
- Override any line's price **for this quote** (reason ≥ 5 chars mandatory) or — with `costings.price_master_edit` — **permanently for this section**
- Edit a line's quantity formula permanently (formula editor with variable chips)
- Attach customer + contact (contact add-inline; snapshot frozen at save)
- Enter a discount (percent or amount; entering one clears the other)
- Approve & Save (versioning modals — §3.1.2); mark a saved costing as a **validated reference**; recall one
- Paste a settings block from the Excel workbook (dimensions, EPS/PU sides, ticks) — v1.42
- Attach the Excel workbook to the AI help panel and run a line-by-line **audit** against the live costing

**The user CANNOT:**
- Add a line item (empty state literally says *"No BOM items — add items in Admin → Trailer Templates"* — `calculator.js:3009`)
- Remove a non-optional line (only price-override it, or an admin excludes it via configurator rules)
- Change quantity directly — quantity is always the formula's output (the only lever is editing the formula itself, which changes it **for the body type permanently**)
- Create a material, section, or body type
- Unlink a computed price (skin/taping/floor/cleat) — the price modals show a red warning and a "🎯 Show me how" tour pointing at the admin page
- See prices at all without `bom.view_prices` — masked as `••••`

#### 3.1.1 The three body-options renderers [FACT — `calculator.js:4522`]

The same panel renders three different ways, by body-type state:

| Renderer | When | Feel |
|---|---|---|
| Settings-draft tree | `configurator_v2` = true AND a Configurator draft exists | Deep folder/category/flag hierarchy with radios and tickboxes (mirrors the admin Configurator's Explorer 1:1) |
| Configurator tree | v2, no draft | Grouped "pick one" / "flags" cards; first load all-collapsed |
| Legacy flat panel | `configurator_v2` = false | Group → subgroup checkboxes/radios; DRD/SRD get master ON/OFF pills |

**Dev-DB reality check (17 Aug 2026):** 26 active body types, **17 of them v2** — so both worlds are live and the new UI must absorb both. [FACT]

#### 3.1.2 The save flow [FACT — `calculator.js:5116`]

```text
Approve & Save
  ├─ editing?          → Overwrite Rev N  |  Save as Revision N+1 (reuse quote-number ticked)
  ├─ no customer?      → warn: Go Back | Continue Without Customer
  └─ duplicate exists? → Save as new costing | Save as Revision N+1 (reuse qno unticked)
                          | 🗑 Replace — DELETES ALL this customer's costings for this body (no second confirm!)
```

### 3.2 Cost Calculator 2 — `/calculator2` [FACT — being ELIMINATED]

A parallel fork of Calculator 1 sharing the same engine and templates. Differences that matter for the migration matrix (Part 31):

| Only in Calculator 2 | Only in Calculator 1 |
|---|---|
| **Repair Quote tick** (`is_repair`) | Edit mode (`?edit=`) — the whole overwrite/revision flow |
| **Per-line exclude checkboxes on EVERY section** (seeded from `calc2_default_excluded`) | Validated references (mark/recall/drift) |
| Print / Full Report buttons | Excel paste; Export/Preview bridge to the MES shell |
| | Insulation pair guards; NO REAR DOORS machinery; 55% ratio default |

**Ratified decision:** Calculator 2 is retired completely. The repair tick becomes the new Repair costing type; per-line excludes and print/report become new-UI requirements (Parts 24, 29).

### 3.3 Body Templates — `/admin/templates` [FACT]

The only place BOM rows are authored: create/rename/duplicate/deactivate body types; add/edit/remove/move BOM rows; create sections, set multipliers, mark Optional; link/unlink rows to the four computed-pricing engines; mark rows radio/tickbox/always; set default dims + markup; toggle `configurator_v2`; import a body from Excel. **The new UI must make the costing flow independent of this page — but the page's authoring functions must survive somewhere** (they are the only source of template maintenance).

### 3.4 The supporting cast (summary)

| Screen | What it holds | New-UI relevance |
|---|---|---|
| Body Configurator settings + preview (`/admin/settings`, `/admin/configurator-preview`) | The draft tree (folders/categories/flags + per-item include/exclude rules) that renderer 1 displays | The gating logic it authors must survive; the authoring UX is out of the costing flow |
| Formulas (`/admin/formulas`) | Global variables (`{Waste}`) + formula library | Formula simplification is the core pain — Part 23 |
| Materials & Prices (`/admin/materials`) | The de-facto stock list: name, category, sub-category, size, unit, price, supplier, SAP code; bulk ±50% price updates with undo | Becomes the basis of the new stock model (Part 27) |
| Skin Formulas / Taping Blocks / Floor Plates / Mounting Cleats / SAP Prices | The four recipe engines + SAP last-purchase prices (KZN sync) | Computed prices must keep working invisibly |
| Chassis Options (`/admin/chassis`) | Chassis option + constant catalogues | Chassis block carries over |
| Customers, Quote Numbering, Quote/PDF Templates, BOM Snapshots | Supporting admin | Unchanged by this redesign |
| Dashboard (`/`) + React Costings screens | KPIs, worklists, accept/decline, pre-job handoff | Downstream consumers — the new UI must keep feeding them the same saved-costing shape |

### 3.5 Results page — `/results/{id}`

Read-only record of a saved costing: dimensions, geometry, category totals (red = optional sections, `× N` multiplier badges), margin/ratio/selling/discount rows, full BOM with override/outdated/recent markers, chassis. Export (Excel/Word/PDF, multi-ratio columns, optional email — internal-domain allowlist), Generate Quote PDF, Accept/Decline.

---

## 4. Existing Costing Workflow (current state)

Nadie's actual flow today [FACT, assembled from screens + interview]:

```text
/mes-app/costings/new  (React shell, iframe embeds the calculator)
   ↓
Select Body Type            ← dropdown; defaults land AFTER /api/trailers resolves
   ↓
[calculator auto-costs on every change — 700 ms debounce]
   ↓
Adjust dims / margin / ratio
Toggle body options (3 possible renderers)
Choose insulation sides (EPS/PU per pair; rear door follows DRD/SRD)
Tick optional EXTRAS sections/rows
(maybe) Override prices with reasons
(maybe) Enable + configure chassis
   ↓
Attach customer + contact
   ↓
Approve & Save  → versioning modals → quote number assigned
   ↓
(maybe) Mark as validated reference
   ↓
Dashboard/React list: Accept / Decline / Pre-Job Card → production
```

**Friction points observed in code and ratified by the BA (feeds Part 22):**
- Quantity changes require *formula* edits — permanent, token-based, per-body-type.
- Price maintenance is spread over five surfaces (quote override, section override, material price, recipe ingredient prices, SAP sync).
- Insulation and doors silently write to the **shared template** (toast: "Body Template updated") — a costing gesture has fleet-wide effect.
- Three different body-options renderers for the same concept.
- The costing flow depends on admin pages for anything structural.

---

## 5. Body Type Logic

### 5.1 What a body type IS [FACT]

`trailer_types` row: name, description, `is_active` (soft delete — deletion renames to "… [deleted-{id}]" and hides it), `default_length/width/height`, `markup_percentage` (seeds the Margin field), `protect_overrides` (excluded from bulk price propagation), `configurator_v2` (the renderer switch), group (report-template binding). Its BOM rows carry everything else.

Body types ARE the Excel worksheets: one per family × size band. The workbook's `E1` cell (e.g. "FREEZER") became the import hint; dims cells `C4:C6` became the defaults; `G5` became markup; `G8:G18` became the ratio chips.

### 5.2 Where body types are created/maintained [FACT]

Only on `/admin/templates` (manual) or via the three Excel import paths (admin-gated). **Nothing in the costing flow creates or edits a body type's structure** — except the insulation/door thickness writes (§7.4), which are the documented exception and a known surprise.

### 5.3 What selecting a body type does in the calculator [FACT]

1. Loads its BOM (`loadBOM`) — a body-type switch **clears** price overrides, selections, discount, edit state, and `lastRecordId` (v1.46.1: so a stale save can't be referenced).
2. Applies default dims **only after** `/api/trailers` has resolved (a late response leaves template dims 13.6×2.5×2.7 in place — the root of a fixed CI race; see RULE-EDIT-008).
3. Seeds margin from `markup_percentage`, ratio to 55% (new costings only).
4. Renders body options via whichever renderer applies; seeds selections from `body_option_default` / saved localStorage.
5. Auto-calculates.

### 5.4 The ratified new-UI distinction

> **Existing Body Types must be retained** as the starting point of a costing:
> ```text
> Select Existing Body Type → Start Costing
> ```
> The user must **never** need the old Template page to begin, adjust, or complete a costing. The Template page's *authoring* role (creating body types, structural BOM maintenance) continues to exist for administrators — outside the costing flow. **[RATIFIED]**

The same dropdown gains one more entry: **Repair** (Part 21/26) — a costing type that starts from an empty line list instead of a template. **[RATIFIED]**

---

## 6. Category Logic

"Category" and "section" are the same thing seen from two ends [FACT]: `bom_sections` rows (name, `sort_order`, `multiplier`, `is_optional`, v2: `body_option_master_id`, `archived_at`) group BOM rows; the calculator's result groups lines by `row.bom_section` falling back to the material's category (`calculator.py:503`).

### 6.1 How a category can be included/excluded today [FACT]

There is **no single user-facing include/exclude control**. A category disappears from a costing through any of five mechanisms:

| # | Mechanism | User-visible? | Where |
|---|---|---|---|
| 1 | Optional section not ticked | Yes — red header + checkbox | `is_optional` flag OR name starts with `OPTIONAL` |
| 2 | Radio-category sibling not selected | Indirect — picking A drops B | configurator draft `selectionMode='radio'`, siblings by parent |
| 3 | Masterless tickbox category off | Yes (tickbox) | draft state |
| 4 | Ancestor radio/tickbox folder off | Indirect | draft folder gating |
| 5 | v2 section gated by an unselected master / archived | Invisible | `body_option_master_id`, `archived_at` |

Mechanisms 2–5 arrive at the server as `excluded_categories` — a **hard drop**: rows never enter the response at all (`calculator.py:504`), unlike optional/user exclusions which ride along soft-excluded with a reason.

### 6.2 Category facts that must survive [FACT]

- **Multipliers**: a section's total is multiplied (SIDES × 2 on dev). Excel origin: `=SUM(H111:H140)*2`. Shown as a red `× N` badge; admin can click it into a "single side" display mode.
- Dev DB (17 Aug 2026): optional sections are `EXTRAS`, `OPTIONAL EXTRAS` (flagged) and `OPTIONAL EXPLOSIVE EXTRAS` (by name-prefix rule); `SIDES` ×2 is the only multiplier ≠ 1.
- Category totals accumulate **unrounded** line costs and round once; line items round individually — the two can differ by cents in the same view (Risk R-01).
- Excluding a category is currently **consequence-blind**: nothing warns that excluding FLOOR removes the floor.

### 6.3 Ratified new-UI category model

Every category shows an **Include/Exclude** control on the costing page. **Any category may be excluded — with a warning** (Excel-like freedom; the user who deletes the FLOOR section knows why). All five current mechanisms must map onto this one visible model without losing the underlying gating logic (radio siblings, folder gates, master gates keep working — they just become *visible* as included/excluded states). **[RATIFIED]**

---

## 7. Insulation Logic

The most rule-dense area of the system. Insulation is configured **on the costing page's body-options panel** today — there is no insulation admin screen — but its writes land on the **shared body template**.

### 7.1 The model [FACT]

- An **insulation pair** = exactly two body-option rows in the same group/subgroup, one name containing `EPS`, one containing `PU` (structural identification, name-substring based — Risk R-14). Each carries its thickness in `variable_value` (metres).
- Formulas reference thicknesses as `{FRONT EPS}`, `{ROOF PU}` tokens — resolved from **every** body-option row's `variable_value` regardless of selection (which is why the unselected side must be zeroed).
- **The checked radio OWNS the pair's thickness** (v1.39.10 invariant): select PU and the EPS thickness is copied onto PU and EPS is zeroed — persisted with `PUT /api/bom/{id}` → *the template changes for every future costing of that body*.
- Switching one pair offers "Switch ALL insulation categories from EPS to PU?" (global modal).
- Both-sides-zero renders a red **"Both X and Y can't be zero"** warning (suppressed for the inactive rear door). Production scan 29 Jul 2026 found 16 real both-zero pairs.
- Thickness is editable inline — `(0.076 m)` click-to-edit — with an explicit tooltip: *"This change updates the body template — all other costings using this template will see the new value."*
- In an edit, thicknesses are **pinned** (`body_variable_overrides`) so a reopened quote reproduces its saved numbers even after later template changes.

### 7.2 Rear doors are insulation's special case [FACT]

A body is quoted as **either** DRD (double rear door) **or** SRD (single), never both. One rear-door thickness follows the choice. **All skin formulas read `{SRD EPS}`/`{SRD PU}` — none read `{DRD ...}`** — so an SRD quote deducts rear-door insulation and a DRD quote does not. Three healing layers keep this true (on click, on render, on load — RULE-DOOR-003/004/005). Default thickness when nothing exists: 0.06 m.

### 7.3 Legacy hidden defaults [FACT]

`#f-insul-thick = 0.076`, `#f-floor-thick = 0.028`, `#f-panel-thick = 0.063` — hidden inputs still feeding the geometry engine (`insulation_thickness` etc. remain formula variables).

### 7.4 Ratified new-UI insulation model

> Insulation is configured **directly within the relevant category** — no Settings page, no separate panel:
> ```text
> CATEGORY: FLOOR                    [x included]
> Insulation:  Type [ PU v ]  Thickness [ 60 mm v ]
> Item                                Qty      Price     Total
> -------------------------------------------------------------
> Floor Panel                          1       R —        R —
> ...
> ```
> The exact UX is the new CA's to design. **What must not change:** one thickness per pair; the selected type owns it; rear door follows the DRD/SRD choice; the `{TOKEN}` formula linkage keeps resolving. **What must change:** a costing-page gesture must NOT silently rewrite the shared template (see OQ-02 — per-costing insulation values with explicit "save to template" is the obvious shape, but it alters today's semantics and needs BA sign-off). **[RATIFIED direction, OQ on template-write semantics]**

---

## 8. BOM Logic

### 8.1 A BOM row [FACT — `database.py:246-324`]

The widest table in the domain. Per row: body type, material, section (+id), `sort_order`, `formula_expression` (quantity formula, default `"1"`), `waste_percentage`, `unit_price_override` (permanent per-row price), import traceability (`excel_formula`, `source_cell`, `unit_price_snapshot`), body-option fields (`is_body_option`, group/subgroup, `variable_value`, `selection_mode`, `body_option_default`, `bom_conditions` JSON), gating (`body_option_linked(_id)`), `calc2_default_excluded`, and four recipe FKs (`skin_formula_id`+region, `taping_block_id`, `floor_plate_id`, `mounting_cleat_id`).

### 8.2 Row lifecycle [FACT]

Created: admin Body Templates page or Excel import. Never by a user, never from the costing page. Deleted: admin only (hard delete). A soft-deleted material leaves its BOM rows silently costing against the "deleted" material (Risk R-12).

### 8.3 Inclusion pipeline (per calculation) [FACT — order matters]

```text
For each BOM row of the body type:
 1. excluded_categories?          -> HARD DROP (row absent from response)
 2. v2: section archived?         -> skip
 3. v2: section master unselected?-> skip        (FK resolved by NAME locally)
 4. v2: per-item bom_conditions   -> soft-exclude with human reason ("FRONT PU = Y")
 5. legacy: DRD*/SRD* section not selected -> drop
 6. legacy: body_option_linked not selected -> drop
 7. body-option master rows       -> never cost-carrying (v2 drops them entirely)
 8. optional section not enabled  -> soft-exclude "Optional section not enabled"
 9. user_excluded_bom_ids         -> soft-exclude "Excluded by user"
10. survivors -> quantity formula -> price -> line cost
```

Soft-excluded rows still show (with the eye toggle) at qty computed, cost `—`.

---

## 9. Optional Extras

[FACT] A section is optional when `bom_sections.is_optional` is set **or its name starts with `OPTIONAL`** (prefix, not substring — `"NON OPTIONAL EXTRAS"` is not optional; `services/__init__.py:57-63`). Optional sections render red, start **excluded**, and contribute nothing until ticked. State is per-browser (`localStorage` per body type) — which is precisely why optional extras were **excluded from the validated-reference fingerprint** (a reference marked with extras on never matched a fresh browser; ratified 11 Aug 2026).

Client semantics worth preserving exactly: header tick = whole section; row ticks = partial (indeterminate header); disabling a section marks every row excluded so a later single un-tick yields a *partial* state, not all-on. **Checked = excluded** today (inverted) — the new UI should use normal polarity (include = checked) [PROPOSAL].

Known data issue: the five perennially unpriced OPTIONAL EXTRAS materials cost R0 silently when ticked (Prod scan 29 Jul: 135 of 137 zero-price lines). New UI must surface unpriced lines loudly (Part 24).

---

## 10. Stock Logic

### 10.1 Today: there is no stock [FACT]

Zero hits for "stock" across the costing domain. No on-hand, no availability, no warehouse, no reorder. What exists:

- **`materials`** — the de-facto catalogue: name, category, sub-category (source price-sheet name), size, unit (descriptive only — no unit conversion anywhere), `price_per_unit`, supplier, **`sap_code`**, `is_active` soft-delete, price history, bulk ±50% updates with undo.
- **`sap_item_codes`** — 5,147 SAP codes + last-purchase prices, seeded from FORMULAS 2018's SAP ITEM CODES sheet; feeds **only** skin-formula ingredient pricing (KZN sync).
- **`icb_sap` schema** (OWHS/OITM/OITW) — a read-only SAP B1 mock landing zone (ADR 0013) with real stock columns (`OnHand`, `IsCommited`, `OnOrder`, generated `Available`, `AvgPrice`). **No price or stock data flows from it into the costing calculator** — it serves the MES production side.

### 10.2 The SAP-ready conceptual stock model (new-UI requirement)

The brief's target shape maps almost 1:1 onto columns that already exist somewhere:

| Brief field | Exists today as | Gap |
|---|---|---|
| Stock ID / Internal Item ID | `materials.id` / `materials.material_code` (dormant — accepted by the API, absent from the UI) | expose it |
| Part Number / SAP Item Code | `materials.sap_code`; `icb_sap.OITM.ItemCode` | soft join today; formal link later |
| Description / Category / UoM | `materials.name` / `category_id` / `unit_of_measure` | — |
| Cost Price | `materials.price_per_unit` (+ SAP `U_LastPurchasePrice` unused by costing) | price-source policy = OQ-06 |
| Selling Price | does not exist per item (selling is costing-level: ÷ratio) | decide if per-item selling is wanted (OQ-07) |
| Active | `materials.is_active` | — |

**[PROPOSAL]** The new stock list = the `materials` table, surfaced to the costing user as a searchable picker (name/SAP code/category), designed so a future SAP integration populates/updates it by `sap_code` without schema surgery. Do **not** build against `icb_sap` directly today.

---

## 11. Quantity Logic

[FACT — `formula_engine.py`]

- `quantity = evaluate_formula(expr, geometry, body_vars, formula_library) × section_multiplier × (1 + waste%/100)`, rounded to 4 dp.
- Geometry variables: `length, width, height, floor_thickness, panel_thickness, insulation_thickness, num_doors, num_axles, wall_area, roof_area, floor_area, front_rear_area, surface_area, total_panel_area (no floor), volume`. Engine defaults `num_doors=1`, `num_axles=2` — but the client sends `num_doors=2` (Risk R-09).
- `{TOKEN}` resolution: body variable (case-insensitive) → formula library (recursive, cycle-guarded) → unknown = `(0)` **and** the row is flagged `formula_error` (renders `— err —` + red warning; the line still costs whatever the zero-substituted expression yields).
- Empty formula ⇒ quantity **1** (not 0). Negative results clamp to 0 — except the pure-number fast path (Risk R-19).
- Allowed functions: `abs round min max sqrt ceil floor pi`. The evaluator is a sandboxed Python `eval` (Risk R-10).
- Body variables **beat** global variables of the same name; `{Waste}` is the canonical global.
- **The user cannot type a quantity.** Quantity is always derived. The only current lever is a permanent formula edit. **The new UI makes quantity directly editable (brief Part 11) — treated as a per-costing quantity override, leaving the formula as the default** [RATIFIED direction; mechanics = new CA design + OQ-03].

## 12. Pricing Logic

[FACT] Unit-price precedence per row (`calculator.py:506-519`):

```text
1 skin_formula_id     -> recipe SUM(price x qty_per_m2)     (region: standard | kzn | sap)
2 taping_block_id     -> recipe SUM(m2 x price x qty)
3 floor_plate_id      -> recipe SUM + ordered x / division op-chain
4 mounting_cleat_id   -> recipe SUM
5 unit_price_override -> per-row permanent price
6 material.price_per_unit
THEN: quote-only override (session) WINS over all — reason >= 5 chars mandatory
```

- Recipe region rules: `"sap"` prices every ingredient at SAP last-purchase; a per-ingredient `price_source="sap"` overrides in any region; else KZN column for region kzn, standard otherwise.
- Price-age badges: updated ≤ 7 days (`Price updated {date}`), outdated ≥ 90 days, bulk-updated ≤ 30 days — all suppressed when a quote override exists.
- **Unpriced material ⇒ R0, silently** (Risk R-20).
- Price maintenance surfaces today (the pain): quote override → section override (`costings.price_master_edit`) → material price (`menu.materials`) → recipe ingredient prices (`recipes.edit_inline`) → SAP price sync. Five surfaces for one concept. Part 24 collapses the *experience* to "edit the price where you see it, choose scope" without touching the precedence chain.

## 13. Calculation Logic

[FACT] Money pipeline:

```text
materials_total = SUM category_totals              (server, banker's rounding)
+ chassis.subtotal (if enabled)                    -> grand_total  (NOTE: includes chassis)
+ margin  = grand_total x margin%                  (only if margin > 0)
/ ratio   (a DIVISOR 0.30–0.70, steps 0.025; default 0.55)
          selling_price = (grand_total + margin) / ratio
- discount (percent clamped 0–100 | amount clamped <= total)
          net_total = base - discount              (always set)
```

Two structural quirks the new CA must not accidentally "fix" into a behaviour change:
1. **Live vs save asymmetry**: on live recalcs, ratio and discount are applied **client-side only**; the server computes them **only at save** (`/api/approve`). The edit-balance verifier exists because of this. New UI: compute everything in one place (server) — flagged as a behavioural improvement, not a silent change (Part 24). [FACT + PROPOSAL]
2. **Rounding convention**: the app rounds half-to-even (banker's); Excel rounds half-up. The audit tool quantifies the difference as "rounding drift" rather than hiding it. Any new implementation must keep a single declared convention and keep the drift concept in the audit. [FACT]

Chassis: tyres/rims per axle (2 super-single / 4 dual) × (axles + lift axles); suspension & brake kits × axles; lifting axle only when lift_count > 0 (3-axle only in the UI); constants = `qty_per_metre × length + qty_constant`, skipped when ≤ 0. `cost_per_sqm = grand_total(pre-chassis) / floor_area`.

---

## 14. Business Rules Catalogue

Every rule the investigation identified, in the brief's format. **None may be lost in the redesign** unless explicitly retired here or in Part 31. Each entry: Condition → Action → User impact → Example → Dependencies → Source. All [FACT] unless marked.

### 14.1 Calculation engine — RULE-CALC

**RULE-CALC-001 · Quantity pipeline.** IF a BOM row survives inclusion gating THEN `qty = eval(formula) × section_multiplier × (1 + waste%/100)`, `line = qty × price`. *Impact:* every visible number. *Example:* `wall_area * 1.05` on a 13.6×2.5×2.7 body, SIDES ×2, waste 5% → qty = 73.44×1.05×2×1.05. *Deps:* geometry vars, section multiplier, waste. `formula_engine.py:176-180`.

**RULE-CALC-002 · Empty formula = 1.** IF `formula_expression` is empty THEN qty is 1.0 — an unconfigured row costs one unit, not zero. `formula_engine.py:67-100`.

**RULE-CALC-003 · Negative clamp (with a hole).** Formula results clamp to ≥ 0 — EXCEPT when the expression simplifies to a pure number, which returns as-is (literal `-5` → −5). [FACT; hole = Risk R-19] `formula_engine.py:87-96`.

**RULE-CALC-004 · Token resolution order.** `{TOKEN}` resolves: body variable (case-insensitive) → formula library (recursive, cycle-guarded → `(0)` on a cycle) → unknown = `(0)` + row flagged `formula_error`. *Impact:* red "⚠ Calculation Error" naming the unknown token; **the line still costs the zero-substituted result.** `formula_engine.py:20-64`.

**RULE-CALC-005 · Body vars beat globals.** `merged = {**global_variables, **body_variables}` — a body variable named like a global wins. *Example:* a body-level `{Waste}` would shadow the global. `formula_engine.py:159`.

**RULE-CALC-006 · Body variables are selection-independent.** ALL `is_body_option` rows with non-NULL `variable_value` feed the formula context, selected or not — the reason unselected insulation sides must be zeroed (RULE-INS-002). `calculator.py:181-192`.

**RULE-CALC-007 · Geometry variables.** `length/width/height` (not L/W/H), thicknesses, `num_doors` (engine default 1, client sends 2 — R-09), `num_axles` (2), and derived areas: `wall_area = length×height×2`, `roof_area = floor_area = length×width`, `front_rear_area = width×height×2`, `surface_area` = all four, `total_panel_area` = surface minus floor, `volume`. `formula_engine.py:103-138`.

**RULE-CALC-008 · Excluded rows still compute.** A soft-excluded row shows its real quantity with cost forced to 0 and is omitted from category totals. `formula_engine.py:194,202-203`.

**RULE-CALC-009 · Banker's rounding.** All server rounding is Python `round()` (half-to-even). Excel uses half-up. The audit quantifies the difference per line ("rounding drift", cap R0.05/line) and per workbook. `formula_engine.py` throughout; `help/reconcile.py:468-534`.

**RULE-CALC-010 · Category totals are unrounded sums.** Category totals accumulate unrounded line costs (rounded once at output); items round individually — a section header subtotal (client-side, from rounded lines) can differ by cents from the summary panel. [FACT; flagged unintentional = R-01] `formula_engine.py:194 vs 203`.

**RULE-CALC-011 · cost/m².** `grand_total(pre-chassis) / floor_area` (guarded `or 1`). `formula_engine.py:206-207`.

**RULE-CALC-012 · Chassis is inside grand_total.** When enabled, `grand_total += chassis.subtotal` — so drift verdicts (RULE-REF-05) see chassis changes. `calculator.py:614-619`.

**RULE-CALC-013 · Chassis quantities.** Tyres/rims = (axles + lifts) × (2 if super-single else 4); suspension & brake kits × axles; lifting axle only when lifts > 0 (UI: 3-axle only); constants `qty_per_metre × length + qty_constant`, skipped ≤ 0. `services/__init__.py:493-543`.

**RULE-CALC-014 · Recipe pricing.** Skin formula: Σ(ingredient price × qty/m²), region standard/kzn/sap (sap = last-purchase price per ingredient; per-ingredient `price_source="sap"` overrides any region). Taping/cleat: Σ(m² × price × qty), qty 0 skipped. Floor plate: Σ then an ordered ×/÷ op-chain (`[{"op":"/","val":12},...]`; only × and ÷; val 0 skipped; errors return raw). `services/__init__.py:250-417`.

**RULE-CALC-015 · Live vs save asymmetry.** `/api/calculate` never receives ratio or discount (client-side display); `/api/approve` receives and stores both. Two code paths must agree by construction; `verifyEditBalance` exists because of it. [FACT; the new UI should unify — Part 24] `calculator.js:5052-5065` vs `5213-5223`.

**RULE-CALC-016 · Cache-window divergence.** `/api/calculate` reads a 30 s-TTL cached formula library/globals; `/api/approve` queries the DB — a formula change can make preview ≠ saved for up to 30 s. [FACT; R-07] `calculator.py:731-732 vs 886-888`.

### 14.2 Insulation — RULE-INS

**RULE-INS-001 · Pair identity is structural.** A pair = exactly 2 body-option rows sharing group+subgroup, one name containing `EPS`, one `PU`. Name-substring matching is the only discriminator (R-14). `calculator.js:441-451`; server mirror `calculator.py:84-92`.

**RULE-INS-002 · The checked radio owns the thickness.** IF exactly one side is selected and the invariant is violated THEN the value moves to the selected side, the other becomes 0, both persisted to the TEMPLATE (`PUT /api/bom`). Toast: "Insulation thickness moved… · Body Template updated". Runs at every render, re-entry-guarded. `calculator.js:4427-4486`.

**RULE-INS-003 · Copy-on-switch.** Selecting the other side copies the thickness across and zeroes the source; both-NULL pairs are left alone; a quoted rear door with nothing anywhere gets 0.06. Mirrored into edit pins. `calculator.js:642-680`.

**RULE-INS-004 · Switch-ALL modal.** Flipping one pair offers to flip every INSULATION pair to the same type (name-substring matched — R-14). `calculator.js:739-814`.

**RULE-INS-005 · Both-zero warning.** A rendered pair with both sides ≤ 0 shows red values + "⚠ Both X and Y can't be zero" — suppressed for a non-selected rear door. Display-only. `calculator.js:685-736`.

**RULE-INS-006 · Manual thickness edit hits the template.** Inline edit → `PUT /api/bom/{id}` → toast + persistent TEMPLATE UPDATED badge; any logged-in user may write `variable_value` (the one open field on that endpoint). `calculator.js:817-892`; `trailers.py:319-320`.

**RULE-INS-007 · Edit pinning.** Inside an edit/recall, `body_variable_overrides` (keyed by material name) ride every recompute so the saved quote's thicknesses reproduce even after template drift; a deliberate in-edit flip updates the pin. `calculator.py:195-207`; `calculator.js:453-465`.

**RULE-INS-008 · Flip releases stuck exclusions.** Flipping a pair clears the pair's section rows from the optional-row-exclusion store (not in OPTIONAL sections; not in edit-replay). `calculator.js:617-637`.

### 14.3 Rear doors — RULE-DOOR

**RULE-DOOR-001 · Either DRD or SRD, never both.** One rear-door thickness follows the choice. `calculator.js:467-474`.

**RULE-DOOR-002 · Only `{SRD *}` tokens exist in formulas.** A DRD quote (SRD zeroed) deducts no rear-door insulation; an SRD quote does. Intended costing behaviour. `calculator.js:467-474`.

**RULE-DOOR-003 · Carry on click.** Switching door type carries thickness AND side (EPS stays EPS) onto the new door, zeroes the old door completely, persists all four cells, pins them. Keyed off the door-type SELECTOR with gate fallback. Default 0.06. `calculator.js:519-548`.

**RULE-DOOR-004 · Heal on render.** A selected door at 0/0 (pair not NULL/NULL) gets the carry re-run from the other door. `calculator.js:4501-4520`.

**RULE-DOOR-005 · Zero the inactive door on load.** On BOM load, every non-selected door group's EPS+PU are forced 0 (template write). Ambiguous selection → no-op ("never guess"). Edit pins deliberately untouched. `calculator.js:559-580`.

**RULE-DOOR-006 · Door off = zero both cells.** Toggling a door group off clears its selections and zeroes its pair "so it neither warns nor leaks a deduction". `calculator.js:380-394`.

**RULE-DOOR-007 · NO REAR DOORS + side doors.** Including a SIDE DOOR extra while a rear door is quoted AND the body has an (unchecked) NO REAR DOORS control → modal offering to remove the rear doors. NO REAR DOORS checked with no side-door extra → amber warn-but-allow "No doors quoted". `calculator.js:7780-7827`.

**RULE-DOOR-008 · Doors resolve for display from saved data.** The results page derives selected side and active door from saved selections, falling back to "the non-zero side was quoted" for legacy records. [INFERENCE fallback can mislabel old records — R-16] `calculator.py:54-152`.

### 14.4 Sections & categories — RULE-SEC

**RULE-SEC-001 · OPTIONAL prefix.** A section is optional if flagged OR named starting `OPTIONAL` (trimmed, upper-cased, PREFIX only). Read-time derivation; the flag is never auto-written. `services/__init__.py:57-63`.

**RULE-SEC-002 · Optional gate.** Optional section not enabled → soft-exclude "Optional section not enabled". A NULL-`bom_section_id` row in an optional-named section can NEVER be enabled (R-13). `calculator.py:533-536`.

**RULE-SEC-003 · Optional state is per-browser.** Enabled sections + per-row exclusions live in localStorage per body type; partial states are deliberate (disabling a section excludes each row so one re-tick = one row). `optional_sections.js`.

**RULE-SEC-004 · excluded_categories is a hard drop.** Rows in an excluded category never enter the response. Populated from radio siblings, masterless tickboxes, and off folders — by section NAME. `calculator.py:504`; `calculator.js:4886-4995`.

**RULE-SEC-005 · Radio categories.** Draft categories with `selectionMode='radio'` group by parent; every non-selected sibling's category is excluded. Owner masters resolve by section name (rename-safe) UNION material name (legacy). `calculator.js:4923-4948`.

**RULE-SEC-006 · v2 gating chain.** For `configurator_v2` bodies: archived sections skip; a section's `body_option_master_id` (resolved BY NAME locally) must be selected; per-item `bom_conditions` soft-exclude with a human reason; master rows are dropped entirely; the legacy DRD/SRD-prefix and `body_option_linked` gates are SKIPPED (no double filtering). `calculator.py:415-490`.

**RULE-SEC-007 · bom_conditions shapes.** include_when list (AND), `{"mode":"exclude","all":[...]}` (AND→negate), `{"mode":"always_exclude"}`; `equals` defaults "Y"; malformed JSON fails SAFE to include. Reason chips like `excluded · FRONT PU = Y`. `calculator.py:210-253`.

**RULE-SEC-008 · Legacy DRD/SRD section prefix filter.** Non-v2: a row in a section starting `DRD`/`SRD` drops unless that group is selected, regardless of per-line links (both gates must pass). `calculator.py:466-474`.

**RULE-SEC-009 · Legacy per-item link gate.** `body_option_linked_id` (by material id) else `body_option_linked` (by name against selected options/groups); no match → drop. `calculator.py:481-489`.

**RULE-SEC-010 · Section multiplier resolution.** By `bom_section_id` first, then section name, default 1.0. Echoed as `category_multipliers` only when ≠ 1 → red `× N` badge; admin single-side toggle is display-only. `calculator.py:520-522`; `calculator.js:5787-5881`.

**RULE-SEC-011 · flag_overrides alias union.** Each draft flag contributes label + binding name + bound material name as aliases; an alias once true never downgrades; server merges every truthy name so conditions written against any alias resolve. `calculator.js:4997-5036`; `calculator.py:291-294`.

**RULE-SEC-012 · Hidden-row eye.** Soft-excluded rows render only when the per-section eye toggle is on — EXCEPT optional-section rows, which always render (they carry the tick). Exports strip excluded items. `calculator.js:5276-5554`; `services/__init__.py:154-168`.

### 14.5 Pricing — RULE-PRICE

**RULE-PRICE-001 · Precedence.** skin → taping → floor plate → cleat → row `unit_price_override` → `material.price_per_unit`; a session quote-override beats everything. `calculator.py:506-519`.

**RULE-PRICE-002 · Quote override needs a reason.** ≥ 5 chars, ≤ 500; price ≥ 0; setting the original price back clears the override (no reason needed). Stored on the result by bom-id AND material-name with reasons. Red cell + `*` + tooltip. `calculator.js:1939-1968`; `calculator.py:899-903`.

**RULE-PRICE-003 · Permanent price is per-ROW.** `costings.price_master_edit` gates a price-only `PUT /api/bom/{id}` (the same material in another section is unaffected); saving clears the session override so the new permanent price shows; computed-price rows are read-only here. `calculator.js:1364-1393`; `trailers.py:321-326`.

**RULE-PRICE-004 · Price-age badges.** ≤ 7 days "Price updated"; ≥ 90 days "Outdated price"; bulk note ≤ 30 days; all suppressed under a quote override. `calculator.js:1000-1024,1562-1567`.

**RULE-PRICE-005 · Zero price is silent.** Unpriced material → R0 line, no flag (R-20; five perennial OPTIONAL EXTRAS materials on prod). `formula_engine.py:166`.

**RULE-PRICE-006 · Bulk updates are capped and journalled.** ±50% cap, price_history + last_bulk note, undo; BOM overrides prompted separately (protect_overrides bodies excluded); single permanent saves journal their own 1-row batch. `materials.py`; `trailers.py:364-372`.

### 14.6 Money — RULE-MONEY

**RULE-MONEY-001 · Margin.** `profit = round(grand_total × margin%, 2)` only when margin > 0; seeded from the body's markup. `calculator.py:623-628`.

**RULE-MONEY-002 · Ratio is a divisor.** Valid (0,1]; UI options 0.30–0.70 step 0.025; `selling = (grand_total + margin) / ratio`; label "55%"; `selling_price` stored only if margin > 0 or ratio applied. Default 55% on NEW costings only (edit/copy restore theirs). `calculator.py:632-649`; `calculator.js:2456-2459`.

**RULE-MONEY-003 · Discount.** Percent clamped 0–100 of base (selling else grand); amount clamped ≤ base; net always = base − discount; entering one input clears the other; persisted to dedicated columns AND result_json (columns win on read). `calculator.py:654-677,956-959,1365-1368`.

**RULE-MONEY-004 · List headline totals.** `net_total → result.net_total → selling_price → grand_total`; both headline totals NULL without `bom.view_full_cost`. `calculator.py:1150-1198`.

**RULE-MONEY-005 · Multi-ratio exports.** Each selected ratio gets its own full recompute (never combined); with ≥ 2 ratios no discount rows; with exactly 1, discount rows only when it equals the saved ratio. `services/document_context.py:85-166`.

### 14.7 Saving & versioning — RULE-SAVE

**RULE-SAVE-001 · Duplicate detection.** Same customer + body + SAME quote type (repair vs normal have independent revision sequences; legacy NULL = normal). Modal offers save-as-new / revision / REPLACE. [FACT; the client's check-duplicate call omits is_repair — R-03] `calculator.py:762-811`; `calculator.js:5162`.

**RULE-SAVE-002 · Version actions.** `overwrite` (pending only, 409 otherwise; keeps id/qno/version; never touches the counter) · `new_version` (next rev) · `save_as_new` (v1, race-guard skipped by design) · `replace` (BULK-DELETES all matching records — cascades validated references away, R-05) · default v1 with a 409 race guard. Process-local lock only (R-06). `calculator.py:934-1004`.

**RULE-SAVE-003 · Quote numbers.** Global counter, template `{user_initial}{counter}/{month}/{year}` (placeholders safe-defaulted; `{counter}` mandatory); assignment idempotent, numbers immutable; reuse only on `new_version` (edit modal defaults reuse ON, duplicate modal OFF); assignment failure is swallowed → a record can save with NULL quote number (R-04). `quote_numbering.py`; `calculator.py:1022-1047`.

**RULE-SAVE-004 · Contact snapshot.** Saving 422s fast if the contact doesn't belong to the customer or is inactive; contact fields freeze at write time (deprecate-not-drop). `calculator.py:816-851`.

**RULE-SAVE-005 · input_state + ui_snapshot.** Everything needed to re-hydrate rides INSIDE result_json (overrides+reasons, selections, exclusions, optional sections, margin, is_repair, ratio, chassis, ui_snapshot — the latter NULL in replay edits, keyed by bom-row-id for body vars vs material-name in result.body_variables). `calculator.py:909-927`; `calculator.js:2559-2585`.

**RULE-SAVE-006 · Status flow.** pending → accepted (idempotent) / declined (reason REQUIRED, min 5 in UI); delete is admin-only (dashboard right-click); repair quotes read as "Repair" once accepted+. `calculator.py:1229-1292,1174-1184`.

### 14.8 Edit & copy — RULE-EDIT

**RULE-EDIT-001 · Copy (`?from=`).** Dims/margin/customer/selections/ratio restore; price overrides, optional sections, chassis, discount DO NOT; record id cleared. "A copied quote always starts with clean prices." `calculator.js:2226-2251`.

**RULE-EDIT-002 · Edit (`?edit=`) hydration order is load-bearing.** Inject inactive body if needed → non-pending degrades to copy (toast) → pre-seed localStorage BEFORE loadBOM (preserveInputs) → hard-restore draft stores AFTER → pin body vars → snapshot? else build replay → discount/overrides/ratio/chassis/optional sections → render → runCalc → verify balance. `calculator.js:2278-2407`.

**RULE-EDIT-003 · Replay mode (legacy records).** No ui_snapshot → force-include exactly the saved lines (`include_all_items` + saved formulas + saved prices as baseline), bypassing all gating. Survives template drift by construction. `calculator.js:2532-2554,5070-5079`.

**RULE-EDIT-004 · Balance gate.** After edit load, derived selling AND manufacturing totals are compared to saved (tolerance R1.00). Balanced → green tick. Drift → THE SAVED FIGURES ARE DISPLAYED with an amber explanation; the next edit switches to current numbers. `calculator.js:2593-2635`.

**RULE-EDIT-005 · Post-save exit.** A successful edit save drops edit mode and scrubs `?edit=` — the next save is a normal duplicate/version flow. `calculator.js:5237-5250`.

**RULE-EDIT-006 · Body-switch reset.** A non-preserving body switch clears record binding, overrides, selections, discount, edit state; v2 bodies also skip localStorage restore (always start from configurator defaults). `calculator.js:2811-2842`.

**RULE-EDIT-007 · Return-trip state.** Jumping to the Materials editor arms a 30-min one-shot sessionStorage snapshot (trailer+user matched) restoring the full costing state on return; a mismatched shared last-session is discarded rather than trusted. `calculator.js:1063-1207`.

**RULE-EDIT-008 · The 700 ms debounce.** Every input schedules recalc through one 700 ms timer; the approve button is only disabled once the timer fires — approving inside the window saves the PREVIOUS calc's payload (fixed in CI by waiting for idle; the UI hazard remains — R-11). `calculator.js:2035-2038,5082`.

### 14.9 Validated references — RULE-REF

**RULE-REF-001 · Identity (fingerprint) contents.** IN: body type, dims (L/W/H, 3 dp), selected body options, excluded categories, truthy flags, ALL body variables (3 dp). OUT (ratified): price overrides, margin, ratio, discount, customer, chassis, optional extras + user row-excludes (localStorage-resident; their cost surfaces as drift instead). `services/validated_references.py:101-143`.

**RULE-REF-002 · Marking guards.** Needs `costings.validated_refs_manage` + a computed result + a SERVER-verified bound record of the same body type with dims matching the screen (±0.0005). Refusals open Save-first naming the actual reason (dims moved / different body / unsaved). Pre-v1.39.9 records 409 ("re-save it"). Re-marking relabels (idempotent). `calculator.js:6269-6367`; `routers/validated_references.py:124-187`.

**RULE-REF-003 · Recall is a copy.** Full hydration (like edit) but NEVER sets edit bindings — a reference's record cannot be overwritten from recall. Overrides restore so the recalled load balances. `calculator.js:6156-6246`.

**RULE-REF-004 · Drift basis.** Pre-margin/ratio/discount manufacturing total (= grand_total, which INCLUDES chassis — RULE-CALC-012). Tolerance = admin setting, default 2%. Zero-total reference matches quietly. Top-3 category deltas, vanished/appeared categories included. `services/validated_references.py:174-227`.

**RULE-REF-005 · Banner is display-only.** Recomputed after every calc; sequence-guarded against out-of-order replies; any failure clears it; never blocks, never writes. `calculator.js:6376-6424`.

**RULE-REF-006 · Retire is soft.** `active=false`, kept for audit; stops matching and leaves the dropdown (dropdown hidden entirely at zero refs). Reading/recall needs NO permission. `routers/validated_references.py:226-241`.

### 14.10 Special rules — RULE-SPEC

**RULE-SPEC-001 · The 3.2 m plywood+glue rule.** IF body ∈ {CHILLER MEDIUM, FREEZER MEDIUM} AND length is literally 3.2 THEN the 4MM PF PLYWOOD row and its adjacent GLUE LINE in FRONT and SIDES cost R0 — rows stay visible at qty 0. Implemented as DATA (a `(0 if abs(length-3.2)<1e-9 else 1)` guard appended to 8 formulas by an idempotent, fail-loud script); detection is regex-based on the formula text + pinned length, mirrored server/client; red banner + bold-red lines + one line in every export. 3.19/3.21 cost normally. `docs/rules/32m-plywood-glue-zero.md`; `scripts/rules/apply_32m_plywood_glue_zero.py`; `services/__init__.py:176-206`.

**RULE-SPEC-002 · RICE GRAIN ⇄ KICKPLATES.** Ticking an option whose name contains RICE GRAIN auto-selects the option containing 1ST ROW + KICK (and un-ticks with it); removing kickplates while rice-grain is on warns (does not block). The ONLY hardcoded material-name coupling (R-15). `calculator.js:949-999`.

**RULE-SPEC-003 · Excel paste.** TSV paste recognises dims (first numeric wins; 0<v≤100), EPS/PU pairs (Y side wins; both-Y = group skipped; 0 thickness = keep current; ≥1 m rejected), door follows the pair Y (both = both door groups skipped), mutex subgroups (exactly one Y), independent ticks; everything else becomes a "skipped" chip; applies through the SAME primitives as manual clicks. Duplicate labels: last wins. `calculator.js:7343-7770`.

### 14.11 Access — RULE-PERM

**RULE-PERM-001 · Grants (dev DB verified 17 Aug 2026 = seed defaults).** `costings.price_master_edit` {admin, full} · `costings.validated_refs_manage` {admin, full} · `bom.view_prices` / `bom.view_full_cost` {admin, full} (price masking `••••`; view_prices also gates the entire Excel-audit feature) · `export.*` {admin, full} · `quote.generate` {admin, full, user} · `menu.materials` {admin, full} · `menu.body_templates` / `menu.pricing_formulas` / `recipes.edit_inline` {admin}. `role == 'admin'` is a code-level wildcard.

**RULE-PERM-002 · menu.calculator is catalogued but unenforced.** The calculator routes check login only; the key gates nothing except an AI-help tool. [FACT — verified 17 Aug 2026] `calculator.py:157-176`; `help/tools.py:354`.

**RULE-PERM-003 · React shell is permissive by design.** Only `costings.validated_refs_manage` is server-checked in the shell; other `costings.*` keys default open in live mode — real enforcement is on the API endpoints. `frontend/src/store/AppDataContext.tsx:29-44,184-194`.

---

## 15. Excel Relationship

### 15.1 The workbook model the app mirrors [FACT — live sheet verified 17 Aug 2026]

Sheet ` UP TO 4.8 MT FREEZER  (2` (FREEZER MEDIUM), verified cell-by-cell:

```text
E1        = "FREEZER"                     (trailer-type hint)
A4:A6     = LENGTH / WIDTH / HEIGHT       values in C4:C6  (6.5 / 2.5 / 2.5)
G5        = 0.05                          (markup 5%)
G8        = 0.6                           (ratio chip)
A8+ col A = body options (FRONT EPS, ...) with Y/N in column D
col B     = section labels: FRONT, SRD, DOOR FITTINGS, DRD, DOOR FITTINGS,
            SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY
row 228   = GRAND TOTAL:  =SUM(J40:J226)  (totals column J)

A typical item row (r30):
  D = '=C5-C14-C15-C14-C15+0.05'   width minus thickness cells
  E = '=C6-C16-C17-C18+0.05'       height minus thickness cells
  F = '=D30*E30'                   area (the qty)
  G = "='[1]RESINS + ADESIVES'!$D$37"   price from PRICE 2017 MARCH
  H = '=G30*F30'                   line total
  I = '=IF(D8="Y",1,0)'            body-option gate reading FRONT EPS's Y/N
```

Every app concept is visible in that row: geometry-derived quantity (→ `formula_expression`), external price reference (→ `materials.price_per_unit` / recipe FKs), the Y/N gate (→ `body_option_linked` / `bom_conditions`), the flag column (→ import's disabled-row logic), duplicated DOOR FITTINGS after SRD and DRD (→ the importer's `SRD/DRD DOOR FITTINGS` renaming).

**CHASSIS COSTINGS is a different shape** — Y/N flags in column B, ratio-divisor rows (`=I4/0.65`), LENGTH at C3/C5. It became the app's separate chassis engine, not an imported body. The `=I4/H8` division rows are the Excel origin of the app's **ratio-as-divisor** selling-price concept. [INFERENCE from structure]

### 15.2 How the app consumes workbooks — three import paths + two live tools [FACT]

| Path | Surface | Notes |
|---|---|---|
| A · Sheet import | `/admin/import` | The main flow. Parses E1/dims/G5/G8:G18, col-B sections, per-section column sniff (QTY layouts vs area layouts), totals col detection (J standard; "wide" SRD/DRD-variant sheets shift right), flag col 0/1, multiplier extraction from `=SUM(...)*2`, price-formula re-evaluation INCLUDING opening FORMULAS 2018.xls for external refs, symbolic quantity-formula translation (price factored out) |
| B · GRP import | `/admin/import/grp` | Richer: body-options block (name/C=Y-N/D=qty), section master gates from the TOTAL row's `=IF(C<n>="Y",1,0)`, per-line gates, recipe-FK linking via the FORMULAS-2018 cell map |
| C · Template-page import | Body Templates modal | Dev-only in practice (server-side file path; trusts client-parsed data) |
| Formula scan | `/admin/templates/formula-scan` | Chases price cells through refs to decide which resolve into FORMULAS 2018; proposes recipe-FK links from a HARDCODED cell map (FORMULA SKINS D13/D25/D37/D49/D59; TAPING BLOCKS F11/F24/F37/F47/F61/F74; MOUNTING CLEATS F10/F22/F39; SRD FLOOR PLATE F13/F24/F35/F43); `unknown_ref` proposals are never auto-applied |
| Excel audit | AI-help panel | Reuses the Path-A parser; drops sections with ~0 totals (unselected variants are CORRECT absences); FIFO name-matching; per-line cause classification: match / price / formula / **rounding** (half-up vs banker's, proven per line) / unexplained; roll-ups per section + workbook |

**[FACT — defect]** The on-screen import guide and the downloadable synthetic sample claim the item name lives in column C. **Every parser reads column A.** A sheet built to the guide imports zero items. (On machines holding the real workbook the sample download copies a real EXAMPLE sheet, hiding the mismatch.) → Risk R-22.

### 15.3 Uncertainties (explicitly flagged, per the brief)

- The freezer sheet's `$H$29` price reference points at a second price area on the RESINS sheet whose semantics were not decoded (first reference `$D$37` = the PRICE column). **Do not assume**; resolve when porting that sheet's data. [UNCERTAIN]
- `PRICE 20.04.2004.xls` (29 live references, mostly TAUT LINER RIGID) is absent from the provided folder — those cells resolve from Excel's cached values. Which prices those are, and whether they are still commercially valid, is OQ-14. [UNCERTAIN]
- Wide-sheet (SRD/DRD variant column) detection warns but the exact per-sheet column shifts were only spot-verified. [UNCERTAIN]

## 16. Formula Dependencies

[FACT] Resolution graph at calculation time:

```text
BOM formula_expression
 ├─ geometry vars        <- dims + hidden thickness inputs
 ├─ {BODY VARIABLE}      <- ALL body-option variable_values (selection-independent)
 │     └─ overridden by edit pins (body_variable_overrides)
 ├─ {Formula Library}    <- admin formulas (recursive, cycle -> 0)
 └─ {Global Variable}    <- e.g. {Waste} (loses to a same-named body var)
Price side:
 unit price <- recipe engines (skin/taping/floor/cleat <- ingredient prices <- SAP last-purchase via sync)
            <- row override <- material price <- quote override
```

Fragilities the new design must respect (all [FACT], from the risk register): fingerprints embed ALL body variables (a template thickness edit invalidates old references, R-17); section renames break `excluded_categories` matching; material renames break flag aliases; client tooltips re-implement recipe maths and can drift (R-18).

## 17. User Permissions / Controls

See RULE-PERM-001..003. Summary for the new CA: two costing-specific keys exist (`price_master_edit`, `validated_refs_manage`); price VISIBILITY is `bom.view_prices`/`view_full_cost` (mask `••••`); exports and quote generation have their own keys; everything structural is admin. The dev DB's live grants exactly match the seed defaults [FACT, 17 Aug 2026]. The new UI keeps this model; any new capability (free-hand lines, repair costings, quantity overrides) needs new keys following the same pattern (Part 24).

## 18. Validation Rules

[FACT] Client-side: dims > 0 (length ≥ 0.01, thicknesses ≥ 0.001) — field-level red errors block calculation; margin 0–100; discount clamps mirrored client/server; override reason ≥ 5 chars; decline reason ≥ 5 chars; contact add requires a name; validated-reference label required, ≤ 120 chars. Server-side: contact-customer pairing (422), edit of non-pending (409 → degrade to copy), duplicate race guard (409), repair-phase scheduling requires `is_repair` (409), pre-v1.39.9 reference marking (409), quote-number template must contain `{counter}`.

## 19. Error Handling

[FACT] Formula errors: row shows `— err —` + red warning naming unknown tokens; section header aggregates a warning; THE LINE STILL COSTS the zero-substituted result. Unpriced materials: silent R0 (R-20). Calculation failure: toast "Calculation failed", approve stays disabled. Save conflicts: 409s with human messages (race, non-pending). Quote-number assignment failure: swallowed, record saves numberless (R-04). AI-audit sheet mismatch: explicit `sheet_not_found` with available sheets listed. Balance drift on edit: NEVER silent — the saved figures display with an amber explanation (RULE-EDIT-004).

## 20. Standard Costing Workflow (current)

Documented in Part 4. Key states: pending → accepted/declined → pre-job → planning (production side). Revisions per (customer, body, quote-type); quote numbers immutable; accepted repair quotes display as "Repair".

## 21. Repair Costing Workflow (current)

[FACT] What exists: `calculations.is_repair` (Calculator 2 tick only) → independent revision sequence → "Repair" status display → dashboard filter → planner writes `repair_phases_json` after acceptance (phase entry points for MES scheduling; requires `is_repair`). What does NOT exist: any repair costing model — no repair BOM, rates, labour, or free-form lines. A "repair costing" today is a full body-template costing with a badge; consequently **real repairs are quoted manually in Excel** (BA, 17 Aug 2026), and Calculator 2 — built to host the repair tick — was rejected by reality.

## 22. Current Pain Points

Ratified with the BA; each traces to facts above:

1. **Formula-mediated price/quantity maintenance** (the core complaint): changing a quantity means editing a token formula, permanently, per body type. Five separate surfaces to change a price.
2. **Template side-effects from costing gestures**: insulation/door choices write to the shared template mid-costing ("Body Template updated" toasts).
3. **Three body-option renderers** for one concept; radio/tickbox/folder semantics invisible to the user.
4. **Inverted controls**: checked = excluded on optional sections.
5. **Configuration spread**: Template page, Configurator (×2 pages), Formulas, 5 pricing pages — all upstream of a simple costing.
6. **Two calculators** with silently different capabilities (edit vs repair-tick).
7. **No free-hand items, no repairs, no stock view** — the gaps that keep Excel alive.
8. **Silent zeros**: unpriced lines and formula errors still "cost" — R0 leaks into quotes.

---

# PART II — THE NEW COSTING EXPERIENCE

## 23. New UI Principles [RATIFIED]

The new UI must NOT resemble the old application visually or structurally. It is a redesign of the **costing experience**, inspired by the directness of the Excel workbook — not a re-skin of the existing screens. It must be: simple, fast, visually clean, spreadsheet-like where appropriate, minimal-navigation, minimal-configuration, focused on the costing itself. Primary persona: **Nadie**. Most costing work happens on **one page**.

Anti-goals (from the design philosophy, Part 20 of the brief): do not copy the current page structure, navigation, configuration workflow or interaction model. The old system is the source of rules, calculations, data, body types and history — nothing else.

## 24. New Costing Page Requirements

```text
+----------------------------------------------------------------------+
| MATERIALS      + MARGIN       TOTAL (/ratio)      NET (after disc.)  |   <- always visible (Part 10 of brief)
+----------------------------------------------------------------------+
| [ Body type v ]  L [    ] W [    ] H [    ]   Margin [  ] Ratio [ v ] |
|----------------------------------------------------------------------|
| > CATEGORY: FRONT            [x include]           subtotal  R ---   |
|     Insulation: [ EPS v ] [ 60 mm v ]                                |
|     item rows: qty | unit | price | total   (edit in place)          |
| > CATEGORY: SIDES  (x2)      [x include]           subtotal  R ---   |
| > OPTIONAL EXTRAS            [ ] include           ...               |
|   + Add item  (stock search | free-hand)                             |
+----------------------------------------------------------------------+
| Customer [ v ]  Contact [ v ]   Discount [   ]   [ Save Costing ]    |
+----------------------------------------------------------------------+
```
*(Illustrative sketch only — layout is the new CA's to design.)*

Requirements (each traces to a ratified decision or the brief):

1. **Totals bar at top, all four stages** — Materials · +Margin · ÷Ratio=TOTAL · −Discount=NET — permission-masked exactly as today (RULE-PERM-001). [RATIFIED]
2. **Everything on one page**: body type, categories with include/exclude, insulation inside categories, items, quantities, prices, line/category/overall totals, stock picks, free-hand entry, add/remove item, customer+contact, save. [RATIFIED, brief Part 9]
3. **Category include/exclude**: any category, with a consequence warning (§6.3). Underlying gating (radio siblings, folder gates, masters) keeps operating and surfaces as visible state changes, not hidden rules. [RATIFIED]
4. **Editable quantity**: per-costing quantity override on any line; the formula remains the default and the UI shows which is in force (see value-provenance below). The formula editor stays available behind an affordance for power users, not in the main flow. [RATIFIED direction; OQ-03]
5. **Editable price where permitted**: one gesture, scope chosen at save ("this costing" needs a reason as today; "permanently" needs `costings.price_master_edit`) — collapsing today's five surfaces into one experience WITHOUT changing the precedence chain (RULE-PRICE-001..003). [RATIFIED direction]
6. **Value provenance must be visible** (brief Part 11): system-calculated vs computed-price (recipe) vs editable vs overridden vs stock-derived vs manually entered. Today's colour/badge conventions (override red + reason tooltip, computed-price engines, price-age badges, zero-rule red) carry forward in spirit.
7. **Add item, two methods** (brief Part 12): stock-list picker over `materials` (search by name/SAP code/category) and **free-hand entry** (description, qty, unit price — NEW capability; needs a new permission key and a decision on where free-hand lines land in the data model — OQ-04).
8. **Loud zeros**: unpriced or formula-error lines must be visually unmissable and never silently included at R0 (fixes R-20/RULE-CALC-004's sharp edge).
9. **One calculation authority**: live totals and saved totals computed by the same server path, eliminating the live/save asymmetry (RULE-CALC-015) and the debounce/stale-approve hazard (RULE-EDIT-008). Save must bind exactly what is on screen.
10. **No template writes from costing gestures** — insulation/door/thickness changes affect THIS costing; template updates become an explicit, separate act (OQ-02 for the exact semantics).
11. Preserved as-is: save/versioning flows and modals' SEMANTICS (RULE-SAVE-*), validated references (RULE-REF-*), Excel audit, chassis block, customer/contact snapshot, quote numbering, exports, accept/decline. The `replace` action must gain a real confirmation (R-05).

## 25. New Category Requirements

- Categories are the page's organising unit; order = today's `sort_order`.
- Include/exclude control per category (normal polarity: checked = included), with consequence warning on excluding non-optional categories. Optional (EXTRAS) categories default excluded, exactly as today's optionality rules define them (RULE-SEC-001..003).
- Multipliers (`× 2` SIDES) shown on the category header; totals behaviour unchanged (RULE-SEC-010).
- Radio-category groups render as a visible choice ("pick one of: …") rather than an invisible exclusion (RULE-SEC-005).
- Per-line include/exclude within any category (Calculator 2's model, generalised — the migration home for `calc2_default_excluded` seeding is OQ-05).

## 26. New Insulation Requirements

Per §7.4: type + thickness controls INSIDE each insulated category; one thickness per pair owned by the selected type; rear-door follows the DRD/SRD door choice; `{TOKEN}` linkage keeps resolving; "switch all categories to PU?" remains as an assist; both-zero impossible to save silently. Template-write semantics per OQ-02.

## 27. New Stock Requirements

Per §10.2: the stock list = `materials`, surfaced as a fast picker (name / SAP code / category / sub-category; show unit + current price + price age). Conceptual model is SAP-ready (Stock ID, Internal Item ID, Part Number, SAP Item Code, Description, Category, UoM, Cost Price, Selling Price, Active) — mapped onto existing columns, with `material_code` exposed and per-item Selling Price explicitly deferred (OQ-07). No availability/on-hand in scope.

## 28. SAP Future Integration Considerations

[FACT-grounded] Two SAP surfaces already exist: `sap_item_codes` (5,147 codes + last-purchase prices; feeds skin-formula ingredients via explicit sync) and the read-only `icb_sap` OWHS/OITM/OITW landing zone (ADR 0013; real stock columns; consumed by MES production, NOT costing; known −12%…+18% price divergence from costing prices per the v4.24 spike). Design constraints for the new CA: join by `sap_code` string (soft), never FK into `icb_sap` from costing; price-source policy (catalogue vs SAP last-purchase) is a BUSINESS decision (OQ-06) — build the seam, not the policy; keep ETL-refresh semantics in mind (OITM reloads truncate).

## 29. Free-Hand Item Requirements [NEW capability]

- Fields: description (required), quantity (required, > 0), unit price (required, ≥ 0), optional note. Line total = qty × price, entering the category the user adds it under (repairs: a flat list).
- Free-hand lines are per-costing data (inside the saved costing), NOT template rows and NOT materials — they must never leak into the body template or the catalogue. [PROPOSAL — model in OQ-04]
- Permission: new key (suggest `costings.freehand_items`), default {admin, full} like its siblings.
- Provenance: visually distinct from template lines ("manually entered").
- Excel-audit note: free-hand lines will appear as `only_in_live` when auditing against the workbook — acceptable; flagged for the audit's docs.

## 30. Repair Costing Requirements [RATIFIED — new capability]

```text
[ Costing type / body dropdown v ]
    ... 26 body types ...
    -----------------------------
    REPAIR
        v
Customer [ v ]   Type of repair [ ................ ]   <- recorded, required
Lines:  + from stock list   |   + free-hand
        description | qty | unit price | total
Totals: Materials -> (margin/ratio policy: OQ-08) -> TOTAL
Save -> normal costing lifecycle (quote number, accept/decline, revisions)
```

- Reached from the SAME dropdown as body types (one flow, not a second application — brief Part 13). [RATIFIED]
- No body template, no BOM, no dims/geometry: a flat line list from stock picks + free-hand entries. [RATIFIED]
- Records customer AND **type of repair** (new field — OQ-09 for whether free text or a maintained list). [RATIFIED]
- Keeps everything the `is_repair` flag already does: independent revision sequence per customer (RULE-SAVE-001 — and fixes R-03's client omission), "Repair" status display, dashboard filter, planner phase scheduling (`repair_phases_json`) downstream. [FACT-grounded]
- Margin/ratio/discount applicability for repairs = OQ-08 (Excel practice unknown).

## 31. Existing-to-New Function Mapping

Every significant function, its fate. "New location" = the one primary costing page unless noted. **Retained? No = requires the BA's explicit sign-off via this document.**

| Existing function | Current location | Current behaviour (rule refs) | New location | Retained? |
|---|---|---|---|---|
| Body type selection | Calc 1/2 dropdown | §5.3 | Costing page dropdown (+ REPAIR entry) | Yes |
| Default dims/margin/ratio seeding | Calc | §5.3, RULE-MONEY-002 | Same | Yes |
| Body options (3 renderers) | Calc panel | §3.1.1, RULE-SEC-* | ONE representation designed by new CA; same gating outcomes | Yes (logic) / No (renderers) |
| Insulation EPS/PU + thickness | Calc body-options panel | RULE-INS-* | Inside each category | Yes (semantics; template-write per OQ-02) |
| DRD/SRD door choice | Calc panel pills / folders | RULE-DOOR-* | Visible door choice on the costing page | Yes |
| Optional EXTRAS sections | Calc (checked=excluded) | RULE-SEC-001..003 | Category include control, normal polarity | Yes |
| Per-line excludes (all sections) | **Calculator 2 only** | §3.2 | Every line, any category | Yes — generalised |
| Repair flag | **Calculator 2 tick** | §21 | REPAIR costing type | Superseded (kept in data) |
| Calculator 2 itself | `/calculator2` | §3.2 | — | **No — eliminated [RATIFIED]** |
| Print / Full Report buttons | Calculator 2 | §3.2 | Costing page (print/report of current costing) | Yes — re-homed |
| Quantity change | permanent formula edit | §11 | Per-costing qty override; formula editor secondary | Yes + NEW override |
| Price change (quote) | ctx menu modal + reason | RULE-PRICE-002 | In-place edit, scope "this costing" | Yes |
| Price change (permanent) | section-price modal | RULE-PRICE-003 | Same gesture, scope "permanent" | Yes |
| Computed prices (4 recipe engines) | invisible + warning modals | RULE-CALC-014 | Same engines; provenance badge; edit via admin | Yes |
| Price-age badges | calc + results | RULE-PRICE-004 | Same | Yes |
| Chassis block | Calc chassis tab | RULE-CALC-013 | Costing page section | Yes |
| Customer + contact snapshot | Calc right panel | RULE-SAVE-004 | Costing page | Yes |
| Discount | summary panel | RULE-MONEY-003 | Totals bar area | Yes |
| Save / versioning / duplicate modals | Calc | RULE-SAVE-001..002 | Same semantics; `replace` gets real confirm | Yes |
| Quote numbering | on save | RULE-SAVE-003 | Unchanged | Yes |
| Edit a pending costing | Calc 1 `?edit=` | RULE-EDIT-002..005 | New page, same semantics incl. balance gate | Yes |
| Copy a costing | `?from=` | RULE-EDIT-001 | Same | Yes |
| Validated references | Calc 1 | RULE-REF-* | Costing page | Yes |
| Excel paste | Calc 1 | RULE-SPEC-003 | Keep (assist for transition) | Yes [PROPOSAL] |
| Excel audit (AI) | help panel | §15.2 | Keep | Yes |
| Exports / email / quote PDF | results + MES bridge | §3.5 | Keep; feed from new page | Yes |
| Accept / Decline / dashboards / pre-job | dashboard + React | RULE-SAVE-006 | Untouched downstream | Yes |
| 3.2 m rule, RICE GRAIN rule, zero-rule banner | data + calc | RULE-SPEC-001..002 | Same engine; same banners | Yes |
| Template authoring (body types, BOM rows, sections, links) | Body Templates | §3.3 | Admin surface OUTSIDE costing flow | Yes (relocated out of flow) |
| Configurator draft authoring | /admin/settings | §3.4 | Admin; its gating logic feeds the new category model | Yes (authoring UX out of scope) |
| Formula library + global vars | /admin/formulas | §16 | Admin | Yes |
| Materials admin + bulk prices | /admin/materials | RULE-PRICE-006 | Admin + surfaces as stock picker | Yes |
| Excel imports + formula scan | /admin/import* | §15.2 | Admin (fix R-22 guide mismatch) | Yes |
| Single-side view (admin × N toggle) | summary panel | RULE-SEC-010 | New CA's call | OQ-10 |
| AI help chat | floating panel | — | Keep | Yes |

## 32. User Journeys (target)

**Standard costing** [validated with BA]:
```text
Select Body Type -> page opens costed at defaults
  -> review categories (include/exclude; warnings on structural excludes)
  -> set insulation per category (type + thickness)
  -> adjust dims -> totals update
  -> edit quantities / prices in place (provenance visible)
  -> add stock items / free-hand items
  -> tick optional extras (loud if unpriced)
  -> customer + contact -> discount
  -> totals bar green across all four stages -> Save
  -> (optionally) Mark as validated reference
```

**Repair costing** [RATIFIED]:
```text
Select REPAIR -> customer + type of repair
  -> add stock items / free-hand items (qty x price)
  -> review total -> Save -> normal lifecycle (accept -> phases -> production)
```

**Price maintenance (Nadie)** [the pain, redesigned]:
```text
See an outdated-price badge on a line -> click price -> new value
  -> scope: this costing (reason) | permanent (permission)
  -> done, on the page. No admin navigation.
```

**Recall a validated baseline**:
```text
Body type -> "Validated references (N)" -> pick -> page loads as a copy that balances
  -> adjust -> drift banner quantifies any change vs the baseline
```

---

## 33. Data Model Requirements

### 33.1 What exists (keep) [FACT]

```text
trailer_types 1--* bill_of_materials *--1 materials *--1 material_categories
                   |                                 *--- price_history
                   *--1 bom_sections (multiplier, is_optional, v2 gates)
                   *--1 skin_formulas | taping_blocks | floor_plates | mounting_cleats
                            (recipes -> items -> ingredients -> sap_item_codes)
trailer_types 1--* calculations *--1 customers 1--* customer_contacts (snapshot cols on calculations)
calculations 1--* validated_references (thin pointer, soft retire)
calculations: dimensions_json, result_json{version, input_state{...}, ui_snapshot},
              status, quote_number, is_repair, repair_phases_json, discount cols, net_total
chassis_constants / chassis_options   ·   quote_counter   ·   formulas / global_variables
icb_sap.OWHS/OITM/OITW (read-only mock; no costing dependency)
```

Notable storage facts the new CA inherits: `version` and `ui_snapshot` live INSIDE `result_json` (no columns); body variables are stored under two different keys (material-name in `result.body_variables`, bom-row-id in `ui_snapshot.body_variables`); contact details are write-time snapshots; validated references copy nothing (pointer + fingerprint).

### 33.2 What the new experience adds [PROPOSAL — shapes for the new CA]

| Concept | Suggested shape | Why |
|---|---|---|
| Costing type | `calculations.costing_type` ('body' \| 'repair') derived from/alongside `is_repair` | repair as first-class; keeps `is_repair` readers working |
| Type of repair | new column (or structured field) on `calculations`; free text vs list = OQ-09 | ratified requirement |
| Free-hand lines | inside the saved costing's line data with `origin='freehand'` (description, qty, unit_price); NEVER template rows or materials | Part 29 |
| Quantity override | per-costing `{bom_id: qty}` map in `input_state`, mirroring price `overrides` | Part 24.4; same replay/edit semantics |
| Line origin/provenance | per-line `origin`: template \| stock-pick \| freehand (+ existing override flags) | Part 24.6 |
| Category include state | per-costing record of include/exclude decisions (today scattered across localStorage + draft states) — costings must re-open on ANY browser | fixes the localStorage fragility that broke reference matching |
| Stock picker fields | expose `materials.material_code`; optional per-item selling price = OQ-07 | Part 27 |
| New permission keys | `costings.freehand_items`, `costings.qty_override` (naming per convention) | Part 17 |

**Migration constraint:** existing saved costings (result_json shapes, replay edits, validated references' fingerprints) must remain readable and re-openable. The fingerprint definition (RULE-REF-001) may NOT change silently — if category-include state moves out of localStorage into the costing, the extras-excluded-from-identity decision should be revisited WITH the BA (it existed only because of localStorage).

## 34. Open Questions

| # | Question | Owner |
|---|---|---|
| OQ-01 | **v4.37**: build the new UI on the parked native React calculator (parity re-skin, ~1,850 lines, ADR 0031) or start fresh and mine it for plumbing? This spec deliberately documents the current system, not v4.37's partial port | BA + new CA |
| OQ-02 | **Template-write semantics**: today insulation/door/thickness gestures write the SHARED template mid-costing. Proposed: per-costing values + explicit "save to template". Confirm, and define who may save to template | BA |
| OQ-03 | **Quantity override mechanics**: does an overridden quantity survive a recalc after dimension changes (sticky) or reset (derived wins)? Suggest sticky-with-badge + one-click revert | BA + new CA |
| OQ-04 | **Free-hand line storage**: confirm lines live inside the costing only (no material creation), and whether they can be "promoted" to the catalogue by an admin later | BA |
| OQ-05 | **`calc2_default_excluded` seeds**: Calculator 2's per-body default exclusions — migrate into the new per-line model, or retire the flag? | BA |
| OQ-06 | **Price source policy** once SAP is real: catalogue price vs SAP last-purchase (known −12%…+18% divergence). Build the seam now, decide policy later | BA (later) |
| OQ-07 | **Per-item selling price** in the stock model: wanted, or does selling stay costing-level (÷ratio)? | BA |
| OQ-08 | **Repairs and money**: do margin/ratio/discount apply to repair costings, and at what defaults? (Excel practice unknown) | BA |
| OQ-09 | **Type of repair**: free text or maintained list (reporting implications)? | BA |
| OQ-10 | **Admin single-side view** (× N toggle): keep in the new UI or drop? | BA |
| OQ-11 | **`menu.calculator`** is catalogued but enforced nowhere — should the new costing page enforce it (recommended), and does anyone rely on the current looseness? | BA |
| OQ-12 | **Category-exclusion warning**: wording/severity per category — generic warning, or per-category consequence text (needs authoring)? | new CA |
| OQ-13 | **Excel paste**: keep in the new UI as a transition assist, or retire once the new page ships? (marked keep [PROPOSAL] in the matrix) | BA |
| OQ-14 | **PRICE 20.04.2004.xls**: 29 live workbook formulas still reference a 2004 price list (file not provided). Which lines, are those prices valid, and do any of them exist in imported app data? | BA + investigation |
| OQ-15 | **Fingerprint scope revisit**: if category/extras state moves into the saved costing (33.2), should extras re-enter reference identity? | BA |

## 35. Assumptions

1. The 26 active body types (17 v2) on the dev DB approximate production's set; the new UI must handle both v2 and legacy gating data. [DB read, 17 Aug 2026]
2. Nadie's roles/permissions match the 'full' role's seeded grants (dev grants = seed defaults; production grants read separately if needed).
3. The provided workbooks are the authoritative Excel model (`GRP Costings 2018.xlsx` actively edited as of 13 Aug 2026).
4. Downstream consumers (dashboards, accept/decline, pre-job, planning, exports) continue to read the saved-costing shape; the new UI writes a compatible record.
5. The four recipe-pricing engines and their admin pages remain the pricing backbone; the redesign changes where prices are *edited from*, not how they are computed.
6. Labour is out of scope (ratified); no unit-of-measure conversion is introduced.
7. The AI help + Excel audit features carry over unchanged in concept.

## 36. Risks

Two families: **inherited defects/quirks** (fix or consciously carry) and **redesign risks**.

### 36.1 Inherited (from the code investigation — each verified with file:line in Part 14 / agent reports)

| # | Risk | Severity |
|---|---|---|
| R-01 | Category totals (unrounded sum) vs line sums (rounded) differ by cents in the same view/documents | Low / trust |
| R-02 | `formula_overrides` honoured only in replay mode — silently ignored elsewhere | Low |
| R-03 | Client duplicate-check omits `is_repair` — repair quotes checked against normal sequence (server side is correct) | Med — fix with repair work |
| R-04 | Quote-number assignment failure is swallowed → numberless record | Med |
| R-05 | `replace` bulk-DELETE cascades validated references away, no second confirm | **High — fix in new UI** |
| R-06 | Approve lock is process-local; 4 prod workers → race window | Med |
| R-07 | 30 s cache TTL: preview vs save can use different formula libraries | Low |
| R-08 | Formula tooltip substitutes different values (thicknesses 0, doors 1) than the engine | Low / trust |
| R-09 | Client sends `num_doors=2`; engine default is 1 — formulas using `num_doors` depend on caller | Med — document |
| R-10 | Quantity formulas run through real `eval` (emptied builtins); admin-writable | Med — new UI should keep the surface admin-only |
| R-11 | 700 ms debounce lets an approve bind the PREVIOUS calc (UI hazard; CI hardened) | Med — eliminated by Part 24.9 |
| R-12 | Soft-deleted materials keep costing silently via existing BOM rows | Med |
| R-13 | Optional-named row with NULL section id can never be enabled | Low |
| R-14 | Insulation pair identity and switch-ALL are name-substring (`EPS`/`PU`) matched | Med — carry consciously |
| R-15 | RICE GRAIN ⇄ KICKPLATES is a hardcoded name coupling — should become data | Low |
| R-16 | Legacy display fallback guesses the quoted door on old records | Low |
| R-17 | Reference fingerprints embed ALL template body variables — template edits invalidate old references | Med — OQ-15 |
| R-18 | Recipe maths re-implemented client-side for tooltips (drift risk) | Low — dies with the new UI |
| R-19 | Negative-quantity clamp has a pure-number bypass | Low |
| R-20 | Unpriced material = silent R0 (5 perennial offenders on prod) | **High — fixed by Part 24.8** |
| R-21 | `/api/approve` re-sorts sections from a fresh DB read vs `/api/calculate`'s cache | Low |
| R-22 | Import guide + sample template contradict every parser (item name col C vs A) | Med — fix with docs |

### 36.2 Redesign risks

- **Silent rule loss** — the reason Part 14 exists. Mitigation: the new CA checks each of the 71 rules off explicitly (retire only via BA sign-off).
- **Fingerprint drift** — changing what identifies a reference breaks existing references (RULE-REF-001, OQ-15).
- **Saved-record compatibility** — old costings must re-open (replay mode is the guarantee to preserve).
- **Template-write semantics change (OQ-02)** — removing mid-costing template writes is a behaviour change users may currently rely on; needs comms.
- **Two-worlds body options** — 17 v2 + 9 legacy bodies must both flow through the new category model from day one.
- **Scope creep into stock/SAP** — the stock model is a picker + seam, not an inventory system (Part 10.1).

---

## 37. NEW CA DESIGN BRIEF

You are designing a NEW costing experience for ICB. This document is your specification of record.

**The new UI must:**
- be fundamentally different from the old MES costing UI — do not copy its page structure, navigation, configuration workflow, or interaction model
- centre on ONE primary costing page (Part 24 sketch is illustrative, not a layout)
- start a costing by selecting an existing Body Type from a dropdown — never via the Template page
- include **REPAIR** in that same dropdown: flat line list (stock picks + free-hand), customer + type of repair recorded (Part 30)
- expose insulation type + thickness directly inside the relevant categories (Part 26)
- let the user include/exclude ANY category, with a warning (Part 25)
- keep the four money stages always visible at the top: Materials · +Margin · TOTAL (÷ratio) · NET (−discount) (Part 24.1)
- make quantity editable (per-costing override; formula stays the default) and price editable with scope choice (Parts 24.4–24.5)
- make value provenance visible: calculated / computed-recipe / overridden / stock-derived / free-hand (Part 24.6)
- support add-item by stock search AND free-hand entry (Parts 27, 29), SAP-ready by `sap_code` (Part 28)
- surface zeros and formula errors loudly (Part 24.8)
- compute live and saved totals through one server path and bind the save to what is on screen (Part 24.9)
- stop costing gestures from silently rewriting shared templates (Part 24.10, OQ-02)
- preserve every rule in Part 14 unless the BA retires it in writing; the Part 31 matrix is your checklist
- keep permissions, exports, versioning, validated references, Excel audit, chassis, quote numbering working as specified
- feel familiar to someone who lived in the Excel workbook — and be dramatically simpler than the current application

**Design philosophy** (ratified): *we are not redesigning the old application; we are redesigning the costing experience.* The old system is your source of business rules, calculations, data, dependencies, body types and history. It is NOT your source of layout, navigation, visual design, configuration workflow, or interaction model. When in doubt, ask: "what would the spreadsheet user expect?"

**On v4.37 (OQ-01):** a parked native React calculator exists on `main` (`frontend/src/screens/Costings/calculator/`, ADR 0031). It is a parity-of-output re-implementation of Calculator 1's existing flow — the opposite philosophy to this brief. Mine it for plumbing (API calls, types, save bar mechanics); do not inherit its UX. Whether to build on that branch or start clean is an explicit open decision for you and the BA.

**Your first deliverables** [PROPOSAL]: (1) a design concept for the one-page costing experience validated against the Part 32 journeys; (2) the OQ answers you need from the BA; (3) a rule-coverage checklist against Part 14; (4) a data-model delta against Part 33.

---

## Appendix A — Route map (current system)

| Surface | Route | Gate |
|---|---|---|
| Calculator 1 | `/calculator`, `/mes/calculator` (iframe target) | login only (RULE-PERM-002) |
| Calculator 2 (to be eliminated) | `/calculator2`, `/mes/calculator2` | login only |
| Legacy dashboard | `/`, `/mes/dashboard` (unlinked) | login |
| Results | `/results/{id}` | login (+ per-feature keys) |
| React shell | `/costings`, `/costings/new` (embeds calc), `/costings/results/:id`, `/costings/:quote` | session + shell keys |
| Body Templates | `/admin/templates` | `menu.body_templates` |
| Configurator settings / preview | `/admin/settings`, `/admin/configurator-preview` | admin |
| Formulas | `/admin/formulas` | admin |
| Formula scan | `/admin/templates/formula-scan` | admin |
| Materials | `/admin/materials` | `menu.materials` |
| Skin/Taping/Floor/Cleats/SAP prices | `/admin/skin-formulas` etc. | `menu.pricing_formulas` |
| Chassis / Customers / Quote numbering / Quote+PDF templates / BOM snapshots / Imports | `/admin/...` | respective `menu.*` / admin |

*Deep-link params:* `?edit=<id>` (edit pending), `?from=<id>` (copy), `?trailer=<id>` (pre-select), `?skin=mes` (light skin).

---

*End of document. Prepared as the primary BA specification for the ICB Costing UI redesign. Questions → Michael (BA) via the BA-coordinator.*
