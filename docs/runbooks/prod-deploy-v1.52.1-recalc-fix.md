# Prod deploy — v1.52.1 "edit-mode thickness recalc fix" + v1.53 catch-up (7 Sep 2026)

Target: **`https://192.168.0.251/mes-app/`** · repo `/opt/icb-platform` · service
`icb-backend` (`uvicorn --workers 4`) · DB `icb_platform`.

| | |
|---|---|
| Prod was at | `cd763c8` (v1.52, September prices) |
| Deployed to | **`e9dd6da`** (#175 squash) |
| Range | 4 commits: #175 (v1.52.1) + #178/#177/#176 (v1.53, never previously on prod) + the v1.52 OUTCOME doc |
| DB migration | **NO** — alembic stays `0047` (asserted before *and* after) |
| Data mutation | **NO** — code only; the day's data fixes were applied separately by their own journaled tools |
| Frontend rebuild | **NO** — no `frontend/src` changes |
| Service restart | **YES** — `backend/app/routers/trailers.py` changed (#176); a ff-pull alone is the half-deploy trap |
| New deps / env | none; prod `.env` untouched |
| Cache-busts | `calculator.js?v=174` → **`?v=177`**; `style.css` unchanged at `?v=21` |

## What landed

- **#175 v1.52.1 — the edit-mode freeze.** `editBodyVariable`'s blur handler PUT a
  hand-typed insulation thickness and called `runCalc()`, but never mirrored it into
  `editBodyVarOverrides`. That pin rides every recompute payload and the server
  replays it over the template (`_apply_body_variable_overrides`), so the totals kept
  the SAVED figures — the recalculation ran and silently used the old value (the
  N9936 mechanism). v1.42.1 fixed the toggle path and the excel-paste path
  (`_xpSetThickness`) but never this one — `_xpSetThickness`'s own comment ("same PUT
  as the manual bv-edit blur, plus the `_pinBodyVar`") documents the gap it left.
  The pin now happens first and unconditionally, and the unchanged-value early
  return recomputes when the pin moved (re-typing the same number is exactly how a
  user tries to break a freeze). Calculator 2 never declares the pin — unaffected.
- **#178 / #177 / #176 (v1.53)** — draft-body editable insulation thickness, Excel
  paste vocabulary on masterless v2 bodies, cross-body Explorer snapshot restore.
  Dev-tested on :8000 before this deploy; this was their first prod exposure. They
  rode along because they are ancestors of #175 on the deploy line.

## OUTCOME — deployed 7 Sep 2026 16:42 SAST, all asserts green

| Step | Result |
|---|---|
| 1 anchor | `cd763c8` confirmed; written to `/tmp/icb-v1521-rollback-anchor.txt` |
| 2 schema before | `0047 (head)` |
| 3 backup | `icb_platform_20260907-1641.dump.gz` |
| 4 ff | `AT v1.52.1 target` — 35 files, no conflicts |
| 5 restart | ActiveEnterTimestamp moved 06:50 → **16:42** |
| 6 boot | **4** workers, **0** bootstrap failures |
| 7 schema after | `0047 (head)` — unmoved, as intended |
| 8 smoke | health 200 · pin-fix marker in served `calculator.js?v=177` = 1 · template on `v=177` |

### ⚠ The step-8 python probe reported a false failure — read this before re-using it

The probe called `/api/configurator/draft-snapshots/1/cross-audit` with no query
string and asserted `401|403`. It got **422**, and the script stopped with
"the new python may not be live". **That verdict was wrong; the deploy was already
complete.** Steps 1–7 had all passed and step 8 is read-only.

The route signature is `(snap_id: int, target: int, ...)` — `target` is a REQUIRED
query parameter, so FastAPI's request validation rejects a param-less call with 422
**before** the `_require_admin_api` dependency ever runs. The staleness signal is
**404** (the route is absent from `cd763c8` — grep count 0), not "anything that
isn't 401".

Confirmed live afterwards, three independent ways:

```
cross-audit?target=17            → 401   (validation passed, auth reached)
/openapi.json contains cross-audit → 1   (FastAPI builds this from RUNNING objects)
/openapi.json contains restore-to   → 1
HEAD = e9dd6da · active since 16:42
```

**Lesson banked:** when probing a route to prove new Python is live, either call it
with every required parameter, or assert on "not 404" rather than an exact auth
code. `/openapi.json` remains the strongest single proof.

## Post-deploy

1. Purge the Cloudflare cache (the domain door), then **hard-reload** — an old tab
   keeps the old JS and will look unfixed.
2. Re-test the fix: open a **saved** costing, change an insulation thickness, and the
   totals must move (before this deploy they stayed frozen at the saved figures).

## Rollback

`/tmp/icb-rollback-v1521.sh` — code only (`git reset --hard` to the anchor +
restart). This deploy changed no schema and no data, so the day's pricing and
thickness corrections are unaffected either way.

## Open item, not addressed by this deploy

Prod's **ICECREAM BODY MEDIUM** has `ROOF PU` and `FLOOR PU` at **0,120 m** where
Burt's September sheet says **0,145 m** (dev is correct at 0,145) — those two lines
under-cost by ~17%. Surfaced by the rear-door sync tool as report-only, since that
tool is deliberately scoped to the DRD/SRD pair. Awaiting Michael's go to extend the
sync to the non-rear-door insulation pairs.
