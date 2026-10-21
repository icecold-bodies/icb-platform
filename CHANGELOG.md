# Changelog

All notable changes to the ICB Platform monorepo are recorded here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## v1.62.0 — 2026 October (deploy line `backport/v1.39-base`): a re-opened quote is the saved quote

What changes for the people who quote:

- **Opening a saved quote shows it exactly as it was saved.** Every line, price and total comes from the quote's own
  saved copy, not from today's template or today's prices. Before this, re-opening a quote quietly re-costed it, so a
  quote could show different lines or a different total from the one the customer was sent (N10022/10/2026 lost its
  ROOF plywood and PU lines this way).
- **A quiet line under the edit banner says how today's prices differ** ("Saved prices of <date> · today's prices
  would change the total by …"). "View changes" lists, line by line and per section, what re-pricing the quote today
  would change. Nothing is saved by looking.
- **The options and the chassis are locked while a saved quote is open at its saved prices.** To change them, click
  "Update to today's prices": the quote is re-priced from today's template and prices and must be saved as a **new
  revision**; the old revision stays as it was.
- **Repairs follow the same rule:** a re-opened repair keeps its saved line prices.
- **Overwrite saves over a quote only from its saved-prices view;** a quote moved to today's prices saves as a new
  revision, "so the one the customer has stays as sent". Every refusal says in plain words what to do next (for a
  costing that breaks Burt's rules: re-open it, click "Update to today's prices", remove the breach, save as a new
  revision, then accept the new revision).
- **A browser tab opened before the update** still runs the old calculator: an Overwrite from it is refused with
  "This page is out of date. Reload it (Ctrl+F5) and save again. Your quote has not been changed." Reload the page
  after the update.

Nothing else moves: no database change (alembic stays 0053), no new package, no MES (SPA) change, and how a NEW
costing prices is unchanged — the costing audit reads the same before and after (0 FLAG / 115 ACCEPTED, smoke 0 / 33).
The calculator's script is `calculator.js?v=191`. One new route, `POST /api/calculations/{id}/reprice-preview`, which
needs a signed-in user like every other.

Built by RT8 (#221, #224, #225, #226); released by RT9 (prod runbook: `docs/runbooks/prod-deploy-v1.62.0.md`).

## [Unreleased] — v4.30 Cost Calculator Unification Cutover

### Added
- Ported the 7-Jun edit-functionality release from `GRP-Costing-System` (`d2da5bf` + `14e6817`): per-quote
  **discount** (percent/amount → Net Total headline), **edit pending costings** (in-place overwrite or a new
  revision with faithful state replay), and **collapsible Excel Cost-Breakdown** sections with header subtotals.
- Migration **0015** — guarded (`ADD COLUMN IF NOT EXISTS`) discount columns on `icb_costings.calculations`
  (`discount_kind/input/amount`, `net_total`); a no-op on the shared prod DB, materialised on icb's own DBs.
- MES Costings surface `net_total` as the headline with a "before discount" breakdown when discounted
  (§0.2a); the Planning Board keeps pre-discount `selling_zar` as a workload metric.
- Calculator: a **new** costing defaults the Ratio to **55%**; edit/copy restore their saved/source ratio.
- `docs/migrations/v4.30-drift-audit.md` (drift register), `docs/runbooks/faje-deploy.md`
  (deploy/env/rollback), **ADR 0017** (cutover + parallel-codebase pattern), and a per-role cutover smoke
  journey (admin + sales).

### Notes
- Single source of truth: the live faje.co.za Cost Calculator moves to `icb-platform`; `GRP-Costing-System`
  is retired (archived). The HostAfrica Git-source switch + env mapping are the paired cutover step (§3.4),
  gated on ticket #2462727. `/calculator` stays byte-identical to v4.29 except the documented ports + the
  55%-ratio enhancement.

## [Unreleased] — Phase 1 foundation (WO v4.12)

### Added
- Monorepo skeleton: `backend/`, `frontend/`, `shared/`, `deploy/`, `db/`, `docs/`, `scripts/`.
- Cost Calculator imported into `backend/` (FastAPI + Jinja2), as-is.
- React MES mockup imported into `frontend/` (React 18 + Vite), served at `/mes-app/`.
- Single local PostgreSQL database `icb` with schemas `icb_costings` + `icb_mes`
  (`deploy/postgres/init.sql`).
- Alembic migration chain: `0001` baseline + `0002` `branches` table and nullable
  `branch_id` columns (backfilled to JHB).
- Environment-variable contract via `backend/app/config.py` (pydantic-settings) and
  `.env.example`; pluggable auth (`auth/`) and storage (`storage/`) Protocol interfaces.
- Windows-first dev scripts and a Linux + Windows CI matrix.
- ADRs 0001–0004.

### Notes
- Phase 1 is **local-dev only**. The live Cost Calculator at faje.co.za is unchanged.
