-- v1.58 — read-only checks after the pricing-corrections apply (BA ruling 2c §2 + §4 items 4-5 + F5 #3).
-- Run from an EMPTY directory (every \o writes a relative CSV there). One READ ONLY transaction, rolled back.
-- No customer, contact or end-user column. `changed_by` (price_history) is the staff account a TOOL stamps; the app's
-- own material edits leave it NULL.
--   00_env.csv                      database, alembic, time, read_only
--   F2_alu_draft_nodes.csv          §2.3: the ALU EXTRUTION FLOOR draft nodes on ICECREAM 3,2 (16) / 4.8 (17)
--   F2_draft_count.csv              drafts per body (no row = no draft)
--   P1_48_floor_lines.csv           §2 open item: every FLOOR line on ICECREAM UP TO 4.8 (17), its gate and price
--   P2_48_floor_draft_nodes.csv     the draft nodes that decide which 4.8 floor choice starts ticked
--   E3_srd_pu_material.csv          the shared SRD PU material (the one that went R516.64 -> R4 100 on 7 Sep)
--   E3_inheriting_lines.csv         §4.4: every line on that material with NO own price (inherits R4 100)
--   E3_all_lines_on_material.csv    context: every line on that material
--   C1_price_history_srd_pu.csv     §4.5: that material's price history, with changed_by
--   C2_changes_7sep.csv             §4.5: every material / line price change on 7 Sep (tool vs UI)
--   F5_3_explosive_pu_history.csv   F5 #3: the EXPLOSIVE 4.9 AND UP PU line-price history
--   F5_3_changes_22sep.csv          F5 #3: every material / line price change on 22 Sep

\set QUIET on
\pset footer off
\pset format csv
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5min';

\o 00_env.csv
SELECT current_database() AS db, (SELECT string_agg(version_num, ',') FROM alembic_version) AS alembic,
       now() AS run_at, current_setting('transaction_read_only') AS read_only;

\o F2_alu_draft_nodes.csv
SELECT d.trailer_type_id, d.updated_at, n.key AS node, n.value->>'type' AS type, n.value->>'label' AS label,
       n.value->>'flagValue' AS flag_value, n.value->>'flagMode' AS flag_mode,
       n.value->>'selectionMode' AS selection_mode, n.value->>'selectionValue' AS selection_value,
       n.value->>'flagBindingId' AS binding
  FROM configurator_drafts d, jsonb_each((d.payload::jsonb)->'nodes') n
 WHERE d.trailer_type_id IN (16, 17) AND upper(n.value->>'label') ~ 'ALU EXTRU'
 ORDER BY 1, 3;

\o F2_draft_count.csv
SELECT trailer_type_id, count(*) AS drafts FROM configurator_drafts WHERE trailer_type_id IN (16, 17) GROUP BY 1 ORDER BY 1;

\o P1_48_floor_lines.csv
SELECT b.id AS bom_id, b.bom_section, m.name AS material, b.formula_expression, b.unit_price_override,
       m.price_per_unit AS material_price, b.bom_conditions, b.is_body_option, b.selection_mode, b.body_option_default
  FROM bill_of_materials b JOIN materials m ON m.id = b.material_id
 WHERE b.trailer_type_id = 17 AND upper(btrim(b.bom_section)) = 'FLOOR'
 ORDER BY b.id;

\o P2_48_floor_draft_nodes.csv
SELECT n.key AS node, n.value->>'type' AS type, n.value->>'label' AS label,
       n.value->>'selectionMode' AS selection_mode, n.value->>'selectionValue' AS selection_value,
       n.value->>'sourceCategoryKey' AS source_key, n.value->>'flagValue' AS flag_value,
       n.value->>'flagBindingId' AS binding, n.value->>'parentId' AS parent,
       (SELECT p.value->>'label' FROM jsonb_each((d.payload::jsonb)->'nodes') p WHERE p.key = n.value->>'parentId') AS parent_label,
       (SELECT p.value->>'selectionMode' FROM jsonb_each((d.payload::jsonb)->'nodes') p WHERE p.key = n.value->>'parentId') AS parent_mode
  FROM configurator_drafts d, jsonb_each((d.payload::jsonb)->'nodes') n
 WHERE d.trailer_type_id = 17
   AND upper(coalesce(n.value->>'label', '') || ' ' || coalesce(n.value->>'sourceCategoryKey', '')) ~ 'PLY|FLOOR|ALU|RICE'
 ORDER BY 1;

-- the shared SRD PU material = the material of FREEZER 2.3's SRD PU line (bom ids are shared dev/prod, material ids not)
\o E3_srd_pu_material.csv
SELECT m.id AS material_id, m.name, m.price_per_unit, m.last_updated, m.last_bulk_update_at, m.last_bulk_update_note
  FROM materials m WHERE m.id = (SELECT material_id FROM bill_of_materials WHERE id = 3576);

\o E3_inheriting_lines.csv
SELECT t.id AS trailer_id, t.name AS trailer, t.is_active, b.id AS bom_id, b.bom_section, b.formula_expression,
       b.is_body_option, b.bom_conditions,
       CASE WHEN b.formula_expression ~ '/\s*2\.98' THEN 'burt_thickness_shape' ELSE 'sheet_or_area_shape' END AS formula_shape
  FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
 WHERE b.material_id = (SELECT material_id FROM bill_of_materials WHERE id = 3576) AND b.unit_price_override IS NULL
 ORDER BY t.is_active DESC, t.id, b.id;

\o E3_all_lines_on_material.csv
SELECT t.id AS trailer_id, t.name AS trailer, t.is_active, b.id AS bom_id, b.bom_section, b.formula_expression,
       b.unit_price_override, b.price_updated_at
  FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
 WHERE b.material_id = (SELECT material_id FROM bill_of_materials WHERE id = 3576)
 ORDER BY t.id, b.id;

\o C1_price_history_srd_pu.csv
SELECT ph.id, ph.material_id, ph.old_price, ph.new_price, ph.changed_date, ph.changed_by
  FROM price_history ph WHERE ph.material_id = (SELECT material_id FROM bill_of_materials WHERE id = 3576)
 ORDER BY ph.changed_date, ph.id;

\o C2_changes_7sep.csv
SELECT 'price_history' AS src, ph.id, ph.material_id::text AS ref, m.name AS what, ph.old_price, ph.new_price,
       ph.changed_date AS at, ph.changed_by AS stamped_by
  FROM price_history ph JOIN materials m ON m.id = ph.material_id
 WHERE ph.changed_date >= '2026-09-07' AND ph.changed_date < '2026-09-08'
UNION ALL
SELECT 'bom_override_history', oh.id, oh.bom_id::text, oh.trailer_type_name || ' / ' || oh.material_name,
       oh.old_price, oh.new_price, oh.changed_at, NULL
  FROM bom_override_history oh
 WHERE oh.changed_at >= '2026-09-07' AND oh.changed_at < '2026-09-08'
 ORDER BY 7, 1, 2;

\o F5_3_explosive_pu_history.csv
SELECT oh.id, oh.bom_id, oh.trailer_type_name, oh.material_name, oh.old_price, oh.new_price, oh.changed_at, oh.batch_at
  FROM bom_override_history oh WHERE oh.bom_id IN (3940, 3974, 3996, 4005)
 ORDER BY oh.changed_at, oh.id;

\o F5_3_changes_22sep.csv
SELECT 'price_history' AS src, ph.id, ph.material_id::text AS ref, m.name AS what, ph.old_price, ph.new_price,
       ph.changed_date AS at, ph.changed_by AS stamped_by
  FROM price_history ph JOIN materials m ON m.id = ph.material_id
 WHERE ph.changed_date >= '2026-09-22' AND ph.changed_date < '2026-09-23'
UNION ALL
SELECT 'bom_override_history', oh.id, oh.bom_id::text, oh.trailer_type_name || ' / ' || oh.material_name,
       oh.old_price, oh.new_price, oh.changed_at, NULL
  FROM bom_override_history oh
 WHERE oh.changed_at >= '2026-09-22' AND oh.changed_at < '2026-09-23'
 ORDER BY 7, 1, 2;

\o
ROLLBACK;
\echo 'prod_checks.sql: finished — READ ONLY transaction rolled back, nothing written.'
