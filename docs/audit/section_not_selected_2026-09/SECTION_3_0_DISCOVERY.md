# v1.59.1: NOT SELECTED header and rule-editor keep. §3.0 discovery

Dispatch 7, 29 Sep 2026. Branch `feat/v1.59.1-section-not-selected`, cut from `e62e339`
(v1.59.0 + the #199 outcome doc). All database reads ran against the dev database `icb` in
read-only sessions (`default_transaction_read_only=on`). Nothing was written to dev.

## Part A: where a section subtotal is rendered (E3 sweep by mechanism)

The key fact is in `formula_engine.calculate_bom`. It adds a line to `category_totals` only
when the line is **not** excluded. So a section whose every line is excluded has **no key**
in `category_totals`. It is never stored as 0. Excluded lines still ride in `items[]` with
`excluded: true` and `line_cost: 0.0`.

| # | Surface | Internal / customer | All-excluded section today | Action |
|---|---|---|---|---|
| 1 | Calculator BOM table, section header (`calculator.js` `renderBOMWithCosts`) | internal | **R0.00**. Grouped from `items[]` including excluded lines. The subtotal shows while the section is collapsed (the default). | **NOT SELECTED** |
| 2 | Calculator cost summary (`renderSummary`, reads `category_totals`) | internal | not listed | none |
| 3 | Calculator 2 section header (`calculator2.js:4810`) | internal | Calc 2 runs `include_all_items`, which never evaluates conditions. Its lines are only ever user-excluded or optional-off, and the ratified rule leaves those unchanged. | none |
| 4 | Saved costing `/results/{id}` (`results.html`) | internal | not listed (`strip_excluded_items` runs first) | none |
| 5 | React saved-costing view (`CostingDetail.tsx` `LiveBom`) | internal | not listed (`filter(l => !l.excluded)`) | none |
| 6 | Excel / Word / PDF costing exports + e-mail (`exports.py`, `document_context.py`) | **customer** | **not listed** (strips excluded items, then iterates `category_totals`) | none |
| 7 | Quote PDFs (`/results/{id}/report`, `report_engine`) | **customer** | no section subtotals at all | none |
| 8 | Repair quotation document (`quote_document.py`) | **customer** | excluded lines filtered, no section subtotals | none |
| 9 | Legacy `pdf_templates/default.html`, `explosive.html`, `reports/cost_breakdown.html` | admin test route / dead | iterate `category_totals` (not listed) | none |

**Customer-facing documents do not list an all-excluded section today.** There was nothing to
STOP on. The only R0.00 is surface 1.

On surface 1 the label is shown in both the collapsed and the expanded header. The subtotal
itself only shows while a section is collapsed. An expanded all-excluded section has no visible
rows (the eye is off by default), so without the label it would read as an empty header.

Residual risk, noted and not changed: a section whose *included* lines legitimately total 0
(R0 prices, zero-rule rows) is listed as 0.00 in the exports. That is correct, because the
section is selected. It relies on the engine's no-key behaviour, not on an explicit filter.

### C4: how condition-excluded is told apart

This lane adds a field; it does not parse `excluded_reason`. The additive field is
`excluded_by: "condition" | "user" | "optional_section"`. It is set in
`_build_bom_items` (both paths), in `free_hand.to_bom_items`, and forced to `None` in the
repair category preview. `calculate_bom` attaches it **only on excluded lines**. An included
line's payload, and every saved snapshot of one, stays byte-identical. When a line is both
condition-excluded and user-excluded, the condition wins, exactly as the reason text already
did. No number changes: this is pinned by
`test_excluded_by_changes_no_money_and_rides_only_on_excluded_lines`.

## Part B: exposure of saved rules to the replace-on-save defect (dev)

The method uses the rear-frame lane's JS port of `collectScopedRuleOptions` /
`buildUsedCategoryMap`, run over every `configurator_drafts` row. It covers every item rule
with named conditions on an active configurator-v2 body.

| | dev |
|---|---|
| rules with named conditions | **230** |
| ≥1 condition outside its branch (exposed) | **0** |
| already rewritten (signature: a single condition = the branch's first offered flag, whose region has no link to the line) | **0** |

**Known-hit self-test (rule 3).** The check was run in memory against a synthetic rule: the
rear-frame lane's proposed `SRD PU = N` on each body's REAR FRAME category. It reads as
EXPOSED on **17 / 17** bodies that have a REAR FRAME category, and the rewritten-signature
check catches all 17 (options[0] is `FRONT EPS` everywhere). The empty result is real.

**Per body:** none are exposed today. The exposure starts when the rear-frame lane writes its
~144 rules. This lane removes it.

### A second way the editor could rewrite a rule it didn't show (found in the sweep)

The editor opened `draft.itemRules[id]` in preference to the database rule. The draft copy is
written only by the editor. A rule written by a tool (PATCH or SQL) or another screen therefore
opened **stale**, and Save wrote the stale copy over the database.

On dev, **14 of 244** draft rule entries differ from the database. They are all on inactive,
classic (non-v2) bodies: ADVANTICA BODY ×10 and MANNI RIGIDS CB [deleted-3] ×4. The draft
holds a rule and the database holds none. Live exposure is 0. The editor now opens the
**database** rule (the categories endpoint's live copy) and falls back to the draft only when
there is none. The catalog chips still read the draft first; that is unchanged and noted.

### The one server-side change in Part B (C-decision)

The categories and tree endpoints dropped each condition's `option_id`. That meant no client
could send a condition back as stored, and an unchanged Save could only be byte-identical when
the server's by-name auto-resolve happened to pick the same id. Both endpoints now pass the
stored `option_id` through when present, which is an additive field. The PATCH endpoint is
unchanged. In the tests, `test_unchanged_save_round_trips_byte_identical[odd]` (a stored id the
server would not auto-resolve) fails without this change.

The preview page (`admin_configurator_preview.html`) offers all body options, not a branch
subset, so it never substituted. It now shows a flag it doesn't offer as itself (`… (kept)`)
instead of visually as the first option. On a flag change, both editors drop the old flag's
`option_id` so the server re-anchors it. Without that, the new `option_id` pass-through would
carry the old flag's id onto the new flag.
