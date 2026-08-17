# Data-model delta — new costing UI (§3.3)

**Scope:** the concrete take on spec Part 33.2, verified against the ORM (`backend/app/database.py`) and the shared dev DB (read-only, 17 Aug 2026). Design-phase proposal for the build WO — no migration is written here.
**Principle:** extend the saved-costing shape, never replace it. Every existing reader (dashboards, exports, pre-job, planning, replay edits, Excel audit) keeps working on an unchanged surface; new facts ride alongside.

## 0. Verified facts the delta rests on

| Fact | Evidence |
|---|---|
| `calculations.trailer_type_id` is **nullable** in the DB (`is_nullable = YES`) and in the ORM (`Column(Integer, ForeignKey(...))`, no `nullable=False`) | information_schema + `database.py:413` — **no schema fight for REPAIR** |
| `calculations.is_repair` is `boolean NULL`, no default; legacy NULL reads as "normal" (RULE-SAVE-001) | information_schema |
| `result_json` today: `input_state{body_option_selections, chassis, excluded_categories, flag_overrides, is_repair, optional_sections_enabled, override_reasons, overrides, profit_margin, ratio_label, ratio_value, ui_snapshot, user_excluded_bom_ids}` + `items`, `body_variables`, `category_totals`, `overrides_by_bom/by_name`, money fields, `version` | latest dev record |
| `validated_references(id, calculation_id, label, config_fingerprint, trailer_type_id, created_by, created_at, active)` — **no version column** | information_schema |
| Fingerprint v1 = `{trailer_type_id, dims(3dp), body_options, excluded_categories, flags, body_variables(3dp)}`; extras deliberately OUT | `services/validated_references.py:101-143` |
| `bom_sections` is a **global** registry (`name UNIQUE`); category identity is by name | `database.py:637-660` |
| Body-option rows: `body_option_group == section name` on v2 bodies; legacy groups may match no section | dev DB (MEAT HANGER LARGE vs TAUT LINER RIGID) |

## 1. Costing type (spec 33.2 row 1)

```sql
ALTER TABLE calculations ADD COLUMN costing_type VARCHAR(16) NOT NULL DEFAULT 'body';   -- 'body' | 'repair'
UPDATE calculations SET costing_type = 'repair' WHERE is_repair IS TRUE;
-- CHECK (costing_type IN ('body','repair'))
-- CHECK (costing_type = 'repair' OR trailer_type_id IS NOT NULL)   -- add NOT VALID first; validate after a data check
```
- **`is_repair` stays** and is written on every save (`is_repair = costing_type = 'repair'`) so every existing reader — status display "Repair", dashboard filter, `repair_phases_json` gate, revision sequences — is untouched.
- Duplicate detection: `(customer_id, costing_type, trailer_type_id)` — the client now sends `costing_type` (fixes R-03 by construction).
- Repairs save with `trailer_type_id = NULL`, `dimensions_json = NULL`, no `body_variables`, no `chassis`.

## 2. Repair types (spec 33.2 row 2, OQ-09 ratified)

```sql
CREATE TABLE repair_types (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,     -- soft delete, same idiom as materials/customers
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
ALTER TABLE calculations
  ADD COLUMN repair_type_id   INTEGER NULL REFERENCES repair_types(id) ON DELETE SET NULL,
  ADD COLUMN repair_type_name VARCHAR(120) NULL,   -- write-time snapshot (contact-snapshot pattern, ADR 0016)
  ADD COLUMN work_description TEXT NULL;           -- D4, optional
```
- Admin CRUD on `/admin/repair-types`, gated like other catalogues (`menu.*` admin). Seed list is a BA input (mockup uses placeholders).
- Reporting/dashboards filter on `repair_type_name` (stable even if a type is renamed) or `repair_type_id` (current name).
- Server 422s a repair save without `repair_type_id` (RULE-SAVE-004 idiom).

## 3. Saved-costing shape — `input_state` v2 (spec 33.2 rows 3–6, 24.10, D3)

No new columns: extend `result_json.input_state`, exactly the pattern the app already uses ("future fields don't need new ALTERs", `database.py:466`). Add `input_state.schema = 2`; absent = v1 (legacy).

