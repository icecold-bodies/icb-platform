-- v1.58 audit pricing corrections — §3.0 IMPACT REFRESH (run just before the prod apply). READ ONLY.
--
-- The saved costings the corrections would have priced differently, by QUOTE NUMBER ONLY:
-- no customer, contact, end-user or person column is selected, and no such table is joined
-- (the 27 Sep data-minimisation ruling). Michael looks each quote up in the MES himself.
--
-- Run from an EMPTY output directory (every \o writes a relative file there):
--   psql "$URL" -X -q -v ON_ERROR_STOP=1 -f impact_refresh.sql
-- One READ ONLY transaction, ROLLBACK at the end: the server refuses any write inside it.
-- Outputs:
--   00_env.csv          database, alembic head, time, row counts
--   C_impact.csv        per affected costing: quote number, body, dims, SRD y/n, dates, status, the affected lines
--   D_recompute.jsonl   the same costings for the CA's offline re-pricing: dims, saved variables, affected lines
--
-- Scope (dispatch default 1, as widened on 28 Sep):
--   F1  a saved SRD PU line with a price  (freezers, icecream 4.9 UP, explosive, CHILLER MEDIUM / LARGE / 2.3)
--   F2  a saved ALU EXTRUTION FLOOR line with a price
--   F3  every ICECREAM 4.9 UP costing (trailer 18) — the impact is 0 at exactly 6.7 m
--   F4  every CHILLER MEDIUM costing (trailer 26) with a double-door DOOR RUBBER line

\set QUIET on
\pset footer off
\pset format csv
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10min';

\o 00_env.csv
SELECT current_database() AS db,
       (SELECT string_agg(version_num, ',') FROM alembic_version) AS alembic,
       now() AS run_at,
       current_setting('transaction_read_only') AS read_only,
       (SELECT count(*) FROM calculations) AS calculations,
       (SELECT count(*) FROM calculations WHERE trailer_type_id IS NOT NULL AND result_json IS NOT NULL) AS body_costings,
       (SELECT max(created_at) FROM calculations) AS last_costing;

\o C_impact.csv
WITH c AS (
  SELECT k.id, k.quote_number, k.trailer_type_id, k.created_at, k.status, k.approved_at,
         k.pre_job_sent_at, k.job_number_assigned, k.deleted_at, k.is_repair,
         k.result_json::jsonb AS j,
         CASE WHEN jsonb_typeof(k.result_json::jsonb->'items') = 'array' THEN k.result_json::jsonb->'items' ELSE '[]'::jsonb END AS items,
         CASE WHEN left(ltrim(COALESCE(k.dimensions_json, '')), 1) = '{' THEN k.dimensions_json::jsonb END AS d
  FROM calculations k
  WHERE k.trailer_type_id IS NOT NULL AND k.result_json IS NOT NULL AND left(ltrim(k.result_json), 1) = '{'
), x AS (
  SELECT c.id,
    (SELECT i FROM jsonb_array_elements(c.items) i
      WHERE upper(btrim(i->>'category')) = 'SRD' AND upper(btrim(i->>'material')) IN ('PU', 'PU FOAM')
      ORDER BY (i->>'line_cost')::numeric DESC NULLS LAST LIMIT 1) AS srd_pu,
    EXISTS (SELECT 1 FROM jsonb_array_elements(c.items) i
      WHERE upper(btrim(i->>'category')) = 'SRD' AND (i->>'line_cost')::numeric > 0) AS srd,
    (SELECT sum((i->>'line_cost')::numeric) FROM jsonb_array_elements(c.items) i
      WHERE upper(btrim(i->>'material')) = 'ALU EXTRUTION FLOOR') AS alu_floor_cost,
    (SELECT count(*) FROM jsonb_array_elements(c.items) i
      WHERE c.trailer_type_id = 18 AND (i->>'formula') ~ '(^|[^0-9.])6\.75?([^0-9]|$)'
        AND (i->>'line_cost')::numeric > 0) AS f3_lines,
    (SELECT sum((i->>'line_cost')::numeric) FROM jsonb_array_elements(c.items) i
      WHERE c.trailer_type_id = 18 AND (i->>'formula') ~ '(^|[^0-9.])6\.75?([^0-9]|$)') AS f3_lines_cost,
    (SELECT string_agg((i->>'quantity') || ' x ' || (i->>'unit_price'), '; ') FROM jsonb_array_elements(c.items) i
      WHERE c.trailer_type_id = 26 AND upper(i->>'category') ~ 'DRD' AND upper(i->>'category') ~ 'FITTINGS'
        AND upper(i->>'material') ~ '2317 DOOR RUBBER') AS f4_2317_door_rubber
  FROM c
)
SELECT c.id AS calc_id, c.quote_number, c.trailer_type_id AS trailer_id, t.name AS body,
       (c.d->>'length')::numeric AS length, (c.d->>'width')::numeric AS width, (c.d->>'height')::numeric AS height,
       x.srd AS srd, c.created_at, c.status, c.approved_at, c.pre_job_sent_at, c.job_number_assigned,
       c.deleted_at, c.is_repair,
       (x.srd_pu->>'formula') AS srd_pu_formula, (x.srd_pu->>'quantity')::numeric AS srd_pu_qty,
       (x.srd_pu->>'unit_price')::numeric AS srd_pu_unit_price, (x.srd_pu->>'line_cost')::numeric AS srd_pu_line_cost,
       (c.j->'body_variables'->>'SRD PU')::numeric AS srd_pu_thickness,
       x.alu_floor_cost, x.f3_lines, x.f3_lines_cost, x.f4_2317_door_rubber,
       (c.j->>'grand_total')::numeric AS cost_total, (c.j->>'selling_price')::numeric AS selling_price,
       (c.j->>'profit_margin')::numeric AS margin_pct, (c.j->>'ratio_value')::numeric AS ratio
