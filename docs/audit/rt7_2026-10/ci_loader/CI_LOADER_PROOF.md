# RT7_RULING_1B §1 — CI's loader: the snapshot's rows win (19 Oct 2026)

**The red:** PR #220 head `1814b0c` — Costing audit #42: freezers 35 FLAG, icecream 40, explosive 6; every one a
`foam_4g` cell. **The BA's diagnosis is confirmed, with one addition below.**

## The mechanism (confirmed)

1. `alembic upgrade head` seeds `admin_settings['costings.pu_foam_4g_factor']` = `1.363109048723898` (migration 0046),
   under its own id (3 on a fresh database).
2. `load_snapshot` was `INSERT … ON CONFLICT DO NOTHING`. The snapshot's row (prod's id **10**, `1.3170731707317074`)
   clashed on the unique `key` and was skipped. The loader even said so: `admin_settings: 1 snapshot row(s) not present
   (already there under another key)`. That line was in every CI log since v1.57.3, and nobody read it as a fault.
3. CI priced 4G at 4 100 × 1.3631 = R5 588.75 instead of prod's R5 400.

**Why the mirror said 0 FLAG (the BA's question).** The mirror is loaded by RT1's `docs/audit/rt1_2026-09/load_mirror.py`.
It calls the same `load_snapshot`, then **sets the factor by hand**. Its docstring names the gap: "The one row a fresh
database already holds under the same natural key is admin_settings `costings.pu_foam_4g_factor` … it is set to the
snapshot's value afterwards, as the v1.58 mirror did by hand." RT1 found the gap and fixed it for the mirror only; CI
was never fixed. RT7 then proved prod = mirror (2 936 / 2 936 cells), not mirror = CI. That was my miss: the proof
should have run CI's own load path.

## What a fresh `alembic upgrade head` already holds (`clash_scan.py`, read-only)

On the fresh scratch database, only **one** row clashes with the snapshot: the factor (natural key `key`, id 3 against
the snapshot's 10). Every other snapshot table is empty.

A *used* test database is different. The shared local `icb_test` holds an older snapshot load (3 254 BOM rows with the
same ids) and the app's startup seeds, which keep 4 natural keys under other ids: the factor, `Waste`, `freezer_quote`
and the `FREEZER` group, some of them referenced. The journeys and the backend tests load into such a database. This is
why the fix covers every case and keeps an undo log.

## The fix (`backend/tools/costing_audit/mes_snapshot.py`)

`load_snapshot` makes the snapshot's rows win in **every table** (E3):

- **Same primary key:** upsert on the key, so the snapshot's values win.
- **Same natural key under another id** (a migration's or the app's seed):
  1. the old row's key is moved aside;
  2. the snapshot row is written;
  3. every row pointing at the old row is re-pointed at the snapshot's;
  4. the old row is deleted (an ordered DELETE, never CASCADE).
- **Rows under a snapshot body or recipe that the snapshot does not carry** (`OWNED_BY`: a body's BOM rows, a recipe's
  items) are deleted.

Every change goes into an undo log. `unload_snapshot` replays it backwards, so a fixture on a shared database leaves it
exactly as found. The whole-DB fingerprint of `icb_test` (98 tables, count + md5 per table, `db_fingerprint.py`) is
identical before and after the suites that load snapshots: audit, v1.58, ops, the admin page and RT4's pre-window. The
full backend suite changes only tables its other tests write: the MES floor reseeds, sessions, users, and the
validated-reference tolerance row's timestamp.

`check_fidelity` (G1) runs after the load. Every snapshot row must equal its database row, column for column, and no row
under a snapshot parent may be missing from the snapshot. Any mismatch is listed by table, key and column. The one value
allowed to differ is the loader's own documented case: a foreign key whose target the snapshot does not carry is written
NULL. These are body 51's 7 orphans; they are counted and logged.

- **In the audit job:** a new step, `python -m tools.costing_audit load-snapshot`, runs the load and the check before the
  pack run and exits 1 on any mismatch.
- **In `run --mes-snapshot`:** it does the same and prices nothing on a mismatch.
- `test_rt7_ci_triggers.py` now also requires the load-fidelity step to come before the run.

## B3 — proved on CI's own path first (`ci_path/`)

Steps:

1. The scratch database `icb_prodmirror` is reset as RT1 did (`reset_mirror.ps1`: the app schemas dropped and
   recreated, `alembic upgrade head` → 0053). Before the load: 0 BOM rows, factor id 3 = the seed.
2. `audit load-snapshot --allow-non-test-db`. The flag is needed only because the scratch database's name does not end
   in `_test`; CI's does.
3. The five packs, `--env prod`, with the committed golden and list.

Results:

| step | result |
|---|---|
| load | 4 828 rows; `the snapshot's values written over admin_settings 1`; 7 dangling FKs (body 51) written NULL |
| fidelity | **4 828 snapshot rows, 147 839 values compared: the database holds the snapshot** |
| factor | id 10 = `1.3170731707317074` |
| packs | smoke **ACCEPTED 33** / PASS 156 / SKIP 45; chillers PASS 590 / SKIP 126; freezers **ACCEPTED 72** / PASS 501 / SKIP 117; icecream UNVERIFIABLE 40 / **ACCEPTED 40** / PASS 416 / SKIP 116; explosive UNVERIFIABLE 36 / **ACCEPTED 3** / PASS 528 / SKIP 117 |

**All 0 FLAG / 115 ACCEPTED, smoke 0 / 33**, as RULING_1B expects. FREEZER MEDIUM FLOOR L3 is on its pins, `foam_4g`
included: MES − Excel = +347.13, ACCEPTED.

## F6 — the negative control (`nc_do_nothing/`)

Steps:

1. The same fresh reset.
2. Load with **the loader as it was at `1814b0c`** (`git show 1814b0c:…/mes_snapshot.py`, DO NOTHING), then the new
   check.
3. Freezers.

Results:

| step | result |
|---|---|
| load | `admin_settings: 1 snapshot row(s) not present (already there under another key)` |
| fidelity | **1 MISMATCH: `admin_settings id=10 (key='costings.pu_foam_4g_factor'): not in the database`** (exit 1) |
| freezers | **FLAG 35** / ACCEPTED 68 / PASS 470 / SKIP 117: CI #42's 35. FREEZER MEDIUM FLOOR L3 `foam_4g`: `ACCEPTED_AMOUNT_CHANGED entry 4 pinned +347.13; actual +453.77`, the BA's numbers |

The same control runs as a test on every PR: `test_negative_control_with_do_nothing_put_back_the_fidelity_check_names_the_seeded_row`
(`tests/costing_audit/test_rt7_pins.py`).

## Tests (`tests/costing_audit/test_rt7_pins.py`, all in rolled-back transactions)

- the snapshot's rows win over a migration seed, and the fidelity check proves it;
- the negative control above;
- a seeded row under another id is replaced, its referrers follow, and `unload_snapshot` puts it all back;
- a row under a snapshot parent that the snapshot lacks is flagged (named), then removed by the next load;
- `test_admin_run_support.py::test_unload_removes_exactly_what_load_inserted`: a committed load and unload on the
  database, fingerprinted before and after. It still holds on the used local `icb_test`.

`sync_settings`, the first settings-only fix, is removed. RULING_1B asked for every table.

## Found by the full backend suite: a sequence left behind (fixed in `4e17b26`)

The first full run of `pytest --ignore=tests/journeys` on the new loader failed one test,
`test_rt3_bootstrap::test_a_fresh_database_seeds_the_templates_and_the_groups`: `report_templates_pkey (id)=(5)
already exists`. The cause is that `setval` is not transactional:
1. the new loader deletes a replaced row (the seeded `freezer_quote`, id 5);
2. it then set each sequence to the remaining MAX(id), which was 4;
3. the rolled-back load put row 5 back, but the sequence stayed at 4, so the next insert collided.

The fix: the loader only moves a sequence forward, to `GREATEST(MAX(id), last_value)`. The test
`test_a_rolled_back_load_never_leaves_a_sequence_behind` replays the case in a savepoint. **Negative control:** with the
`795f441` loader it fails, `assert 19 >= 20`.

The two sequences my earlier runs had left behind on the shared local `icb_test` were moved forward to their table's
max (`global_variables` 1 → 2, `report_templates` 4 → 5; forward only). A check of every serial sequence in both app
schemas now reads 0 behind.
