# RT5 §3.0 discovery: evidence (5 Oct 2026)

## Prod discovery (read only)

**Folder:** `prod/discovery_20261005-160939/`. This is the VM run of `ops/prod-rt5/rt5_discovery.sh`, staged from
`3a18354`, on prod `01751fa` at alembic 0051. The tar came back with sha256 `dca08869…`, and every `SHA256SUMS.out`
line matched on arrival.

**What it holds:**
- `discovery.txt` / `discovery.json`:
  - the families;
  - the forbidden masters, against the live draft and its backups;
  - the saved costings that carry a forbidden choice, by quote number only;
  - the validated references;
  - the freezers' side-door lines.
- `drafts.json`: the six chiller and freezer drafts, payload only. It passed the email gate. It was loaded into
  the local `icb_prodmirror` (6 rows; the journal is in the CA's scratchpad).
- `reports/prod_{freezers,smoke}.{md,json}`: the staged `roof_floor_eps` tool, run over prod's deployed code with
  `--env prod`.

## The roof_floor_eps proof (RT5_RULING_0 Q1)

| run | where | freezers (UNVERIF / ACC / PASS / SKIP) | smoke |
|---|---|---|---|
| CI dispatch 37320351986 | base `8cdc804`, committed snapshot (`all_eps`) | 27 / 24 / 522 / 117 | 9 / 15 / 165 / 45 |
| CI dispatch 37320312903 | `rt5/discovery` `ba5bae8`, committed snapshot | 0 / 24 / 549 / 117 | 0 / 15 / 174 / 45 |
| local, read only | `icb_prodmirror` | 0 / 24 / 549 / 117 | 0 / 15 / 174 / 45 |
| prod, read only | `icb_platform` | 0 / 24 / 549 / 117 | 0 / 21 / 168 / 45 |

- **The new cells agree everywhere.** All 154 `roof_floor_eps` cells (115 freezer + 39 smoke) are identical, both
  `mes_total` and status, on the snapshot, the mirror and prod.
- **Freezers:** prod and the mirror agree on all 690 cells. The snapshot differs from both on 41 `foam_4g` cells,
  all PASS on every side. That is snapshot staleness, which is RT6's job.
- **Smoke:** prod differs from the snapshot and the mirror on 6 ICECREAM UP TO 4.8 cells (PASS → ACCEPTED). Those
  come from Michael's 3–4 Oct edits, already reported in RT4.
- **Base vs new:** the chillers, ice-cream and explosive packs are cell for cell identical. In freezers and smoke,
  only the `all_eps` cells were swapped for `roof_floor_eps`.
- **The totals hold:** freezers stay at 54 scenarios and 690 cells, smoke at 18 and 234, and All at 2 702 cells.
- **Why `all_eps` was unverifiable:** the base's 27 freezer UNVERIFIABLE cells were all `all_eps` on FRONT, DRD and
  SIDES, with `EXCEL_NO_PRICE:EPS`. Burt's own freezer sheets cannot price EPS there.

## Found on the base (not RT5's)

`ci/ci_base/costing_audit_explosive.md` has **15 FLAG**, all on EXPLOSIVE 4.9 AND UP ROOF: every variant at
3 lengths, +1.016 %, with GROUP_DIFF 4MM against 6MM PF PLYWOOD. CI on pull requests runs the smoke pack only, so
this went unseen. It is RT6's job: the snapshot refresh and the re-judging of the accepted list.

## Screens

`screens/`: the proposed notes, on the prototype branch `rt5/note-preview` (local only, never merged). It is served
on a side port over `icb_prodmirror` with prod's drafts. The note colour is `#D12424`, which is RT3's `ink()` of the
skin's `--red` `#DC2626`. That red alone gives 4.50:1, short of 4.6; `#D12424` gives 4.91:1 on both `#FFFFFF` and
`#F5F7FB`.
