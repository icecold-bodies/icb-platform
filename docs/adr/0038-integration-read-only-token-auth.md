# ADR 0038 — Read-only integration bearer-token auth (ERP enablement)

**Status:** Accepted (ERP_MES_INTEGRATION_PACK_v1.0 ratified 21 Jul 2026; Michael full-push)
**Relates to:** ADR 0013 (icb_sap read-only landing zone), ADR 0008 (API surface conventions),
docs/handoffs/ERP_MES_INTEGRATION_PACK_v1.0.md (§2 auth contract, §4 endpoint allowlist)

## Context

The in-house ERP (Marnus, Group IT — NestJS/PG16 at 192.168.0.252) needs to READ the MES
API server-to-server. Auth was session-only: `deps.get_current_user` reads the `session_id`
cookie, and every `/api/*` route depends on a session user — there was no
`Authorization: Bearer` support anywhere. The ratified Pack contracts a scoped read-only
bearer token (§2) over a fixed GET allowlist (§4), with OAuth2 client-credentials free to
supersede it later without changing any endpoint. Two of the contracted paths did not
exist: floor state was only at `/api/plan/floor-state`, and the `icb_mes.floor_events`
journal (written by every floor transition since v1.41.0) had no read endpoint at all.

## Decision

1. **Tokens in env, feature-off by default.** `INTEGRATION_API_TOKENS` — comma-separated
   `token=name` pairs (`abc123=erp`), parsed per-request off `settings` with a memo.
   Empty/missing = off: every bearer request is rejected and session auth is untouched.
   Values are exchanged in person (Michael ↔ integrator), never committed; rotation =
   env change + restart. Comparison is `secrets.compare_digest` across ALL configured
   pairs (no early break); the presented value is never logged or echoed.
2. **The allowlist IS the opt-in — no path table.** An endpoint grants token access by
   adding the `@integration_readable` marker under its `@router.get(...)` (or, in the one
   legacy inline-auth case — `GET /api/calculations/{id}` — calling
   `integration_identity_if_bearer` before `get_current_user`). Handlers deliberately KEEP
   `Depends(require_user)`: the house test idiom overrides `require_user` via
   `app.dependency_overrides`, and a wrapper dependency silently detaches every marked
   route from those overrides (the first CI run proved it — dozens of existing suites
   401'd). `require_user` consults the marker on the routed endpoint
   (`request.scope["endpoint"]`) before session resolution. Grep `@integration_readable`
   to enumerate the live allowlist. No middleware auth.
3. **Deny-by-default at the session chokepoint.** `deps.get_current_user` calls
   `reject_integration_bearer` first: a bearer-presenting request NEVER falls through to
   session auth — 401 for an unmatched token, 403 for a valid token on anything that
   didn't opt in (all writes, admin, session, auth, and UI routes, including the
   `/mes-app/*` SPA gate). Because require_user / require_admin / require_perm and every
   legacy inline caller flow through this one function, coverage is total by construction.
4. **Synthetic read-only identity, zero permissions.** A matched token resolves to an
   `IntegrationIdentity` (role `integration`, `id=None`, `_perm_cache=frozenset()`): no
   user row, no session row, no CSRF involvement (GETs are CSRF-exempt), and every
   `user_can` check answers False via the existing perm-cache mechanism — permission-gated
   fields and routes deny without a DB round-trip. Every allowlisted read the Pack
   contracts is plain require_user-level, so nothing is lost.
5. **The two missing contract paths become real, read-only.** `routers/floor_read.py`
   adds `GET /api/floor/state` (delegates to the same handler logic as
   `/api/plan/floor-state` — one payload source; the SPA path untouched) and
   `GET /api/floor-events` (first reader over the journal: ascending-id incremental pull
   with `since_id`/`last_id`, job/type filters, capped limit). Floor transition logic is
   byte-identical.
6. **Observability rides the existing request logger.** The token path stamps
   `request.state.integration_name` (the NAME, never the token; `invalid` for unmatched)
   and `diagnostics.install_request_logger` appends `integ=<name>` to its one-line-per-
   request log — method, path, status, integration identity on every token request.

## Consequences

- Marnus's ERP can read the full Pack §4 surface day-one with one env var on the MES
  side; browser behaviour is byte-identical (locked by tests: valid/bad/absent token ×
  allowlisted/write/admin/session/UI matrix + feature-off, in
  `tests/test_integration_token_auth.py`).
- The read grant is endpoint-scoped, not field-scoped: an integration token sees what any
  signed-in user sees on those GETs (including costing prices on `/api/calculations/{id}`
  — contracted in Pack §4). Field-level scoping, more identities, or OAuth2 are additive
  follow-ups on the same seam.
- `icb_sap` stays exactly per ADR 0013 (read-only from app code; the ERP loader replaces
  the ETL as sole writer) — this ADR adds the *outbound* read surface only.
- New writes must NEVER carry `@integration_readable`; the resolver hard-ignores non-GET
  methods as a belt, but the review rule stands: writes stay session-gated.