```jsonc
"input_state": {
  "schema": 2,
  "costing_type": "body",                       // mirrors the column
  "door_choice": "DRD",                          // explicit — retires the R-16 display guess for new records
  "insulation": {                                // per-costing, per insulated category (Part 26 / OQ-02)
    "FRONT": {"side": "PU", "thickness_m": 0.060},
    "FLOOR": {"side": "EPS", "thickness_m": 0.076}
  },
  "body_variable_overrides": {"FRONT PU": 0.060, "FRONT EPS": 0, "FLOOR EPS": 0.076, "FLOOR PU": 0, ...},
                                                 // DERIVED from `insulation` at save; kept because the engine
                                                 // and edit-replay already speak this key (RULE-INS-007 pins)
  "category_state": {"ROOF": "excluded"},        // user excludes of NON-optional categories (Part 25); absent = included
  "optional_sections_enabled": [79],             // unchanged key; now authoritative (moves off localStorage — OQ-15)
  "user_excluded_bom_ids": [1234, 1240],         // unchanged key; now spans every category (Calc-2 model generalised)
  "qty_overrides": {"1234": 15.0},               // bom_id → FINAL quantity (D2); mirrors `overrides` (price) shape
  "overrides": {...}, "override_reasons": {...}, // unchanged (quote price overrides)
  "added_lines": [                               // stock picks + free-hand (Parts 27, 29) — per-costing only
    {"origin": "stock",    "material_id": 88, "section": "OPTIONAL EXTRAS", "qty": 1,
     "unit_price": 8600, "unit": "Each", "description": "Side door … – Single", "sap_code": "…"},
    {"origin": "freehand", "material_id": null, "section": "FLOOR", "qty": 2,
     "unit_price": 350, "unit": "each", "description": "Extra floor drain (site)", "note": null}
  ],
  "zero_ack": {"count": 2, "at": "2026-08-17T10:31:00Z", "by": "nadie"},   // D3 acknowledgement, null if none
  "result_hash": "sha256:…",                     // the server result the save bound to (Part 24.9)
  "body_option_selections": {...}, "flag_overrides": {...}, "excluded_categories": [...],   // unchanged (engine inputs)
  "chassis": {...}, "profit_margin": 5, "ratio_value": 0.55, "ratio_label": "55%",           // unchanged
  "ui_snapshot": {...}                                                                       // unchanged
}
```
`result_json.items[]` gains two read-only provenance fields per line so exports/results can label without re-deriving:
`"origin": "template" | "stock" | "freehand"` and `"provenance": {"qty": "formula"|"override", "price": "recipe"|"permanent"|"catalogue"|"quote_override"|"freehand", "price_age_days": 12}`. Free-hand/stock lines carry `bom_id: null` and an `added_index`.

