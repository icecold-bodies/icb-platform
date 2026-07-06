# ICB Platform — Manufacturing Execution System

Unified codebase for **Icecold Bodies (ICB)**: the Cost Calculator (legacy calc, iframe-wrapped) and the new native React Manufacturing Execution System (MES), served together from a single FastAPI service.

> **Current release:** v1.40.0 (Phase 1 launch — 5 Jul 2026)
> **Live URL (on-premises, ICB network):** `http://192.168.0.251:8000/mes-app/`
> **Access:** ICB office network (LAN) or VPN for off-site users

---

## 1. What is the ICB MES?

The ICB MES is the digital operations system for Icecold Bodies — a South African manufacturer of refrigerated truck bodies. It replaces the earlier paper + spreadsheet + email workflows with a single connected system that tracks a body from **quote to delivery**.

The system covers:
- **Costing & quoting** — build a quote for a customer's trailer body with formulas, BOMs, and margin controls
- **Pre-Job Card handoff** — Sales and Planning sign-off before a quote becomes a production job
- **Planning Board** — schedule jobs across bays and weeks, drag-and-drop workflow
- **Chassis Management** — track truck chassis records through the pipeline
- **Pre-Assembly / Merge / QC** — production floor state tracking (bay lifecycle)
- **Materials & Stores** — stock counts, discrepancies, forecast, purchase orders
- **Reporting** — dashboards, KPIs, exports

---

## 2. Who uses it?

| Role | Person(s) | Primary responsibilities |
|---|---|---|
| **Sales Rep** | Burt Smith | Creates costings, signs off Pre-Job Cards as Sales |
| **Planner** | Deon | Schedules jobs on the Planning Board, signs off Pre-Job Cards as Planner |
| **Materials / Planning / Stores** | Simeon (planner@icecoldgrp.co.za) | Tracks bays, monitors materials, stock counts, receives all Submit-for-Check emails as CC |
| **QC Inspector** | Kenny | Runs QC inspections, sign-offs on completed bodies |
| **Estimator** | Nadie | Creates pre-job cards, submits for check |
| **Admin** | Michael | System configuration, user setup, permissions, deployments |

Every user logs in with a username + password. Roles are:
- `admin` — full system access, user setup, all configurations
- `sales` — costings, Sales sign-off on Pre-Job Cards
- `planner` — Planning Board, Planner sign-off, materials read-only
- `production` — read-only for production floor tracking (chassis, bays)

---

## 3. Main features / modules

### 3.1 Costings
- Create new costings via the Cost Calculator (Body Type, Doors, Insulation, Ratio, Margin)
- The BOM (Bill of Materials) is built from formulas (e.g. skin plates, insulation, mounting cleats, floor plates)
- Approve & Save creates an accepted costing which becomes eligible for a Pre-Job Card
- Edit-pending costings supported (reopens in the calculator)
- Right-click "Edit permanently" preserves the full costing state across the round-trip
- Real BOM data displayed (no more "illustrative" placeholder)
- DRD/SRD rear-door insulation follows the door type selection (self-heals; both-zero warning cannot appear in normal ops)
- FRONT/SIDES/ROOF/FLOOR EPS/PU thicknesses follow the selected radio (v1.39.10 invariant enforced)

### 3.2 Pre-Job Cards
- Nadie (Estimator) fills in the pre-job card details (customer notes, insulation specs, fridge unit choice, sign-off panel)
- On Submit for Check, **individual personalized emails** are sent to:
  - Sales signer (Burt) — role-scoped link to `/mes-app/prejob/{id}/signoff/sales`
  - Planner signer (Deon) — role-scoped link to `/mes-app/prejob/{id}/signoff/planner`
  - CC recipients (Simeon + any additional CCs) — lighter email with link to view the pre-job card in MES
- Sales and Planner sign off in the MES via the deep-link
- Once both sign-offs are recorded, the job is confirmed and becomes a production job

### 3.3 Planning Board
- Weekly slot view of production capacity
- Drag & drop unscheduled jobs onto planning slots
- Chassis ETA gate: jobs can't be scheduled before chassis arrival is confirmed
- Bay model showing Parking → Pre-Assembly → Merge → Awaiting QA
- Cockpit view for cramped-layout scenarios

### 3.4 Chassis Records
- Chassis attributes (VIN, make/model, dealer, customer, tail-lift code, body-gap)
- Sole-editor chokepoint: only admin/planner can edit chassis fields; audit trail per field change
- Optimistic-lock (etag) prevents concurrent-edit corruption
- Audit trail viewer shows who changed what and when

### 3.5 Pre-Assembly / Merge / QC
- Pre-Assembly lane: bodies are built from panels (Vacuum/Press → Pre-Assembly bay)
- Merge lane: body meets its chassis
- QC bay: Kenny inspects, signs off
- Dispatch: body ready for customer collection

