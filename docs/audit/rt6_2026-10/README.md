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
