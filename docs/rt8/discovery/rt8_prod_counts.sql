-- RT8 §3.0 — READ ONLY. Pending costings: can each be frozen from its own result_json? Quote numbers, months, body
-- names and counts only (G4): no customer, contact or user field is selected. One statement.
with c as (
  select c.quote_number, to_char(c.created_at, 'YYYY-MM') as month, coalesce(t.name, 'REPAIR') as body,
         (c.trailer_type_id is null) as repair, c.result_json::jsonb as r
    from calculations c left join trailer_types t on t.id = c.trailer_type_id
   where coalesce(c.status, 'pending') = 'pending' and c.deleted_at is null
), f as (
  select quote_number, month, body, repair,
         jsonb_typeof(r->'items') = 'array' and jsonb_array_length(r->'items') > 0             as has_items,
         r ? 'category_totals' and r ? 'grand_total'                                          as has_totals,
         r ? 'body_variables' and r ? 'global_variables'                                      as has_vars,
         not exists (select 1 from jsonb_array_elements(case when jsonb_typeof(r->'items') = 'array'
                                                             then r->'items' else '[]'::jsonb end) it
                      where not (it ? 'formula' and it ? 'unit_price' and it ? 'waste_pct'
                                 and it ? 'section_multiplier' and it ? 'line_cost' and it ? 'quantity'))
                                                                                              as lines_complete,
         coalesce(jsonb_typeof(r->'input_state'->'ui_snapshot') = 'object', false)            as has_snapshot,
         coalesce(jsonb_array_length(case when jsonb_typeof(r->'input_state'->'repair_lines') = 'array'
                  then (select jsonb_agg(l) from jsonb_array_elements(r->'input_state'->'repair_lines') l
                         where l->>'kind' = 'stock') end), 0)                                 as stock_lines
    from c
)
select month, body, repair,
       count(*)                                                                         as pending,
       count(*) filter (where has_items and has_totals and (repair or (has_vars and lines_complete)))
                                                                                        as freezable,
       count(*) filter (where not repair and has_snapshot)                              as with_snapshot,
       sum(stock_lines)                                                                 as repair_stock_lines,
       string_agg(quote_number, ' ' order by quote_number)
         filter (where not (has_items and has_totals and (repair or (has_vars and lines_complete))))
                                                                                        as not_freezable_quotes,
       (select count(*) from formulas where is_active)                                  as library_formulas
  from f
 group by month, body, repair
 order by month, body;
