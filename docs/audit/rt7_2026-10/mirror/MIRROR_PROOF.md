# RT7 mirror proof — the 19 Oct build paste, the refreshed golden, the pinned list (19 Oct 2026)

**The mirror:** `icb_prodmirror` (scratch, owner `icb_app`), backed up first
(`Documents\icb_db_backups\rt7-mirror\icb_prodmirror_pre_rt7_20261019-151820.dump`, sha256 `12b7cee1…`, 101 table-data
entries), reset as RT1 did (the three app schemas dropped, `icb_costings` + `icb_mes` recreated), `alembic upgrade head`
(0053, the RT7 code), loaded with `docs/audit/rt1_2026-09/load_mirror.py` from the build paste's 15-body snapshot
(`all.json`, digest `336dd05e…`; 4 090 BOM rows; 7 dangling FKs = body 51's orphans, written NULL as CI does), and the
4G factor set to the snapshot's exact text `1.3170731707317074`.

| check | result |
|---|---|
| prod's paste (deployed v1.61.0 golden + list) vs the mirror with the SAME golden + list, cell by cell (status, MES and Excel totals to the cent) | **2 936 of 2 936 identical** — the snapshot is prod |
| the paste's data vs the 16 Oct discovery export, the 12 audited bodies | one row moved: `costings.pu_foam_4g_factor` `1.361219512195122` -> `1.3170731707317074` (updated_at still 1 Oct: Michael's 19 Oct SQL set the value only). Every other difference is rows the 3 extra bodies bring |
| the paste's cells vs 16 Oct's | MES moved on 165 cells (freezers 41, icecream 40, explosive 84) — every one a 4G cell, down by at most 3.24 % (5400/5581); the Excel side identical; chillers and smoke unmoved |
| the mirror against the REFRESHED golden, the old list | All **48 FLAG / 67 ACCEPTED**, smoke 15 / 18 — the 16 Oct picture: 0 status changes; 144 of 148 FLAG/ACCEPTED amounts identical, 4 foam_4g icecream cells ±R0.01 (4G rounding) |
| the walk (`../list/walk_h4.txt`): 8 prunes one at a time, the 4 survivors re-labelled, the 3 FREEZER MEDIUM entries | every prune: 48 / 67 unchanged; after the 3 entries: **0 / 115**, smoke **0 / 33** |
| `audit pin --write --snapshot` | 122 pins over 7 entries, 0 unaccepted; the pair recorded |
| **the final run: the committed prod list (strict), the refreshed golden, the mirror** (`final/`) | **All 0 FLAG**: chillers PASS 590 / SKIP 126; freezers ACCEPTED 72 / PASS 501 / SKIP 117; icecream ACCEPTED 40 / PASS 416 / SKIP 116 / UNVERIFIABLE 40; explosive ACCEPTED 3 / PASS 528 / SKIP 117 / UNVERIFIABLE 36 — **115 ACCEPTED**; smoke ACCEPTED 33 / PASS 156 / SKIP 45 |

These are the window's expected numbers after the deploy (prod's data as on 19 Oct 15:15).
