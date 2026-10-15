# RT6 §3.0 discovery: evidence (6 Oct 2026)

## Mirror (read only, plus one journaled test costing)

| file | what |
|---|---|
| `mirror/discovery_mirror.txt` / `.json` | `ops/prod-rt6/rt6_discovery.py` over `icb_prodmirror`. It shows the classification of every insulation master on the CHILLER and FREEZER bodies, using `backend/app/services/insulation_rules.py` (the guards' own check), plus the tally for every family. |
| `mirror/remove_proof_rows.txt` | The test costing `A1/10/2026` (id 1, FREEZER MEDIUM, saved with EPS on the SIDES), read three times: as saved; after re-open + Remove + calculate (**byte-identical**); after the overwrite that Remove allowed. |

## Screens (`screens/`)

- **How they were made:** on the local-only preview branch `rt6/preview` (never merged), served on side port 8017
  over the mirror, using element shots of the configuration card and the paste dialog only.
- **`facts.json`:** what each step read back: the calculate breaches, the payload after Remove, the greyed controls
  and their tooltips, and the paste preview text.

| file | shows |
|---|---|
| `RT6_1_reopen_FREEZER_MEDIUM_EPS_SIDES.png` | re-opened: the red warning under the note, with Remove |
| `RT6_1b_after_Remove.png` | after Remove: SIDES PU 0.060 m, no warning |
| `RT6_2_CHILLER_MEDIUM_PU_greyed.png` | a draft that still offers PU: all six PU choices greyed, the rule as their tooltip |
| `RT6_3_paste_PU_row_refused.png` | Paste from Excel: `FRONT PU` refused, with the rule as its reason |

## Prod

`prod/discovery_<ts>/` is the VM run of `ops/prod-rt6/rt6_discovery.sh`, read only. It is added when it comes back.

# RT6 build (v1.61.0): evidence for RT6_RETURN_2

| file | what |
|---|---|
| `mirror/REHEARSAL_v1.61.0.md` | the prod-mirror rehearsal: backup → 0053 → the rules (dry-run / apply / again / show / revert / revert twice refused / re-apply) → RULING_1a on a mirror test costing (soft-deleted = prod's state, restore, Accept 409, re-open warning + Remove, save, accept) → both mirror test costings removed, journaled → All before / after the rules: **No change** (0 differences, 2 936 cells) |
| `mirror/mirror-01-restored-reopened-warning.png` / `mirror-02-after-remove.png` | the restored breaching costing re-opened (the red list, Remove); after Remove (SIDES PU 0.060 m) |
| `negative_controls.txt` / `negative_controls.py` | F6: 22 mechanisms broken one at a time — each caught by its tests; the tree restored from git and proved clean |
| `../../screenshots/journeys/rt6_rules/` | the side-port journey's element shots (re-open → warning → Remove → save; greyed in three renderers; Switch ALL; the paste refusal; the restored costing; the unused door; the TEST bar) |

**Prod in RT6 stays read only until the window.** No test quote is created on prod (RULING_1a): the re-open →
warning → Remove → Accept-refused proof is the mirror rehearsal above and the side-port journey.

# RT6 window (v1.61.0 on prod, 15 Oct 2026): `prod/window_20261015/`

The records the kits wrote on prod, fetched in one tar (`rt6-window-back-20261015-131720.tar`, sha256 `2522f967…`):
`icb-release-v1.61.0/` (preflight ×3, verify ×3, env, deploy with `OUTCOME.txt`), `icb-rt2-all/` (pre ×2, post ×2;
run logs, compare, sums and the `.md` reports — the JSON / CSV / HTML stay out of git), `icb-rt2-doors/`,
`icb-rt6-rules/` (dry-run, apply with its journal, show), `icb-rt6-tidy/` (the dry-run that found 0 of 34). Plus
`window_pastes.txt` (the one-liners run outside a kit: copy, step 4b, step 8, the step-9 check, fetch, the /tmp close),
`cells_window.txt` (All before vs after: 0 differences over 104 966 values; the 156 pre-existing FLAG cells by body and
section) and `step7b_prod_chiller_medium_config.png` (cropped to the configuration card: no customer field). The
runbook's OUTCOME (`docs/runbooks/prod-deploy-v1.61.0.md`) reads them.
