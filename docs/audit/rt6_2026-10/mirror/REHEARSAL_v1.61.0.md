# RT6 v1.61.0 — the prod-mirror rehearsal (6 Oct 2026, ~17:44–17:55 SAST)

`icb_prodmirror` (local; prod's pricing as mirrored for RT5) with the `rt6/enforce` code. Every read below ran in a
read-only session unless it says it writes. Scripts: the committed `ops/prod-rt6/rt6_rules.py` (as `--target
mirror`), the committed audit CLI, and three lane scripts kept with the CA (state read-back, the browser proof, the
journaled removal of the two test costings).

## 1. Backup, then 0053

| step | result |
|---|---|
| checked full backup | `icb_prodmirror_pre_0053_20261006-174446.dump`, 658 286 bytes, sha256 `4fd96030da23…`; `pg_restore -l`: 101 TABLE DATA entries incl. `alembic_version`, `trailer_groups`, `trailer_types`, `calculations`, `bill_of_materials` |
| before | alembic **0052**; no `insulation_rule` column; 1 costing (the §3.0 test `A1/10/2026`, already Removed + re-saved clean in §3.0) |
| `alembic upgrade head` | `Running upgrade 0052 -> 0053`; read back: alembic **0053**, the column present, every family `None` |

## 2. The rules tool (`rt6_rules.py --target mirror`)

| step | result |
|---|---|
| dry-run | **2 to apply, 0 already applied.** — CHILLER (#8) on CHILLER 2.3 METER / LARGE / MEDIUM; FREEZER (#4) on FREEZER 2.3 METER / LARGE / MEDIUM |
| apply | `APPLIED 2 rule(s): #8 CHILLER; #4 FREEZER`; journal `rt6_rules_journal_mirror_20261006T154645Z.json` (sha256 `2cbc8c1a…`) |
| dry-run again | **0 to apply, 2 already applied.** |
| show | CHILLER = `{"allowed":{"FRONT":["EPS"],"SIDES":["EPS"],"ROOF":["EPS"],"FLOOR":["EPS"],"DRD":["EPS"],"SRD":["EPS"]}}`; FREEZER = `{"allowed":{"FRONT":["PU"],"SIDES":["PU"],"ROOF":["EPS","PU"],"FLOOR":["EPS","PU"],"DRD":["PU"],"SRD":["PU"]}}`; every other family `None`. Greyed: 6 PU masters on each chiller body, `DRD / FRONT / SIDES / SRD EPS` on each freezer body. `live breaching costings: 0`, `soft-deleted breaching costings: 0` |
| revert | `REVERTED 2 rule(s)`; the dry-run reads **2 to apply** again |
| revert twice | **REFUSED** — "#8 CHILLER reads None, not the journal's …: moved since — the transaction rolled back; nothing changed" (exit 2) |
| re-apply (after the test costing below was saved) | `APPLIED 2 rule(s)`; journal `rt6_rules_journal_mirror_20261006T154852Z.json` |

## 3. RULING_1a on the mirror test costing (no test quote on prod)

With the rules reverted, a FREEZER MEDIUM quote was saved with EPS on the SIDES through the calculator — the way
`A9998/09/2026` was saved on prod before the rules — as **`A2/10/2026`** (id 2, no customer). Then the rules were
re-applied (above).

| step | result |
|---|---|
| `show` | `LIVE breaching: A2/10/2026 (pending): EPS on SIDES` → **live 1, soft-deleted 0** |
| soft-delete in the MES (`DELETE /api/calculations/2`) | 200 |
| `show` — **prod's state today** | `soft-deleted breaching: A2/10/2026 …` → **`live breaching costings: 0`, `soft-deleted breaching costings: 1`** (window step 7d's expectation) |
| restore (`POST …/2/restore`) | **200** — unguarded (RULING_1 Q3) |
| Accept (`POST …/2/accept`) | **409** — "A2/10/2026 cannot be accepted: it breaks the body family's insulation rule: EPS insulation is not allowed on the SIDES for this body's family. Re-open it, Remove, save, then accept." |
| re-open (`/mes/calculator?stay=1&edit=2`) | the red list under the note: "This quote breaks the rule above (1). It cannot be saved until each is removed: ✖ EPS insulation on the SIDES — Remove" (`mirror-01-restored-reopened-warning.png`) |
| overwrite with the breach | **409** — "This quote breaks the body family's insulation rule: EPS insulation is not allowed on the SIDES for this body's family. Remove it, then save again." |
| Remove | SIDES PU selected, **0.060 m carried**; the warning gone (`mirror-02-after-remove.png`) |
| overwrite after Remove | **200** (record 2) |
| Accept | **200**, status `accepted` (the accept route only; no job was made) |
| `show` | live 0, soft-deleted 0 |

## 4. The two test costings removed (journaled)

Dry run: no row in any table that points at `calculations` (`calculations_sales_rep_audit`, `icb_mes.prejob_cards`,
`icb_mes.production_jobs`, `validated_references`: 0 each). Apply: one transaction, the full rows journaled first
(`rt6_mirror_remove_tests_20261006T155033Z.json`, kept with the mirror backup), deleted by primary key; read back:
**0 costings** on the mirror. (The A-series counter is not reset: the next mirror quote would be A3.)

## 5. All, before and after the rules — **No change**

The five packs with `--env prod`, every session read-only, at 0053 **before** the rules (`pre`) and with the rules
applied and the test costings removed (`post`):

| pack | pre = post |
|---|---|
| smoke | ACCEPTED 15 · PASS 174 · SKIP 45 (234 cells) |
| chillers | ACCEPTED 9 · PASS 581 · SKIP 126 (716) |
| freezers | ACCEPTED 24 · PASS 549 · SKIP 117 (690) |
| icecream | UNVERIFIABLE 40 · ACCEPTED 43 · PASS 413 · SKIP 116 (612) |
| explosive | UNVERIFIABLE 36 · ACCEPTED 99 · PASS 432 · SKIP 117 (684) |

The report JSONs compared value by value (timestamps aside): **0 differences** over 104 308 values, 2 936 cells. The
check is not in the pricing engine, so the rules cannot move a price; this is the proof.

## 6. Found and fixed by the rehearsal and the sims

- `rt6_rules.py` could not import its check when run from the repo (only beside its staged copy): it now falls back
  to `backend/app/services` (appended to `sys.path`). `--show` also takes `result_json` already decoded.
- `rt6_rules.sh` never passed `DATABASE_URL` to the tool (every prod step would have refused, safely): exported.
  Caught by the window sim's stub, which refuses without it.
- `rt6_tmp_tidy.sh`: one reviewed item (`icb-srd-discovery/`) carries its own `SHA256SUMS`; the archive's sum step
  skipped every file of that name at any depth, so the read-back would have STOPPED after the move. Now only the
  archive's own two files are excluded. Caught by the window sim on the real names.
- `release.sh`: an empty `/login` answer read as "no banner" (`0/0`); it now reads "no login page".
- The guards tests' fixture: a negative control that let a refused job through had left its marker rows behind
  (the job's FK blocked the costing's delete). One marker purge now runs at setup and teardown, child-first by id.
