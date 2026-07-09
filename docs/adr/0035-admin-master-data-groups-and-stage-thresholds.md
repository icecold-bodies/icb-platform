# ADR 0035 — Admin Master-Data groups + permission tags, and production-stage thresholds

**Status:** Accepted (Michael's WO 8 Jul 2026; clock semantics, scope, and granularity ratified
in structured Q&A the same day; plan approved before implementation)
**Date:** 2026-07-09
**Numbering note:** cut as 0035 on the `backport/v1.39-base` deploy line (0034 = the costing
contact snapshot), following the 0033 shared-safe numbering convention.

## Context

The SPA Admin area ("Master data") had grown to 14 items rendered as one flat, icon-less text
list; `/admin` and the TopNav both landed on `spec-options`; `/admin/feedback` was an orphan
route linked from nowhere; and nothing tied a menu item to a stable identity that user-role
work could later grant against. Separately, planners had no way to see whether panels have
been in a Vacuum/Press bay longer than they should: the WO asks for admin-captured per-stage
duration thresholds (vacuum=8h, press=4h) with a live progress bar per scheduled job card.

## Decisions

### 1. Grouped, tagged, alphabetical admin menu
Three groups — **Monitor & operate** (O), **System administration** (S), **Manufacturing
data** (M) — alphabetical by title inside each. Every item carries:
- **`permKey` = `admin.<route-slug>`** — the stable identity, mirrored VERBATIM as 16 additive
  `PERMISSION_CATALOGUE` entries (category `admin`, empty default_roles: role `admin` is the
  code wildcard and needs no rows; the rows exist so the BA can grant single pages to other
  roles). The startup bootstrap heals any environment (the 6-Jul prod-permissions lesson).
- **`displayId`** (O1…O6 / S1…S6 / M1…M4) — the human tag on the sidebar badge. **Frozen
  forever**: items keep alphabetical placement, but a badge never renumbers; future items take
  the group's next free number, so alphabetical position and number may diverge over time —
  that is the accepted trade-off (identity lives in permKey, not the badge). In the mono badge
  font the O prefix can read as a zero; tolerated — the badge tooltip shows the full permKey.
- A lucide icon (house icon set; no new dependencies).

**Visibility** = `isAdmin` wildcard → the existing QC-roles exception → `hasPermission(permKey)`.
The load-bearing edge: the SPA's `hasPermission` is **permissive by default** for keys outside
the 15 server-tracked mutation keys — the `admin.*` namespace is now explicitly **deny-by-
default** in live mode (AppDataContext), otherwise every user would see the whole menu.
**Server-side per-page enforcement is deliberately deferred** to the roles release: today every
`/api/admin/*` endpoint stays `require_admin`, so a granted non-admin sees a menu item whose
API still refuses writes — safe-closed in both directions. The TopNav Admin entry likewise
stays `adminOnly` until the roles release decides nav exposure.

**Health Check is the Admin landing** (`/admin` redirect, TopNav target, module fallback), and
FeedbackInbox joined the module as O1 (URL unchanged — `/admin/feedback` now resolves through
`/admin/:resource`).

### 2. Production-stage thresholds: stage-generic table, per-row workday_start
`icb_mes.production_stage_thresholds` (migration 0036): `stage_code` UNIQUE ('vacuum','press'
seeded at 8h/4h), `threshold_hours` NUMERIC CHECK > 0, `workday_start` TIME default 07:00,
`is_active`, audit cols. Future stages (assembly, qc…) are **new rows, not schema changes**.
`stage_code` is deliberately decoupled from `planning_slots.lane` strings — the mapping
(`'panelshop'` → `'press'`, bay-prefix fallback) lives in ONE place,
`plan_status.stage_key_for`, shared by the floor-status derivation and the board clock.

**workday_start is a column on each stage row** (not a singleton settings table, not a magic
row): the generic AdminCrudTable edits the whole feature in one form (a `time` field type was
added), both seeds carry 07:00 so the ratified global semantic is the shipped default, and
per-stage start times are a free superset.

### 3. Clock semantics (ratified)
The clock starts at **`workday_start` on the slot's scheduled day** (week + day_of_week;
legacy NULL-day rows ≡ Monday, byte-identical to every other renderer) and runs **wall-clock
24/7** — weekend slots are deliberate overtime and count fully. Moving a slot re-derives the
clock from the new (week, day, lane) statelessly; unschedule/revert simply delete the slot row
— **no persisted clock state exists anywhere**.

### 4. Transport + skew model
Thresholds ride the existing **`/api/planning-board`** response (already `require_user`,
polled 30s + focus): each visible scheduled V/P slot gains a `progress` object with
`threshold_hours` and a **server-computed `elapsed_hours`** (negative = pending). Progress is
attached AFTER the `_progressed_job_ids` filter, so a lingering slot whose job moved on can
never grow a bar. The client ticks forward from its own fetch moment
(`PlanningContext.lastUpdated`) — **client and server clocks are never compared**, so absolute
skew cannot bend a bar; the 30s poll re-syncs any rate drift. `started_at` is display copy
only ("Starts Thu 07:00"). Naive server-local datetimes throughout; the server and factory
share a timezone and South Africa has no DST — if hosting ever moves to UTC, the single fix
point is the `datetime.now()`/`combine` pair in `_attach_stage_progress`.

Tones mirror the house AgeingPill/KanbanTV language: green <75%, amber 75–100%, red >100%,
pending (empty track) before start. Rendered as a 3px bottom strip on the cockpit day-slot
card + a `SlotStageClock` line in the slot drawer (both drawer surfaces — the embedded /plan
drawer mounts outside the cockpit tree, so the fetch moment is passed as a prop, not context).

## Consequences
- The BA can box any single admin page into a role by adding one grant row for its
  `admin.<slug>` key — no code change, no redeploy (bootstrap-healed everywhere).
- V/P dwell visibility is live for planners with zero new polling and zero persisted state;
  later stages need only a threshold row + (for post-V/P stages) entry-time stamps in the
  floor document — explicitly out of scope this release (the doc has no per-item timestamps).
- Rollback is fully decoupled: old SPA ignores the new JSON; new SPA without the API renders
  no bars; `alembic downgrade 0035` drops the table; orphan `admin.*` Permission rows are
  harmless (the bootstrap never deletes).
