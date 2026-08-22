# BA feedback — v1.50 P3: repair from body categories + reusable repair templates (21 Aug 2026, CA lane → merged `9659475`)

**Scope of this document:** the entire P3 session, dispatch to close — §3.0 discovery, migration
0044, backend, frontend, tests, PR #163, two rebases inside the three-lane merge queue, the full
local suite, the squash-merge, and the post-merge :8000 deploy. Written for the BA-coordinator;
errors and near-misses are reported as plainly as the wins, because that is what the banked-lesson
system runs on. (Dates below are the git/GitHub-recorded ones, SAST = UTC+2.)

**Outcome in one line:** PR #163 merged by Michael at `9659475` with CI green on its exact head
and the full local suite green at that same head (187 journeys, 0 skipped), dev :8000 is on
`9659475` with alembic 0044 applied and `calculator.js?v=169` served-verified, no tag was created,
and the lane was subsequently carried to prod inside v1.50.0 by the R-series session (its runbook
lists `#163 9659475` explicitly).

---

## 1. What shipped

| Item | State |
|---|---|
| **PR #163** — `feat(costings): repair from body categories + reusable repair templates (v1.50 P3)` | Opened 21 Aug 08:16 SAST, **merged 12:09 SAST** as `9659475`; +2401 / −9 across 14 files |
| **Feature 1** — "+ From body category" with the optional *vehicle being repaired* block | Shipped as ratified (Defaults 1–6) |
| **Feature 2** — reusable repair templates (create / use / manage / soft-retire), no stored prices | Shipped as ratified (Defaults 7–11); migration **0044**; catalogue key `costings.repair_templates_manage` `{admin, full}` |
| **Fix found in-lane** — Approve saved a stale repair payload when the type was typed last | Shipped in the same PR (§5) |
| **Tests** | 20 new units (`test_repair_categories_templates.py`) + 1 new journey (`test_repair_categories_journey.py`, ran, 0 skipped); migration up→down→up on `icb_test` |
| **CI** | Green on both heads it ran on: `81cdd32` (pre-P2 rebase) and **`5842da1`** (the merged head) — see §12 |
| **Dev :8000** | ff-only pulled to `9659475`, alembic `0043→0044`, SPA rebuilt, restarted, served bytes verified |
| **Tag** | None — per dispatch; BA confirms the version at release time (the R-series session later tagged `v1.50.0`) |
| **Document impact (Default 12)** | Reported; a *summarise-by-origin* print mode **proposed, not built** (§10) |

## 2. Discovery (§3.0) — what the codebase turned out to be

The WO's one STOP condition — "if category quantities cannot be computed without the full
body-option context, STOP" — **did not arise**, and the reason is worth banking:
`_build_bom_items(include_all_items=True)` already exists in `routers/calculator.py` (built for
Calculator 2) and is precisely the "bypass every body-option gate, drop the master toggle rows,
keep every costed line" mode the preview needs. Feeding its output, filtered to the chosen
categories, into the same `calculate_bom(items, dims, body_vars, formula_lib, global_vars)` a body
costing runs gives the body costing's quantities by construction — section multiplier (×2 for
SIDES) and waste included. Nothing was reimplemented.

Other load-bearing findings:
- A repair is a `CalculationRecord` with `is_repair=True` **and `trailer_type_id IS NULL`** — that
  *absence* is the mode discriminator (`free_hand.is_repair_mode`). So the vehicle block had to ride
  `input_state.repair_vehicle`, never the top-level `trailer_type_id`/`dimensions`, or the costing
  would silently flip onto the body-costing path.
- Repair lines live in `result_json.input_state.repair_lines` and materialise per calculate into
  synthetic `bom_items`; "ordinary repair line" therefore means "a free-hand line" — which fixed
  the shape of a pulled line (§3).
- Categories are the distinct `bom_section` names of the trailer's BOM rows in global section
  order; sections parked in the Unassigned tray (`archived_at`) are excluded because a body
  costing would never render them either.
- The stock-list picker (`modal-stock-pick`) was the component idiom to copy; Lane D's
  `paginate_lines` + carry-over already handles long repair quotations (Default 12, §10).

