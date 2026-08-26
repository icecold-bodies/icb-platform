# BA feedback — repair quote presentation session (25–26 Aug 2026, CA lane → prod v1.51)

**Scope of this document:** the entire session, dispatch to close — PR #169 (repair quote
print modes + board R-number, the original WO), PR #170 (cross-lane merge defect found on
:8000), PR #172 (footer overlap, Lezette's 26 Aug report), PR #173 (Cloudflare cache /
no-store, still open), the prod deploys along the way, and two infrastructure discoveries
that explain several days of confusing observations. Written for the BA-coordinator; errors
and corrections are reported as plainly as the wins, because that is what the banked-lesson
system runs on.

**Outcome in one line:** the customer-facing repair quotation now matches the old system's
ratified look (three print modes, breakdown default), the board shows the R-number Lezette
is asked about on the phone, the footer-overprint defect is dead at the mechanism, and the
"prod still broken" mystery turned out to be a Cloudflare edge cache in front of a second
front door nobody had told the verification story about — fixed in code (#173, awaiting
merge) and needing one dashboard purge.

---

## 1. What shipped

| Item | State |
|---|---|
| **PR #169** — three print modes (SUMMARY / **BREAKDOWN default** / ITEMIZED), mode persisted per quote, editable reference caption ("Veh reg nr:" → free text), uppercase forcing removed at all four mechanism sites, header overlap hardening (60-char test), acceptance-form Order Number rule, board Quote # shows R-number primary + internal beneath on all three list surfaces, search matches both numbers, heal script staged | Merged `537af2e`, CI green on head `ab02fdb` (4th round — §3) |
| **PR #170** — one `calculator.js` tag, not two (cross-lane auto-merge defect) | Merged `b44982a`, CI green on head `7d465e2` |
| **PR #172** — quote lines/totals never drawn over the remittance footer | Merged `e2dbfd5`, CI green on head `445fd6a` |
| **PR #173** — `Cache-Control: no-store, private` on every extension-suffixed authenticated route | **OPEN, CI green on head `683df3b`** — awaiting merge authorisation (§6) |
| **Dev :8000** | At `e2dbfd5`; every feature served-bytes-verified and console-clean after each deploy |
| **Prod** | At `e2dbfd5` since 26 Aug 08:53 SAST (footer fix live; #173's header **not yet live**). The v1.51 bundle itself (#168–#171) was deployed 25 Aug 21:04 by the parallel-lane CA — their runbook is the deploy record |
| **Test infra** | `icb_test` now exists locally (5432/PG18, alembic 0045, mockup-seeded); full backend suite (0 failures) + all 205 journeys (0 skips) runnable on this machine again |

## 2. The WO itself — built to the ratified defaults, one bounce avoided

All nine ratified defaults landed as dispatched: no migration (print mode and reference
label ride `result_json`/`input_state` exactly like the R-number), body-costing exports
byte-pinned by regression test, catalogue names untouched by the caps removal, stored
ALL-CAPS text not rewritten. The download chooser opens on the mode the quote was LAST
downloaded in, so a re-download reproduces the document already in the customer's inbox —
that invariant (not just "a mode param exists") is what the journey pins end to end.

**Found during discovery and pinned rather than bounced:** the #167 filename dedupe is a
substring test, so a registration like "2001" would vanish inside "R-2001". Pinned with the
plain-number convention tests; no behaviour change needed.

## 3. PR #169 took four CI rounds — every failure mine, and worth the ledger

The lane's features were correct from round one; the test discipline around them was not.
Reported plainly because three of the four lessons are reusable:

1. **A guard on a button is not a guard on the page.** My results-page chooser JS sat
   outside the `{% if %}` that wraps the button, so `repair-quote.pdf` leaked into every
   costing's HTML — body costings and deleted ones included. Three existing tests correctly
   define "the page does not offer the quotation" as a property of the whole response.
2. **Sweep by shape, not by name.** I hunted the v1.49 uppercase assertions by test name
   and missed two; re-sweeping by mechanism (feeds lower-case, asserts ALL-CAPS) found
   exactly those two and nothing else. Same E3 rule as ever; I applied it late.
3. **Displayed-vs-displayed, never hand-computed.** My journey hardcoded `35,751.20`; VAT
   is admin-editable, so the constant pinned the test to a configuration, not a rule. The
   repo convention was already written in `test_repair_categories_journey`'s docstring.
   Money now derives from the saved costing via the document's own `money()`, and the
   asserted rule is the real one: the total is identical across all three modes.
4. **A fix found by hand must land in the test that needs it.** I discovered path-vs-hash
   routing (`/mes-app/costings`, not `/mes-app/#/costings`) in the browser during live
   verification, fixed my manual test, and still shipped the journey with the hash URL.

## 4. PR #170 — two lanes, one line, no conflict marker

#168 (PU foam, `v=170`) and #169 (`v=171`) each bumped the same cache-bust line; the second
merge auto-merged the two `<script>` tags **side by side** and base served both — the
second copy died on `SyntaxError: Identifier 'allCustomers' has already been declared` on
every calculator load. Neither lane's CI could see it: both were green in isolation, and
the defect exists only in the merge result. Fixed at `v=172` (a fresh number, because both
old ones had already been served to browsers), swept for siblings (no other duplicated
script/stylesheet; both shared .py files clean of duplicate keys/kwargs).

**Convention proposed (G1-adjacent):** after any second lane merges into base, load the
page and read the console before calling the merge good. The B2 pre-commit check catches
collisions a lane can see; this class only exists after the merge.

## 5. PR #172 — Lezette's footer overprint, and why the first test lied

**Not a regression from the print modes** — the very first R-2001 (rendered before this
lane existed) already overprinted its footer with "Total before Discount: ZAR 30,408.40"
across the ICB e-mail address. My lane widened row padding ~4pt, which made a latent defect
fire on nearly every real-length quote.

Root cause: three heights nothing ever budgeted (the column-header row repeated on every
page, the Carry Over row a continuation page opens with, and the totals block itself) plus
`_row_height` *estimating* a row (paragraph + 11pt) instead of measuring one — the estimate
drifted the moment padding changed. Everything is now measured with the same widths and
paddings the renderer draws with, and when the totals genuinely cannot fit they take a page
of their own — which is how the old system's own R-231037388 reads (totals alone on 2/4).

**The testing lesson is the valuable part:** a text-based PDF assertion **cannot see
overprinting at all**. `pypdf.extract_text()` rebuilds text in content-stream order, so the
footer read back perfectly intact while being visually destroyed — my first regression test
was green against the broken renderer. The check had to move to coordinates
(`visitor_text`, y = `tm[5] + cm[5]` because `drawOn` translates the canvas). And one
sharper edge: a block-replace of mine briefly deleted a fixture list, so 24 tests went red
on a NameError and looked like a passing negative control. **A red negative control must be
red for the right reason — read the failure text.** The honest control: 12 red at base,
54/54 green with the fix, 1–60 items × 3 modes swept with zero overlaps.

Verified against every real repair record on dev (all 10, all modes, position-checked) and
on prod after deploy.

## 6. The two-front-doors discovery — why "prod still broken" was true and false at once

Michael reported the overlap still present on prod after the #172 deploy; every server-side
check said otherwise (byte-identical renderer, fresh workers, recompiled bytecode, same
reportlab as dev). Both were right:

- **Prod has two front doors.** `https://192.168.0.251` (nginx, LAN, no cache) and
  `https://mes.icecoldgrp.online` — a **cloudflared tunnel** on the same VM, running since
  11 Aug, token in `/etc/cloudflared/token`, configuration living in the Cloudflare
  dashboard (no local config file). Michael tests via the domain; every CA verification
  this session used the IP.
- **Cloudflare caches by URL extension and injects `Cache-Control: max-age=14400`** onto
  responses that carry none (verified live: `/static/css/style.css` MISS→HIT with the
  injected header). The quotation URL ends in `.pdf` and sent no cache header — so the edge
  kept a copy AND the browser was told to keep one for four hours. No restart could reach
  him through that.
- **Sessions are per-hostname**, so being logged in on the IP ≠ logged in on the domain —
  that produced the misleading `Unauthorized` mid-diagnosis, and it means a fresh
  unauthenticated fetch can never return a PDF: any PDF seen from a logged-out context was
  by definition cached or previously saved.

**Fix (#173, open):** every authenticated GET whose path ends in a CDN-cacheable extension
now sends `no-store, private` — the quotation PDF plus the two admin import samples, which
a pattern sweep shows are the only three such routes (exports carry no extension, so
Cloudflare's default never caches them). Test pins the header; negative control red on
exactly that assertion. First CI round hung on a runner (47 min, no log, step never
completed); the rerun was green in a normal 10 minutes on identical code.

**This is also a data-exposure finding, not just a staleness bug:** an authenticated
customer quotation cached on a public CDN edge is servable again without reaching our auth.
`no-store` stops future fills; it does **not** evict what is already cached.

## 7. Security items for BA decision

1. **Cloudflare governance (from §6).** Needed beyond the code fix, in order:
   (a) **dashboard purge now** (Caching → Purge Everything) to evict the already-cached
   customer PDFs; (b) a **cache rule bypassing `/api/*`** as belt-and-braces so the next
   extension-suffixed endpoint anyone writes is safe by default; (c) the tunnel's
   dashboard-held configuration documented and owned — it is currently invisible to the
   repo and to runbooks, which is how it stayed out of every verification story;
   (d) a one-line staff guidance on which hostname to use, since sessions do not carry
   across.
2. **`/openapi.json` is world-readable on prod** — 348 KB describing the full API surface,
   no auth (Michael flagged it for this round on 26 Aug). It proved genuinely useful for
   deploy verification (FastAPI builds it from the running objects, so it is the best
   "which Python is live" probe we have), which suggests the fix is *gating*, not removal:
   wrap `/openapi.json` + `/docs` + `/redoc` behind the existing session auth (admin-only),
   keeping the diagnostic value on an authenticated call. A CA lane of an hour or two,
   including the CI probe updates.

## 8. Open items

| Item | Owner | State |
|---|---|---|
| **Merge #173** (CI green on `683df3b`) → prod deploy (pull + restart, no migration) → verify the header through **both** doors | Michael authorises; CA executes | Waiting |
| **Cloudflare purge** (evicts cached customer PDFs; independent of the merge) | Michael (dashboard) | Waiting |
| **Heal script** for prod R-2001/R-2002 (`backend/scripts/sql/heal_repair_doc_numbers_v1_51.sh`, dry-run default, staged on the VM alongside the template revert) | Michael on the VM | Staged, unrun |
| Board duplicate React key — rows keyed by non-unique `quote_number`, stale row survives a narrowed search | Next lane (chip spawned) | Open |
| RHINORANGE 5 rows unclassifiable by migration 0046 (rate 6373.80) | Burt, via PU lane's ledger | Open |
| `/openapi.json` gating (§7.2) | BA to ratify → CA lane | Proposed |

## 9. Environment notes worth keeping

- `icb_test` setup has **three** steps, not two: `init_test.sql` (as postgres, **port
  5432**), `alembic upgrade head`, then `python -m backend.scripts.seed_from_mockup
  --reset` — without the seed, ~20 `*_seeded` tests fail `assert 0 == 12` on an empty DB.
  The missing third step was a CA omission in the instructions Michael was given.
- A background task-notification's "exit code 0" is the **wrapper's**, not the command's —
  the same class as the `| tail` trap. Two CI verdicts this session were initially
  misread green because of it; every watch now records `$?` to a file and reads that.
- **Probe the door the user uses.** Verifying prod through one front door says nothing
  about what the other serves. Now banked alongside the half-deploy rule (a pull without a
  restart looks deployed to every template/static probe; probe a Python-side field).
