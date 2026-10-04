# RT4 Part C §3.0: what answers without a session (local sweep, 4 Oct 2026)

**Code:** `b59d8e3`. Its `backend/app` is byte-identical to prod's `682a6cc` (v1.60.0); #213 changed docs only.

**How:** in-process `TestClient` calls, with **no session cookie**, made to every route the app registers:

- 470 registrations, which are 469 distinct (path, method) pairs. `GET /api/import/sheets` is registered twice
  (`import_excel.py` ~L205 and ~L381), so the second registration is unreachable.
- **Prod-like environment** (`wt4.ps1`):
  - `MES_DEMO_AUTOLOGIN_USER=` is empty, so the autologin route is not mounted, exactly as on prod;
  - SMTP, Twilio, Anthropic and the feedback pings are all off.
- **Every database session is read-only at the server.** `PGOPTIONS=-c default_transaction_read_only=on` is
  asserted before the first call, and the startup seed is never run, so nothing could be written. The DB was the
  local prod mirror.
- **Two passes:**
  1. ints = 1, strings = `x`, body `{}`;
  2. every 400 / 404 / 405 / 422 / 500 again, with real ids and the required query params filled in.
- **Shapes only:** status, content type, size and the top-level keys of each response. No values are kept.

| file | what |
|---|---|
| `routes_list.py` → `routes.json` | every registration: methods, path, handler, source line, dependencies, auth-shaped calls in the handler (a static hint) |
| `noauth_sweep.py` → `sweep_final.json` | the dynamic answer per (path, method), after pass 2 |
| `probe_list_check.py` | checks `ops/prod-rt4/noauth_probe_paths.txt` (the prod GET probe list) against the local app. It matched **43 of 43** |

## Result

| answer with no session | count |
|---|---|
| 401 (`/api/*`, `require_user` / `require_admin` / `_require_admin_api`) | 374 |
| 403 (custom checks run before the session check: origin, dev mode, permission; each handler was read, and a session check follows in every one) | 17 |
| 307 / 303 to `/login` (pages) | 33 + 3 |
| 422: form or query validation runs **before** the handler's own `require_admin` (each handler was read; all are gated) | 10 |
| **answers (200 / 302 / 404-then-200)** | **32** |

The 32 that answer are listed in `RT4_RETURN_1` §C1, with what each returns.