Collision checks (the corrected ones) were run with positive controls before trusting them: max
migration on any ref was 0043 → **0044**; max `?v=` 167 → **168**, later moved to **169** (§6).

## 3. Feature 1 — as ratified, and the design calls made under C4 latitude

Built to Defaults 1–6 with no bounce-backs. Endpoints: `GET /api/repair/body-categories`
(auth only) and `POST /api/repair/category-preview` (auth only; compute-only, nothing written —
unit-asserted). The preview forces `excluded=False` on every chosen-category line and passes the
chosen sections as `optional_sections_enabled`, so an *explicitly picked* OPTIONAL section arrives
priced rather than soft-excluded: picking the category **is** the opt-in; the modal's tick boxes
do the excluding.

Calls made (all in the PR description, none needing a bounce):
1. **Pulled lines are `free_hand` kind**, not `stock`. Default 4 wants them editable (description,
   qty, price) and removable; Default 5 wants the price as a snapshot at insertion. A stock line is
   catalogue-locked and server-re-priced on every calculate, so free-hand is the only kind that
   satisfies both. They additionally carry `material_id` as *provenance metadata* (never used for
   pricing — the client keys stock behaviour on `kind`, never on `material_id`) so that a template
   made from them can re-price live later.
2. **Origin chip** (`origin`, e.g. `SIDES`) rides both line kinds through `parse_lines` →
   `snapshot` → reopen; it replaces the "manual" chip on a free-hand line (it says more) and sits
   beside "stock" on a stock line. The document layer does not yet read it (§10).
3. **Option-variant rows all appear** (e.g. both the EPS and the PU panel rows of a SIDES section,
   one of them computing 0) — ticked, un-tickable. That is the honest consequence of "no body-option
   context" and exactly Default 3's wording; the real CHILLER LARGE screenshot on :8000 shows it.
4. **Guard (Default 6)**: the menu item is rendered dimmed with a hint when no body type + dims are
   set, **and** clicking it toasts the explanation — readiness is read fresh at menu-open and at
   click, never cached, so it can't be stale. Never a silent no-op.
5. The vehicle block prefills L/W/H from the body type's defaults and is restored on edit/duplicate.

## 4. Feature 2 — as ratified, the price semantics, the gate

Migration 0044 (`repair_templates`, `repair_template_lines`, schema `icb_costings`; inspector-guarded,
idempotent, mirrors 0040/0043; up→down→up verified on `icb_test`, and cleanly `0043→0044` on dev).
Lines store `kind`, `material_id`, `description`, `qty`, `unit`, `notes`, `origin` — **no price
column exists, by design**. `/expand` is the use path: today's material-list price for a stock
line, today's list price *offered* for a free-hand line that carries a material reference (a pull),
nothing for a plain free-hand line (typed at use, inserted at 0), and `unavailable: true` for a
material that has left the list (seeded unticked in the picker with a plain note) rather than a
stale price. Retire is soft and `/expand` refuses a retired template with 409; restore brings it
back. The manage surface (rename inline, retire/restore, per-template line view) sits inside the
repair surface's source menu — the smallest thing that works.