### 3.6 Materials & Stores
- Stock counts (cycle counting)
- Discrepancy tracking (buyer queue)
- PO suggestions (with supplier override + bulk-raise)
- Demand forecast (materials rollup)
- Supplier master

### 3.7 Admin
- User Setup: create/edit users, set email addresses, assign roles
- Configurable Body Templates (post-Phase 1)
- Configurable Pricing Formulas (post-Phase 1)

---

## 4. How to access

### 4.1 Production URL
**Primary URL:** `http://192.168.0.251:8000/mes-app/`

Access options:
- **On ICB office network:** open directly in browser
- **Off-site (working remotely, e.g. Michael):** connect to ICB VPN first, then open URL
- **On-site tablets (Shop Floor, Kanban TV):** open direct URL

### 4.2 Login
- Enter your username (e.g. `burt`, `deon`, `simeon`, `nadie`, `kenny`, `admin`)
- Enter your password (set via /admin/users)
- The MES remembers your session; you'll stay logged in until you log out

### 4.3 Landing pages by role
- **Admin (Michael):** lands on `/production` dashboard
- **Sales (Burt):** lands on `/costings` list to see current quotes
- **Planner (Deon), Materials (Simeon):** lands on `/planning` to see the board
- **QC (Kenny):** lands on `/admin/qc` for inspection queue

### 4.4 Key screens
| Screen | Path | Who |
|---|---|---|
| Costings dashboard | `/mes-app/costings` | Sales, Estimator, Admin |
| New Costing (calculator) | `/mes-app/costings/new` | Sales, Estimator |
| Costing detail | `/mes-app/costings/{quote_number}` | Any |
| Pre-Job Card | `/mes-app/prejob/{id}` | Any |
| Pre-Job sign-off (Sales) | `/mes-app/prejob/{id}/signoff/sales` | Sales |
| Pre-Job sign-off (Planner) | `/mes-app/prejob/{id}/signoff/planner` | Planner |
| Planning Board | `/mes-app/planning` | Planner, Materials, Admin |
| Planning Cockpit | `/mes-app/planning/cockpit` | Planner |
| Chassis list | `/mes-app/chassis` | Any |
| Chassis detail | `/mes-app/chassis/{id}` | Any (edit limited to admin/planner) |
| QC inspection queue | `/mes-app/admin/qc` | QC, Admin |
| Materials catalogue | `/mes-app/materials` | Materials, Admin |
| Kanban TV (wall display) | `/mes-app/kanban/pre-assy` | Production floor |
| Admin User Setup | `/mes-app/admin/users` | Admin only |

---

## 5. Key workflows (end-to-end)

### 5.1 Quote → Job → Delivery

1. **Estimator (Nadie)** creates a new costing in `/costings/new` — enters trailer body dimensions, door type, insulation, ratio, margin
2. **Nadie** submits the costing (status = Pending), edits pending as needed
3. **Sales (Burt)** approves the costing → status becomes Accepted
4. **Nadie** creates a Pre-Job Card from the accepted costing → status = Pre-Job Sent
5. **Nadie** hits Submit for Check → individual personalized emails go to Burt (Sales) + Deon (Planner) + Simeon (CC)
6. **Burt** clicks the Sales deep-link → signs off as Sales
7. **Deon** clicks the Planner deep-link → signs off as Planner
8. **Once both sign-offs recorded** → status = Pre-Job Confirmed → becomes a Production Job
9. **Deon** schedules the job on the Planning Board
10. **Chassis arrives** at ICB → Chassis Received recorded → job proceeds
11. **Production floor** builds panels (Vacuum/Press), drops onto Pre-Assembly bay → body builds
12. **Chassis merges** with body at Merge bay
13. **QC (Kenny)** inspects → signs off
14. **Dispatch** → customer collects

### 5.2 Pre-Job sign-off workflow (email → decision → MES)

1. Nadie hits Submit for Check
2. Sales signer receives email: "Pre-job check requires your Sales sign-off — Job {job_number}"
3. Body reads: "Hi Burt, [job details]. The PDF copy is on the URL page for records (download it from the MES system)."
4. Link points to `/mes-app/prejob/{id}/signoff/sales`
5. Burt clicks, logs in, reviews the card, clicks Sign as Sales
6. Same flow for Planner (Deon)
7. Simeon (CC) receives lighter email with just a link to view — no sign-off action

### 5.3 Blank slate reset (for new user onboarding)

An admin script clears demo/test data while preserving users, branches, roles, and lookup tables:

```bash
python -m backend.scripts.wipe_demo_data           # dry-run
python -m backend.scripts.wipe_demo_data --apply   # applies
```

