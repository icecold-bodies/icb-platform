# ADR 0033 — V/P day-slot scheduling (A10): day_of_week on planning_slots + the 7-day sub-grid

**Status:** Accepted (Simeon ratified the A10 v0.2 design 6 Jul 2026; BA-coordinator ratified the
§3.0 discovery synthesis 7 Jul 2026)
**Date:** 2026-07-07
**Numbering note:** cut as 0033 on the `backport/v1.39-base` deploy line — `main`'s ADR chain
already holds 0029–0032 (v4.36c/d/e era), so the next shared-safe number is used to avoid a
same-number/different-content collision when the lines reconcile (the 0030/0031 migration-collision
lesson applied to docs).

## Context

Each V/P bay (Vacuum + Press cutting stations) finishes one panel set per day, but the Planning
Cockpit scheduled per **week** per bay — planners couldn't express *which day* a cut happens, and a
5-job week looked identical to a 1-job week. Simeon (Materials/Planning/Stores) asked for day-level
slots: 5 weekday slots per bay-week plus 2 optional **weekend overtime** slots that stay visually
skinny until booked (A10 v0.2 mockup, ratified).

Discovery ground truth that shaped the design (7 Jul):

- The live grid is **`PlanningCockpit.tsx` embedded on `/plan`** (PlanningBoard.tsx is dead code;
  `/planning*` routes redirect). V/P bays are **8 hardcoded frontend strings** (`V-1..V-5`,
  `P-1..P-3`) and free text in `planning_slots.bay` — deliberately not a table (0016 note).
- `planning_slots` keyed on (free-text `bay`, `week` DATE = Monday) with **no DB uniqueness**;
  cell exclusivity is app-enforced at the service `_occupied` chokepoint.
- The chassis-ETA gate compared against the target **week's Friday 23:59:59 UTC**; a
  chassis-received signal bypasses it; a missing ETA blocks.
- The planner grid had **no 4-state health computation** — a fixed green border plus an amber
  "ETA committed" pill from `getChassisState`.

## Decision

1. **Schema (migration 0034):** add `planning_slots.day_of_week INTEGER NULL` with DB CHECK
   `day_of_week IS NULL OR 0..6` (0=Mon .. 6=Sun); backfill existing rows to Monday (0), the same
   date their `planned_start_date` already carried. Inspector-guarded, idempotent, clean
   up→down→up. **No DB uniqueness added** — exclusivity stays at the service chokepoint, now keyed
   on (bay, week, **day**), with legacy `NULL` days normalising to Monday in code. This matches the
   existing "bay state is app-derived, not DB-constrained" pattern and keeps stray legacy rows from
   violating a constraint at migration time.
2. **API:** `POST /api/planning-slots` and `POST /api/planning-slots/{id}/move` accept optional
   `day_of_week` (pydantic 0..6). **Omitted → legacy weekly semantics are byte-identical**: stored
   as Monday, ETA-gated against the week's Friday (schedule) or the slot's kept day (move keeps the
   current day on a week-hop). Day-aware requests are ETA-gated against the **slot day's end** —
   weekends get no special allowance (§8.2.7: a Saturday slot accepts an ETA up to that Saturday).
   `planned_start_date` becomes the slot DATE (Monday + day) — for legacy calls, unchanged.
3. **Grid:** each bay-week cell is a 7-column CSS sub-grid — `repeat(5, minmax(64px,1fr)) 24px
   24px` — where an occupied weekend column flexes to `1fr` (the A10 **dynamic weekend width**
   pattern, computed per bay-week from visible occupancy; the week header aggregates across bays).
   Today's column carries a subtle red tint. The bay-label column adds the lane type and a
   **utilization dot** (weekday bookings, first visible week: green 5/5 · amber 2–4 · grey 0–1,
   weekend bookings suffixed separately).
4. **Compact job card (~82px):** health **border-left + dot** via the existing chassis-state
   machinery projected onto the slot day — received → green, ETA on/before the slot day → amber,
   ETA **after** the slot day → red, no ETA → grey; a keyword-classified **body-type pill**
   (Chiller/Freezer/Dry Freight/Insulated/Repair — `body_type` is free text, so classification is
   lexical with a no-pill fallback), the parsed length label, and a **WKND** corner marker on
   weekend cards. Card testids/drag payloads (`cockpit-slot-cell`, `application/x-panel-job`) are
   unchanged for the A06 floor + journey contracts.
5. **Drag-drop:** drop targets are the day-cells; a 409 (occupied) or 422 (ETA gate) flashes the
   exact day-slot red (the visual reject cue) — the 422 detail toast still comes from the shared
   API-error path.

## Consequences

- Two jobs can now share a bay-week on different days — the pre-0034 "one job per bay-week" rule
  is intentionally retired; capacity footers count day-slots against 8 bays × 5 weekdays.
- Weekly-era callers (older scripts/tests) keep exact pre-0034 behaviour; their slots land on
  Monday. Anything reading `planned_start_date` now sees the true day for day-aware bookings.
- The weekend columns make overtime *visible but unobtrusive*; a booked weekend widens its row's
  weekday columns slightly relative to other rows (accepted in the mockup — rows flex
  independently, the header tracks the widest state).
- Health red now means "the plan can't be met as scheduled" (ETA past the slot day) — a state that
  previously hid inside the amber pill until someone opened the drawer.
- Server `capacity` (bay-per-week) is unchanged; the embedded cockpit derives day-level Filled /
  Empty from visible cards instead (single-location rule preserved).

## Verification

- Migration: up→down→up round-trip on the shared dev DB + CI's `upgrade head → downgrade base →
  upgrade head`.
- `tests/test_planning_day_slots_api.py` — day-aware gate unit matrix (weekday/weekend/legacy),
  (bay, week, day) occupancy incl. legacy-NULL normalisation, move day-semantics,
  planned-start-date, request validation, board payload.
- `tests/journeys/test_planning_day_slots_journey.py` — rendered day placement (`data-day`),
  WKND marker + weekend expansion, weekend ETA gate at the drag contract, weekend
  drag-back-to-pool.
- Existing planning suites (roles/gates/window: `test_planning_session_roles_api`,
  `test_v4_29_upstream_fixes`, drag/ack/unschedule journeys) pass unmodified — the
  backward-compat contract above is what they pin.
