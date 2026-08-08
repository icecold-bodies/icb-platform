# Costing rule: 3.2 m → plywood + glue at R0,00 (the two MEDIUM bodies)

**Business rule (Nadie, ratified by Michael — Aug 2026).** On body types
**CHILLER MEDIUM** (`UP TO 5.5 CHILLER AND 2.3 WIDE`) and **FREEZER MEDIUM**
(`UP TO 4.8 MT FREEZER  2`), when the entered length is **literally 3.2 m**
(3.20 parses identically; 3.19 / 3.21 cost normally):

- in categories **FRONT** and **SIDES**, the **4MM PF PLYWOOD** row and the
  **GLUE LINE** row directly **below** it (BA-ratified pairing) total
  **R0,00** — the rows stay visible with qty 0, never hidden;
- the user is told the rule is active: a bold red banner on the costing page,
  the four affected line totals in bold red, and one bold red line under the
  price summary on Excel/PDF previews and exports.

Doors (DRD/SRD), FLOOR (12MM ply) and OPTIONAL EXTRAS plywood are
deliberately **out of scope**.

## Mechanism — data, not engine code

Each of the 8 pinned `bill_of_materials` rows carries a formula guard:

```
({original expression}) * (0 if abs(length - 3.2) < 1e-9 else 1)
```

`length` is always in the formula engine's eval scope, so the guard zeroes
the **quantity** at exactly 3.2 and the zero flows everywhere quantities do:
both calculators, previews, exports, and newly saved costings. No engine or
unit-price change. The red notices key off the guard text in the calc result
(`calculator.js` + `app.services.zero_rule_note`) — data-driven, no template
or material names hardcoded in the detection.

Costings **saved before** the guard keep their stored figures (edit-pin
machinery owns those); re-opening an old 3.2 m quote in edit mode shows the
standard drift warning — expected.

## The guard is a DATA change — prod needs the script run once

Git carries the code (notices, script, tests) but **not** the dev-DB data
change. At the next prod deploy, run the idempotent script (dry-run first,
then apply):

```
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; \
  /opt/icb-platform/.venv/bin/python \
  /opt/icb-platform/backend/scripts/rules/apply_32m_plywood_glue_zero.py'

# review the printed row list, then:
sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; \
  /opt/icb-platform/.venv/bin/python \
  /opt/icb-platform/backend/scripts/rules/apply_32m_plywood_glue_zero.py --apply'
```

The script matches templates by **name set** (the imported original *and* the
"CHILLER MEDIUM" / "FREEZER MEDIUM" rename, whitespace/case-insensitive) and
resolves the glue pair **structurally** (the row directly below the plywood
must be a GLUE LINE). It refuses to write anything unless all 8 rows resolve
cleanly, and re-running it on a guarded DB is a reported no-op. If a template
is renamed to something outside the name set, the run fails loud and prints
the live template list — extend `RULES` in the script and re-run.

## Changing or retiring the rule

- **Different length**: edit `PINNED_LENGTH` in the script and re-apply to
  fresh rows (remove the old guard first). The notices display whatever
  length the guard pins — no UI change needed.
- **Retire**: strip the guard suffix from the 8 rows (admin Templates page or
  a one-off UPDATE); the notices disappear with it.