**One nuance the BA should hold:** a BOM row priced by a skin formula / override pulls into a
repair at its *computed* price, but its template reincarnation prices at the **material-list**
price — that is the literal ratified Default 7 ("resolve LIVE from the material list at the moment
of use"). It is stated in the PR; if Lezette's real bundles are dominated by formula-priced rows it
may warrant a BA word.

Permission: `costings.repair_templates_manage` seeded `{admin, full}` (the `price_master_edit`
pattern); using a template needs no key. The v1.48 lesson is pinned as a unit test — the gate string
is asserted to be **in** `PERMISSION_CATALOGUE` — and the dev startup bootstrap was observed seeding
key + both grants after the deploy restart.

## 5. Found in passing — a latent pre-existing defect, fixed in the same PR

`approveCosting` spread `lastCalcPayload`, which captures the repair's type / scope / document
fields at **calc** time; typing the type does not re-cost (v1.47's deliberate "the type gates the
save, not the price"). So a user who filled the type **after** the last line change posted a stale
payload and the server answered **422 "Type of repair is required"** against a form that plainly
showed one. I hit it within minutes of live-verify because the new flows invite exactly that order
(pull lines first, describe later). `approveCosting` now refreshes those fields (and the vehicle
block) from the surface at save time; the journey deliberately types the type last. Same class as
Lane C's "stale not wrong" bugs — the BA may want it on the v1.50 what's-new as a quiet fix.

## 6. Merge-queue chronology

| When (SAST) | Event |
|---|---|
| ~07:00 | Dispatch; worktree on `2b82af7` (= prod v1.49.2); collision checks run with positive controls (0044 / 168) |
| 07:30–08:00 | §3.0 report; 0044 + models; router + 20 units green (62 with the free-hand suite); frontend; live-verify on side port **8013** against `icb_test` |
| ~08:05 | Noticed **P1 (#162) already merged** via the shared refs before being told; rebased (one catalogue-key conflict, both keys kept); sweep + #162's own tests green |
| 08:10 | Re-ran the `?v=` check: **P2's branch had appeared holding 168** → moved to **169** (its own commit, documenting why) |
| 08:16 | PR #163 opened; CI green both OS on `81cdd32` (9m12s / 8m46s) |
| ~09:40 | P2 (#161) + #164 merged; rebased again (one `calculator.js` conflict — P2's `_setRepairDocNumber` beside my `_setRepairVehicleInputs`, both kept); sweep: exactly one script tag at 169, no markers, 0044 unique to my branch; dist rebuilt; sweep tests green |
| ~09:50 | Force-pushed `5842da1`; CI green both OS (9m41s / 9m35s); P2 agent's handoff message arrived — its collision picture matched mine line for line |
| ~10:00 | Michael's :8000 stopped (its exact launch command captured first); **full local suite at `5842da1`**: units exit 0, journeys 187 passed / 0 skipped in 6m51s; :8000 restarted healthy, port checked free of orphaned fixture servers first |
| 12:09 | Michael squash-merged → **`9659475`**; remote branch auto-deleted |
| 12:10–12:20 | Post-merge :8000 procedure + served-bytes proof + three read-only screenshots on the real box |

## 7. CA errors and near-misses — reported plainly

1. **Journey expected-total arithmetic (my error, caught by the run itself).** The first journey
   run failed only on the final total: I expected 4 000 (glue qty 2) but the real stock picker
   inserts qty **1** (my live-verify had pushed qty 2 by hand), so 3 725 was *correct*. Fixed by
   making the assertion data-driven (each template line's own default qty × today's price).
   *Lesson: never carry a number from a hand-driven rehearsal into an assertion about the real
   control's behaviour.*
2. **`_template_payload` omitted `updated_by`** — a unit caught it on the first run; trivial, but
   it is the reason the rename test exists.
3. **Purge blocked by `price_history` FK.** My live-verify `PUT /api/materials` wrote a
   price-history row; the journey purge's `LIKE 'J150P3%'` also matched my `J150P3LV` live-verify
   rows and hit the FK. Purge now deletes `price_history` before materials. *Banked: an admin price
   edit writes history rows that FK the material; marker prefixes must not be prefixes of each
   other.*
4. **Section-snapshot cache flake, pre-empted.** My unit asserting exact order + the ×2 multiplier
   passed on first run only because the 30 s snapshot happened to load after seeding; under another
   suite order it would have flaked. Fixed with `invalidate_sections()` after seeding/teardown;
   the journey (a different process) asserts displayed-vs-displayed instead.
5. **Screenshots on :8000 — two wrong turns before the right door.** (a) The in-app browser pane
   was hidden, so `screenshot` could not composite (JS-driving still worked). (b) My headless
   Playwright login failed "Invalid credentials": **dev's admin password is not the seed default**;
   the pane had only worked because it was riding an existing host-scoped session. Resolved via
   the app's own `POST /api/mes/autologin` (dev .env has `MES_DEMO_AUTOLOGIN_USER=admin`) — no
   password touched, no DB row minted. *Banked.*
6. **The banked false-negative, re-encountered and recognised:** my first served-page probe for
   `?v=169` returned nothing — an unauthenticated `curl` gets the login page. Re-probed
   authenticated: one tag, 169. (The static JS markers had already confirmed the deploy.)
7. **Not an error, but a judgement call to flag:** the full local suite required :8000 free, so I
   stopped and restarted Michael's server (same command, same clone, same env; verified healthy and
   free of fixture orphans). It happened outside his testing window and is what the dispatch asked
   for; if the BA prefers a standing "authorised :8000 window" ritual, P2's agent suggested the same.

## 8. Deploy — dev, and the prod note

Post-merge :8000 procedure (this lane, 12:10–12:20 SAST): stop → `git pull --ff-only` on Michael's
main clone (`8cb3281 → 9659475`, his uncommitted doc edits untouched) → `alembic upgrade head`
(`0043 → 0044`, both tables present) → `npm run build` (20.4 s, server stopped first — the Windows
build trap) → restart with the captured command → `/health` 200.

Proof chain (because a green build is not a deploy): authenticated `/mes/calculator` serves
**exactly one** `calculator.js?v=169` tag; the served JS carries the P3 and P2 markers;
`/api/repair/body-categories` answers 401 (live, auth-gated — not 404); the permission key and its
`{admin, full}` grants were seeded by the startup bootstrap. Three read-only screenshots were taken
on the real box (CHILLER LARGE, 7,5 × 2,6 × 2,6; its 14 real categories; SIDES preview 10/10 lines,
R 32 489,95) and handed over; the journey's own four screenshots are committed under
`docs/screenshots/journeys/repair_categories/`.

**Prod:** not this lane's step. The R-series session's runbook
(`docs/runbooks/prod-deploy-v1.50.0-repair-numbering-bundle.md`) records v1.50.0 going to prod on
22 Aug 06:58 SAST with `#163 9659475` in the set and migrations `0043→0044→0045`; that document is
the deploy record for P3 on prod.

## 9. Corrections to standing beliefs / facts banked

| Believed (or unknown) | Actual |
|---|---|
| Category quantities might need the full body-option context (the STOP condition) | `include_all_items=True` is an existing no-gating mode; the preview reuses it — no STOP |
| The dispatch's 168 was free for P3 | P2 took 168 while P3 was building; re-running the check **after** rebasing is what caught it → 169 |
| Applying an additive migration to the shared dev DB early is harmless | **Not when other lanes deploy first:** `alembic_version='0044'` with their checkouts lacking the file breaks *their* `upgrade head`. P3 verified on `icb_test` and applied 0044 to dev only post-merge |
| Dev admin password = seed default | It is not; headless auth on :8000 goes through the dev-enabled autologin |
| Journey screenshots need the browser pane | The suite's headless `shot()` and a small Playwright script do it; the hidden pane can drive but not composite |
| Journey dir size | **187 journeys** collected at head `5842da1` (a useful baseline for "did the whole dir run") |
| Full journeys dir can run with `MES_BASE` on a side port | Only some files are base-aware; the rest dial :8000 — confirmed independently by the P2 agent; the only safe full run lets `live_server` boot its own :8000 against `icb_test` |
| Test purge = delete materials last | `price_history` FKs materials and is written by admin price edits — delete it first |

## 10. Open items / BA decisions

1. **Summarise-by-origin print mode (Default 12) — BA decision.** A 40-line SIDES pull renders as
   a clean multi-page quotation with carry-over totals, but reads like a parts list. Proposal (not
   built): an optional print mode with one line per pulled category ("REPLACE SIDES — materials",
   category total), detail kept on screen. `origin` is already stored on every pulled line, so the
   document layer can group without new capture — a small, contained follow-on if ratified.
2. **Template price source nuance (§4)** — formula-priced BOM rows re-price at list price via a
   template. Worth one line to Lezette if her bundles lean on skin-formula rows; or a follow-on
   "remember the computed price as the template default" if the BA prefers (that would store money,
   against Default 7 — so it is a decision, not a bug).
3. **Stale-approve fix** — suggest a one-liner in the v1.50 what's-new ("typing the repair type
   after the lines no longer refuses the save").
4. **Sidebar version string** still reads v1.49.2 on :8000 — none of the three v1.50 lanes touched
   `VERSION`; version naming is yours at tag time.
5. **Worktree** `C:\Users\micge\Documents\icb-platform-p3-repair-categories` still exists (branch
   merged and deleted on origin) — delete at leisure.
6. **Stale-tab trap** — anyone with a calculator tab open from before the deploy must reload
   (`?v=167/168` → `?v=169`); same note P2 raised.
7. **Hardening chips** already on the board from the P2 agent: purge-order hardening for the
   assembly journey (task_854b9e8f). P3 added none.

## 11. Click-to-verify (Michael, on :8000)

1. Costings → New costing → Body Type **REPAIRS**. Under *Type of repair*: **"Vehicle being
   repaired (optional)"** (body type + L/W/H).
2. With no vehicle set: **"+ From body category ▾"** → first item dimmed with a hint; clicking it
   toasts the explanation.
3. Pick a body type (dims prefill) → **From body category…** → tick a section (e.g. SIDES) →
   **Preview lines** → every line ticked with qty / unit price / line total → untick a couple →
   **Add selected** → lines land with a green **SIDES** chip; the total moves by exactly what was
   ticked; lines edit / re-price / remove like any other.
4. Add a stock + a free-hand line → dropdown → **Save lines as a template…** → name → save (the
   dialog shows "list price at use" / "typed at use", never money).
5. Fresh repair → dropdown → **From template…** → pick it → today's list prices → **Add selected**
   → save → **↓ Repair quotation (PDF)** carries the lines.
6. Dropdown → **Manage templates…** → rename inline, **Retire** (gone from the picker; `/expand`
   refuses), **Restore**.
7. Shared-maths spot check: a **body costing** of the same body type + dims shows the **same SIDES
   quantities** the repair pulled.

## 12. Verification ledger (for the record)

- CI (both OS, `build & test`): run `32453743470` on `81cdd32` — ubuntu 9m12s, windows 8m46s;
  run `32455299298` on `5842da1` — ubuntu 9m41s, windows 9m35s. Squash-merge `9659475`.
- Full local suite at `5842da1` (the exact merged head): units exit 0; journeys
  **187 passed, 0 skipped** in 6m51s (both P2's ten free-hand tests and the new P3 journey among
  them); SMTP black-holed for the run per the live-SMTP rule; :8000 restarted healthy after.
- Migration 0044: up→down→up on `icb_test`; `0043→0044` on dev `icb` post-merge; tables + index
  names verified by inspector query.
- §3.5 proof: `test_preview_quantities_match_body_costing` — `POST /api/calculate` (body path) vs
  `POST /api/repair/category-preview`, same body + 7.5 × 2.3 × 2.3, per-line equality of
  qty / price / line total for SIDES, including 17.25 → **34.5** (×2 multiplier) and 100 → **220**
  (+10 % waste).
- Live-verify before the PR: side port 8013 against `icb_test` only; :8000 was never used for CA
  testing (A2 held) until the authorised full-suite window and the post-merge deploy.
- Branch hygiene: 4 lane commits (backend / frontend+fix / journey / cache-bust), rebased twice,
  merged as one squash; remote branch auto-deleted; no force-push after the PR was green except
  the protocol rebase itself.

## 13. Files in the squash (`9659475`)

`backend/alembic/versions/0044_repair_templates.py` (+142) · `backend/app/database.py` (+49) ·
`backend/app/main.py` (+2) · `backend/app/routers/calculator.py` (+6) ·
`backend/app/routers/repair_templates.py` (+432, new) · `backend/app/services/free_hand.py` (+68/−) ·
`backend/app/static/js/calculator.js` (+704/−) · `backend/app/templates/calculator.html` (+119/−) ·
`backend/tests/test_repair_categories_templates.py` (+515, new) ·
`backend/tests/journeys/test_repair_categories_journey.py` (+373, new) · four journey PNGs under
`docs/screenshots/journeys/repair_categories/`. **Untouched by design:** the body-costing flow,
body-option/insulation logic, the 3.2 m rule, validated references, the materials master, R-series
numbering, quote numbering, `/api/*` integration surfaces, `formula_engine.py`, the quotation
document builders.
