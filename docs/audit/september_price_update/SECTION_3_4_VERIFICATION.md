# §3.4 — Dev apply + verification record (v1.52, 4 Sep 2026)

Dev DB `icb` @ localhost:5432. **Dev is left APPLIED** for Michael + Nadie's
click-through on :8000 (restart :8000 to pick up the new backend python; the
DB-side prices are visible immediately either way).

## What ran, in order

1. **Migration 0047** applied (dev at `0047`; proven earlier in a rolled-back
   transaction: up / guard / stamp+expiry / down / re-up).
2. **BEFORE impact snapshot** (`impact_before.json`) — every affected body costed
   through the real engine (`_build_bom_items` → `calculate_bom`, default dims +
   default body options, 32D and 4G passes).
3. **Apply #1** — 431 line actions (371 LINE_UPDATE, 55 PU_COVERED, 5 PU_RESCALE),
   124 override resets, 24 in-place materials (+24 `price_history`), 64 created
   materials, 184 `bom_override_history` rows, factor → `1.3170731707317074`.
   Journal: `apply_journal_dev_20260904T053956Z.json`.
4. **Revert** from the journal — **byte-exact**: sha256 of all five written tables
   (`materials`, `bill_of_materials`, `admin_settings`, `price_history`,
   `bom_override_history`, each dumped `ORDER BY id`) identical to the pre-apply
   snapshot (`fa55cd7e…`, `8922ff34…`, `8cccf580…`, `7a5bbf36…`, `97c39953…`).
5. **Apply #2** (the state dev now holds) — identical action counts; end-state
   **value-identical** to apply #1 on all five tables (multiset comparison
   ignoring only batch timestamps and created-row ids): materials 860 rows ✓,
   per-line BOM state 8989 ✓, settings ✓, history multisets ✓.
   Journal: `apply_journal_dev_20260904T054021Z.json` (the operative revert input).
   Backup: `backups/pre_apply_dev_20260904T054021Z/` (proven == the original
   state; the two intermediate proof snapshots were pruned as redundant).
6. **Double-apply guard proven**: a third `--apply` REFUSED (exit 1, nothing
   written): "88 materials already carry the 'September 2026 price update' stamp".
7. **AFTER impact snapshot** + join → `impact_report.csv`.
8. **Unit suite** (icb_test @ 0047, freshly seeded): **921 passed / 12 skipped /
   0 failed** (exit 0). Journeys run in CI on the PR.
9. **Browser verification** (side port 8012, worktree code, dev DB):
   - CHILLER 2.3 METER: 15 "Updated Sept 2026" badges; FRONT shows
     **Rhinotex 1150 BW** + badge (screenshot in the session log).
   - Badges render with Tips OFF (`body[data-tips]` absent, badge computed
     `display:inline-block`) — the ratified independence requirement.
   - CHESTER SPEC MEAT BODY: 21 badges; sell total R 490 548,58 =
     cost 256 954.02 × 1.05 ÷ 0.55 **exactly** — live calculator and the
     impact-report engine agree to the cent.
   - Calculator 2: 17 badges on CHILLER 2.3. Console clean on both pages.

## Impact headlines (cost-level, default selections — full table in impact_report.csv)

- **Most bodies move DOWN 2–9%** (skins 272/267 → 213/222, PU 32D −4.9%,
  plywoods down) — September is largely a price reduction.
- **CHESTER SPEC MEAT BODY +22.5% (+R47 194)** — its PU lines had no overrides
  and read stale shared defaults (R185 where Burt's August sheet already said
  R258). September writes correct per-line overrides: the body was
  **underquoting** and is now right. Flag to sales explicitly.
- GRP TRAILERS +1.6% (100*50 timber → LVL Beam 128.67→146.59, etc.);
  TAUT LINER +0.08%; ADVANTICA −0.4% (inactive body).
- ADV VACUUM PANELS: engine total at default dims is degenerate (R40M —
  pre-existing formula blow-up unrelated to this lane); its +0.08% delta is
  directionally fine but the absolute numbers on that row are noise.
- 4G columns move slightly more than 32D on PU-heavy bodies (factor 1.3631 →
  1.3171 partially offsets the 32D drop on the 4G view).

## Known-and-reported residue (nothing silently dropped)

- 1 UNMATCHED row: BAKERY BODIES row 95 `19MM PICTURE FRAME` (trailer 39 carries
  Sheet1's `19MM PHONE BONDED PLYWOOD` spelling) — `excluded_scope.csv`.
- 1 REVIEW row: CHILLER MEDIUM DRD PU override (bom 3205) with no thickness link
  — left untouched, `review_rows.csv`.
- Uncovered no-override PU lines still read the stale shared per-section PU
  defaults (Chester-class bodies got overrides; the shared materials themselves
  stay untouched per the 0046 guard) — standing Burt question, restated.
- Override survivors on affected bodies: `override_survivors.csv` (623 rows) for
  BA review per ratified default 3.
- RHINORANGE PU stays on Burt's 4G-flavoured numbers (September moved them by
  5400/5875 — status quo preserved; v1.51's open question stands).
- Out-of-manifest header-block changes (margin/thickness ladder edits, 8 rows)
  listed in §3.0 — outside the ruled scope, BA to decide on a follow-up.

## Coordination caveat

Dev DB sits at alembic **0047** while `backport/v1.39-base` still heads at 0046.
If any OTHER lane runs `alembic upgrade head` against dev from a pre-merge tree
before this PR merges, its head-resolve will fail on the unknown 0047 — same
class as the 0044/P2 incident. BA sequences merges accordingly.
