# ADR 0036 — §9 floor-doc event integration, Phase 1: server-authoritative transitions

**Status:** Accepted (Michael ratified the three design forks 9 Jul 2026: server-confirmed
drags; full chokepoint integration across the arc; admin-only journaled reset)
**Date:** 2026-07-09

## Context
The /plan floor was a client-owned JSON document (plan_floor_state, one row): browsers
mutated local state and PUT the WHOLE document back. Consequences, all observed in
production during the v1.40.x week: two-planners last-writer-wins clobbering (8 s poll
race), a mock-mode session able to seed-stomp the shared floor (onPersist was never
mode-gated), zero audit of floor actions, an unbounded QC list, and a family of
ghost/limbo bugs (V-1 Wednesday, job 9934) born from the doc and the DB being parallel
worlds (the v1.40.0 §9 debt).

## Decision (P1, v1.41.0)
ONE endpoint — POST /api/plan/floor-transitions — applies a typed transition server-side:
SELECT FOR UPDATE on the singleton row → engine-guard ports validate (services/floor.py,
line-for-line against productionFlowEngine.ts, which remains the MOCK-mode implementation)
→ doc mutated + Z-format stamps → version++ → floor_events journal row (house audit idiom:
job_number snapshot, SET NULL FKs, user_name snapshot, doc_version) → one commit. 404/409/
422 roll everything back. Clients never send versions: staleness is caught ENTITY-level
("is it where you say it is"), so concurrent drags of different items both succeed.
The engine's lazy cut-prune moved server-side (journaled as cut_pruned) — with the PUT gone
it had to, or orphan cut entries would strand forever.

PUT /api/plan/floor-state is DELETED — the clobber and the mock-stomp die structurally.
The engine posts transitions pessimistically in live mode (single-flight, .pend pulse,
toast + snap-back on rejection, merge crescendo only on server confirm); mock/offline mode
keeps the exact local behavior. Admin-only floor reset (admin.floor-reset — the FIRST
admin.* key enforced server-side) with typed confirm, journaled, version monotonic.

The DOC SHAPE IS UNCHANGED byte-for-byte: every reader (plan_status labels, drawer clocks,
planning occupancy/pool) is untouched in P1 — near-zero blast radius.

## Next phases
P2 (v1.41.1): the domain chokepoints join the SAME transaction via commit=False threading
(record_body_attached on confirm-merge, record_moved_to_awaiting_qa on dispatch,
record_panels_arrived_in_bay/assign_assembly_bay/clear/return on the bay legs); bay lane N
maps to the Nth active assembly_bays row by sort_order; declare-cut realizes
planning_slots.status='completed'; one admin floor-reset at cutover aligns worlds.
P3 sketch: readers move off doc-parsing onto floor_events/chokepoint queries; the QC zone
derives from awaiting_qa records (fixing the unbounded doc list); the doc slims to layout.

## Rollback
Git revert restores the PUT + local engine; migration 0037 is additive (floor_events +
version may stay or downgrade). The journal is append-only — house posture, rows persist.