FROM c
JOIN x ON x.id = c.id
JOIN trailer_types t ON t.id = c.trailer_type_id
WHERE COALESCE((x.srd_pu->>'line_cost')::numeric, 0) > 0
   OR COALESCE(x.alu_floor_cost, 0) > 0
   OR c.trailer_type_id = 18
   OR x.f4_2317_door_rubber IS NOT NULL
ORDER BY c.created_at;

\pset format unaligned
\pset tuples_only on
\o D_recompute.jsonl
WITH c AS (
  SELECT k.id, k.quote_number, k.trailer_type_id, k.created_at, k.status, k.dimensions_json,
         k.result_json::jsonb AS j,
         CASE WHEN jsonb_typeof(k.result_json::jsonb->'items') = 'array' THEN k.result_json::jsonb->'items' ELSE '[]'::jsonb END AS items
  FROM calculations k
  WHERE k.trailer_type_id IS NOT NULL AND k.result_json IS NOT NULL AND left(ltrim(k.result_json), 1) = '{'
)
SELECT json_build_object(
         'calc_id', c.id, 'quote_number', c.quote_number, 'trailer_id', c.trailer_type_id,
         'created_at', c.created_at, 'status', c.status,
         'dims', CASE WHEN left(ltrim(COALESCE(c.dimensions_json, '')), 1) = '{' THEN c.dimensions_json::json END,
         'body_variables', c.j->'body_variables', 'global_variables', c.j->'global_variables',
         'grand_total', c.j->'grand_total', 'selling_price', c.j->'selling_price',
         'profit_margin', c.j->'profit_margin', 'ratio_value', c.j->'ratio_value',
         'items', (SELECT json_agg(json_build_object(
                             'category', i->'category', 'material', i->'material', 'bom_id', i->'bom_id',
                             'formula', i->'formula', 'quantity', i->'quantity',
                             'unit_price', i->'unit_price', 'line_cost', i->'line_cost'))
                   FROM jsonb_array_elements(c.items) i
                   WHERE (upper(btrim(i->>'category')) = 'SRD' AND upper(btrim(i->>'material')) IN ('PU', 'PU FOAM'))
                      OR (c.trailer_type_id = 18 AND (i->>'formula') ~ '(^|[^0-9.])6\.75?([^0-9]|$)')
                      OR upper(btrim(i->>'material')) = 'ALU EXTRUTION FLOOR'
                      OR (c.trailer_type_id = 26 AND upper(i->>'material') ~ 'DOOR RUBBER'))
       )
FROM c
WHERE c.trailer_type_id = 18
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(c.items) i
              WHERE ((upper(btrim(i->>'category')) = 'SRD' AND upper(btrim(i->>'material')) IN ('PU', 'PU FOAM'))
                     OR upper(btrim(i->>'material')) = 'ALU EXTRUTION FLOOR')
                AND (i->>'line_cost')::numeric > 0)
   OR (c.trailer_type_id = 26 AND EXISTS (SELECT 1 FROM jsonb_array_elements(c.items) i
              WHERE upper(i->>'material') ~ 'DOOR RUBBER'))
ORDER BY c.created_at;
\o

ROLLBACK;
\pset tuples_only off
\pset format aligned
\echo 'impact_refresh.sql: finished — READ ONLY transaction rolled back, nothing written.'
