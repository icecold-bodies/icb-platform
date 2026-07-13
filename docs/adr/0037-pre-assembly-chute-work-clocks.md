# ADR 0037 — A11 Pre-Assembly Chute: per-card work clocks over the floor doc

**Status:** Accepted (Simeon-ratified mockup A11 v0.2, 13 Jul 2026; Michael full-push)
**Relates to:** ADR 0036 (floor-doc event integration), migration 0036/0038 (stage thresholds)

## Context

Each Pre-Assembly bay takes ~2h to turn a dropped panel-set into an assembled body, but the
/plan lane rendered cards by hand-dragged track position — no time signal. Simeon ratified a
"chute": cards auto-advance by their own elapsed-in-stage time, pulse when ready, and wait
for the planner to drag them into Merge (human-in-the-loop; no auto-advance to Merge).

## Decision

1. **Elapsed source = the existing doc stamp.** `body.enteredAt` (server-stamped by the
   v1.41.0 `start_body` transition) already feeds the v1.40.8 drawer clocks and the v1.41.1
   breach flags. The chute reads the same stamp — one truth, no new schema.
2. **Threshold = production_stage_thresholds.pre_assembly**, realized from the 0036
   placeholder (40h) to the ratified **2.00h by data migration 0038** — guarded so an
   admin-tuned value is never overwritten. Admin surface unchanged (verified: the existing
   Production Stage Thresholds CRUD edits it; a tune propagates to the chute within one
   8s floor poll — the threshold + a `server_now` skew anchor now ride GET /floor-state).
3. **Two new journaled transitions** through the ONE v1.41.0 chokepoint
   (`POST /api/plan/floor-transitions`) — deliberately NOT bespoke REST routes, matching
   the established mechanism:
   - `reset_timer {id, fraction 0..1}` — drag-BACK re-arms `enteredAt` so elapsed =
     fraction × threshold. Forward drags are visual-only (bring-to-front) and never
     reach the server.
   - `toggle_hold {id}` — hold snapshots elapsed into `heldElapsedS` (+`held`, `heldAt`
     — additive doc fields, loadState-tolerant); resume re-bases
     `enteredAt = now − snapshot`. Gate: `planning.schedule` (ratified).
4. **Hold vs Health Check honesty split (deliberate):** the chute shows frozen WORK time
   during a hold; the drawer clock and v1.41.1 breach flags keep reading the raw stamp
   (WALL time). A long-held body still occupies a bay and still breaches — Health Check
   stays the honest escalation path and its logic is untouched.
5. **Merge block untouched** (Michael's boundary): the `.m-block` markup, confirm/dispatch
   handlers, and the P2 chokepoints are byte-identical; `readyBody()`'s definition changed
   from track-position (`prog ≥ .95`) to time-ready (elapsed ≥ threshold), which only
   changes WHEN the existing merge hint appears, not what it does.

## Consequences

- floor_events gains two event types (`reset_timer`, `toggle_hold`) with full old/new
  stamps in `details` — audit-complete, replayable; no floor_events schema change.
- The doc shape stays byte-compatible ({v, pre, qc, cut, cutAt, consumed, mergedJobs,
  mergedChassis}); `held/heldAt/heldElapsedS` are additive per-body fields every existing
  reader ignores.
- The lane's old position machinery (`pos`, guides, `move_body` desired) stays server-side
  for cross-bay moves; `pos` is vestigial for rendering.
- Client tick is 15s (≈0.2% of the 2h threshold per step); positions are computed against
  `server_now` from each poll, so client clock skew cannot move cards.