**Rules for the added shapes**
- `added_lines` are **never** written to `bill_of_materials` or `materials` (Part 29). OQ-04 "promote to catalogue later" is an admin action outside this record.
- `qty_overrides` values are final quantities; the server applies them **after** multiplier and waste (D2, `formula_engine.py:191` semantics) and marks the item `provenance.qty = "override"`. Sticky across recomputes; the client shows the moved formula value (OQ-03 provisional).
- `insulation` is authoritative; `body_variable_overrides` is derived at save and at every `/calculate` from it (so the engine, edit-replay and the audit tool see exactly today's key).
- `category_state` records only *user* excludes of non-optional categories; rule/sibling exclusions stay derivable (`excluded_categories` unchanged) and are not stored as user intent.

## 4. Free-hand lines & permissions

- Storage: §3 `added_lines` only. Exports strip nothing extra; the Excel audit reports them `only_in_live` (Part 29 note).
- New permission keys in `PERMISSION_CATALOGUE` (bootstrap-healed; the multi-worker advisory lock from #120 makes that safe): `costings.freehand_items`, `costings.qty_override`, `costings.template_save` — default grants `{admin, full}` like `costings.price_master_edit`. `costings.template_save` gates the only remaining template write from the page (Insulation → Save to template).

## 5. Validated references — fingerprint v2 + migration (spec 33.2 migration constraint, OQ-15)

```sql
ALTER TABLE validated_references ADD COLUMN fingerprint_version SMALLINT NOT NULL DEFAULT 1;
```
- **v2 canonical config** = v1 fields **plus** `optional_sections_enabled` (as section names, sorted), `user_excluded_bom_ids` (sorted), `category_state` (sorted excluded names), `added_lines` in optional sections (sorted `material_id`/description), `door_choice`. Insulation continues to enter via `body_variables` (already 3 dp) — no double counting.
- **Migration is a one-shot recompute, not coexistence:** for every reference (active or not), read the pointed calculation's stored `input_state` (which already carries `optional_sections_enabled` + `user_excluded_bom_ids` for post-v1.39.9 records), compute v2, write `config_fingerprint`, set `fingerprint_version = 2`. A reference whose calculation lacks the fields (pre-v1.39.9) cannot be recomputed → set `active = false` with a logged reason (its marking already 409s today, RULE-REF-002). After the migration **only v2 exists at match time**; the version column is audit + a guard (`WHERE fingerprint_version = 2` in the match query) — never a dual-definition lookup.
- Behaviour change (sanctioned): two costings differing only in extras become distinct identities (no match) instead of one identity with drift.
- Idempotent, fail-loud data script per house style (`scripts/rules/*` pattern), run in the same release as the schema change.

## 6. Compatibility guarantees (spec 36.2)

| Concern | Guarantee |
|---|---|
| Old records re-open | `input_state.schema` absent → v1 hydration: `category_state` derived from `excluded_categories`, `insulation` derived from `body_variables`/`body_variable_overrides`, `added_lines = []`. Replay mode (RULE-EDIT-003) untouched. |
| Downstream readers | Every existing top-level `result_json` key, `net_total`, `discount_*`, `quote_number`, `status`, `is_repair`, `repair_phases_json` unchanged in meaning. |
| Exports / results page | Read `items[].origin/provenance` when present; fall back to today's flags when absent. |
| Excel audit | Free-hand/stock lines classify as `only_in_live` (documented). |
| Edit-balance gate | Unchanged (saved money fields vs recomputed). |

## 7. Server contract changes (plumbing mined from v4.37, UX not inherited)

| Endpoint | Change |
|---|---|
| `POST /api/calculate` | accepts `costing_type`, `insulation`, `qty_overrides`, `added_lines`, `category_state`; applies ratio + discount server-side too (**one authority**, RULE-CALC-015); returns `result_hash` and per-line `origin/provenance` + human `reason` for gated rows (derived for legacy links). |
| `POST /api/approve` | requires `result_hash`; **409** on mismatch (bind-what's-on-screen — this **replaces** the 700 ms debounce hazard, RULE-EDIT-008); requires `repair_type_id` when `costing_type='repair'`; stores `zero_ack`. Keeps `version_action` semantics; `replace` additionally requires `confirm: "REPLACE"` (R-05). |
| `GET /api/check-duplicate` | `costing_type` replaces `is_repair` (both accepted during transition). |
| `GET /api/calculations/{id}` | returns the record with the optimistic-lock etag (v4.37 plumbing) — Overwrite sends it back (`412` on mismatch, R-06 shrinks). |
| `GET /api/materials?q=` | picker search over name / SAP code / category / sub-category; exposes `material_code`; no on-hand fields (Part 27). |
| `GET/POST /api/repair-types` | catalogue CRUD (admin). |
| `POST /api/costings/{id}/insulation/save-to-template` | explicit, listed diff → `PUT /api/bom/{id}` writes, gated `costings.template_save`; the **only** template write reachable from the page. |
| Section-name → reason strings | server-side derivation from `body_option_linked(_id)` / `bom_conditions` / masters — nothing authored (guard-rail 1). |

## 8. What does NOT change

`trailer_types`, `bill_of_materials`, `bom_sections`, `materials`, recipe tables, `chassis_*`, `customers`/`customer_contacts` + snapshot columns, `quote_counter`, `formulas`/`global_variables`, `icb_sap.*` (no FK from costing — Part 28), the accept/decline/pre-job/planning columns.

## 9. Migration checklist for the build WO

1. Alembic: `costing_type` (+backfill, checks) · `repair_types` + `repair_type_id/name`, `work_description` · `validated_references.fingerprint_version` — **pick numbers per the parallel-lane rule** ([[feedback-parallel-lane-migration-collision]]).
2. Data script: fingerprint v2 recompute (idempotent, fail-loud, logs retired refs).
3. Permission catalogue: three keys, default grants; bootstrap heals under the advisory lock.
4. `input_state.schema = 2` writer + v1 reader shim; `items[].origin/provenance`.
5. Contract changes §7 with journeys updated in the same phase ([[feedback-verify-ci-green-each-phase]]).