Used before onboarding a new operator (e.g. Simeon's first day).

---

## 6. System architecture (light overview)

```
icb-platform/
├── backend/        FastAPI app (Python 3.12+), Alembic migrations, tests
├── frontend/       React 18 + TypeScript + Vite (the MES UI)
├── deploy/         PostgreSQL init + docker (future)
├── docs/           ADRs, release notes, handoffs, runbooks
└── scripts/        setup / start / start-dev
```

- **Single PostgreSQL 16 database** (`icb`) with schemas: `icb_costings` (quotes + calc), `icb_mes` (production, planning, materials, chassis), `icb_sap` (read-only, integration mirror), `icb_feedback` (v4.38 feedback portal)
- **Single FastAPI service on port 8000** — serves the legacy Jinja calc at `/`, `/calculator`, `/mes/*` AND the React MES at `/mes-app/*`
- **All configuration via `backend/.env`** — SMTP, Twilio, Anthropic API key, database URL, session secret, etc.

---

## 7. Version history (major milestones)

| Version | Date | Highlights |
|---|---|---|
| **v1.40.0** | 5 Jul 2026 | Plan module + persisted shared floor + drawer + admin page + Decline + costing summary + defect fixes + Planning-menu retirement |
| v1.39.10 | 3 Jul 2026 | EPS/PU thickness invariant heal (all pairs, all 27 trailers) |
| v1.39.9 | 3 Jul 2026 | Costing state snapshot across trailer-URL round-trip |
| v1.39.8 | 3 Jul 2026 | CSS theme leak fixes (Dashboard nav, Cancel Edit) |
| v1.39.7 | 2 Jul 2026 | DRD/SRD load-time invariant + self-heal (closes cost-calc error) |
| v1.39.6 | 2 Jul 2026 | CostingDetail dashboard refresh on Approve & Save |
| v1.39.5 | 2 Jul 2026 | DRD/SRD initial port from GRP legacy |
| v1.39.4 | 30 Jun 2026 | CostingsKpiStrip stale-state fix |
| v1.39.3 | 30 Jun 2026 | Real emails + admin User Setup email edit + no-mailto Submit |
| v1.39.1 | 29 Jun 2026 | Original Phase 1 bundle (Edit-wire, tooltips, BOM, backend bay-occupancy fixes) |
| v1.39 | 29 Jun 2026 | Phase 1 baseline (v4.36b + v4.36c + v4.36c.1 + v4.36d + v4.38) |

**Deploy line tag on origin:** `v1.40.0` (annotated + SHA-verified).

---

## 8. Support & getting help

- **Admin (Michael):** system access, permissions, config
- **BA / Ops (Marnus):** server infrastructure, VPN, DNS, prod deployments (from Monday-Friday during work hours)
- **Legacy calc issues (faje.co.za):** referenced as source of truth for cost formulas; CA3 handoffs live in `docs/handoffs/`

Key documents:
- **Deploy runbook:** `docs/releases/v1.40.0.md` §8
- **Rollback:** `git checkout v1.39.7` + `alembic downgrade -1` if 0030 needs revert
- **Blank slate script:** `backend/scripts/wipe_demo_data.py`
- **Seed script:** `backend/scripts/seed_from_mockup.py`
- **BA handover (2 Jul 2026):** `C:\Users\micge\Documents\Burt Costing Model\ICB business process\BA_HANDOVER_2026-07-02_Session_Summary.md`

---

# Developer information

The sections below are for developers, code agents, and BA members setting up local development. End-users can stop here — the user-oriented content above covers day-to-day operation.

## D1. Local development setup

### Prerequisites

| Tool | Version used here |
|------|-------------------|
| Python | 3.12+ (3.14 supported) |
| Node.js | 20+ (24 used) |
| PostgreSQL | 18 (dev) / 16 (prod) |
| Git | 2.40+ |

> Dev machine: PostgreSQL 18 listens on port `5432`. The port is set by `DATABASE_URL` in `backend/.env`.

### First-time setup (Windows)

```bat
:: 1. Create the database (run once, as the postgres superuser)
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -p 5432 -U postgres -f deploy\postgres\init.sql

:: 2. Copy and edit your local env file
copy .env.example backend\.env

:: 3. Install deps, build the frontend, apply migrations, seed
scripts\setup.bat
```

### Run

```bat
scripts\start.bat        :: production-like: single FastAPI service on http://localhost:8000
scripts\start-dev.bat    :: hot-reload: FastAPI:8000 + Vite:5173 (Vite proxies /api -> 8000)
```

### Linux / Mac

`scripts/setup.sh`, `scripts/start.sh`, `scripts/start-dev.sh` mirror the `.bat` files.

## D2. Database & migrations

All schema changes go through **Alembic** (`backend/alembic/`). There is no runtime `create_all`; the dev scripts run `alembic upgrade head`.

```bat
cd backend
alembic upgrade head          :: apply
alembic downgrade base        :: tear down
alembic revision --autogenerate -m "describe change"
```

## D3. Key API surfaces

### Production Jobs (`/api/production-jobs/*`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/production-jobs` | List jobs (filters: status, branch_id, accepted_since, limit, offset) |
| GET | `/api/production-jobs/{id}` | Job detail with joined costing data |
| POST | `/api/production-jobs/from-calculation/{calculation_id}` | Accept a costing into production |
| POST | `/api/production-jobs/{id}/pre-job-card` | Send pre-job card |
| POST | `/api/production-jobs/{id}/pre-job-signoff` | Record sales/production sign-off |
| POST | `/api/production-jobs/{id}/planning-ack` | Planning acknowledgement |
| POST | `/api/production-jobs/{id}/chassis-received` | Confirm chassis arrival |
| GET | `/api/production-jobs/{id}/timeline` | Derived lifecycle timeline |

### Materials & Stores (`/api/mes-materials/*`, `/api/stock-counts/*`, etc.)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/mes-materials` | Catalogue + stock (filters: dept, abc_class, low_stock, branch_id) |
| GET | `/api/mes-materials/{sap_code}` | Material detail + current stock |
| GET | `/api/stock-counts` | Cycle counts |
| POST | `/api/stock-counts` | Record a count |
| GET | `/api/discrepancies` | Buyer queue |
| POST | `/api/po-suggestions/{id}/raise` | Raise PR |
| GET | `/api/demand-lines` | Forecast rollup |

### Planning (`/api/planning-slots/*`, `/api/session/*`)

| Method | Path | Purpose (permission gate) |
|---|---|---|
| GET | `/api/session` | Current user + branch + permissions |
| POST | `/api/session/branch` | Switch active branch |
| GET | `/api/planning-board` | Board: weeks × slots + unscheduled |
| POST | `/api/planning-slots` | Schedule (`planning.schedule`) |
| POST | `/api/planning-slots/{id}/move` | Reschedule (`planning.schedule`) |
| DELETE | `/api/planning-slots/{id}` | Unschedule (`planning.unschedule`) |

### Users & Auth (`/api/users/*`, `/api/auth/*`)

| Method | Path | Purpose |
|---|---|---|
| PUT | `/api/users/{id}/email` | Admin-only email edit (v1.39.3 addition) |
| GET | `/api/session` | Current user + permissions + CSRF token |

### Chassis Records (`/api/chassis-records/*`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/chassis-records` | Chassis list |
| GET | `/api/chassis-records/{id}` | Chassis detail (with version for optimistic-lock) |
| PATCH | `/api/chassis-records/{id}` | Update fields (chokepoint: role-gated, audit-logged) |
| GET | `/api/chassis-records/{id}/audit` | Change history (chassis.update permission) |
| POST | `/api/chassis-records/{id}/vin` | Capture VIN |

Full API docs (Swagger UI): `http://localhost:8000/docs`

## D4. Deployment modes

The same build runs cloud or on-prem; only env vars differ:
- `DEPLOYMENT_MODE`
- `DATABASE_URL`
- `AUTH_PROVIDER`
- `FILE_STORE`
- `SMTP_URL`
- `EMAIL_FROM`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `ANTHROPIC_API_KEY`
- `ALLOWED_ORIGINS`
- `SAP_*` (SAP integration)
- `BASE_URL` (for email deep-links)

Phase 1 prod deploy: on-prem Linux server at 192.168.0.251, Postgres 16, systemd-managed FastAPI service.

## D5. Documentation index

- `docs/adr/` — Architecture Decision Records (0011 db-guard, 0013 SAP read-only, 0028 QC + Dispatch, 0029 Cockpit, 0030 chassis sole-editor + audit, 0031 native cost calc, 0032 bounded-wrapper flex reflow)
- `docs/audit/` — mini-discovery synthesis artifacts per phase (v4.36d §3.0, v4.36e §3.0, etc.)
- `docs/handoffs/` — cross-repo BA briefings (DRD/SRD from CA3, etc.)
- `docs/releases/` — release notes (v1.40.0)
- `docs/runbooks/` — deploy runbook
- `docs/oracles/` — reference documents

## D6. Testing

- Backend tests: `cd backend && pytest --ignore=tests/journeys`
- Journey tests (Playwright): `cd backend && pytest tests/journeys` (runs on CI matrix Ubuntu + Windows)
- Frontend build: `cd frontend && npm run build`
- CI runs both OS runners on every PR

## D7. Support & contact

- **Codebase questions:** review `docs/adr/` first, then reach out to Michael
- **Deploy issues:** Marnus (server admin) — call for urgent, otherwise use engagement WhatsApp
- **Business rules / product decisions:** Michael (BA lead)
