# §3.0 Mini-discovery — September 2026 price + description update (v1.52)

Lane: `feat/v1.52-september-prices` · CA discovery report, 4 Sep 2026.
Inputs: BA manifest (919 rows, committed here), Burt's September + August
workbooks (read-only), dev DB `icb` @ 5432 (alembic 0046).

## a. Sheet → MES body mapping

Verified empirically two ways: (1) `bill_of_materials.source_cell` row numbers
against manifest row numbers with material-name equality (17 sheets ≥80%
row-exact), and (2) name+price set overlap for the sheets whose rows have
shifted since import. Every mapping below is the unique best candidate; no
assignment is by name alone.

| Workbook sheet (exact spelling) | Trailer (id) | Evidence |
|---|---|---|
| `Adv Vacuum panels` | ADV VACUUM PANELS (1) | 80% row-exact |
| `ADVANTICA BODY` | ADVANTICA BODY (2) — **INACTIVE body** | 100% row-exact |
| `TAUT LINER RIGID` | TAUT LINER RIGID (9) | 100% row-exact |
| `CHESTER SPEC MEAT BODY` | CHESTER SPEC MEAT BODY (10) | 92% row-exact |
| `MEAT BODY` | MEAT HANGER LARGE (12) | 93% row-exact |
| `DRY FREIGHT TRAILER` | DRY FREIGHT TRAILER (13) | 91% row-exact |
| `GRP TRAILERS` | GRP TRAILERS (14) | 92% row-exact (twin: 15) |
| `RHINORANGE TRAILER` | RHINORANGE TRAILER (15) | 92% row-exact (twin: 14; PU rates 6373.8 unique to 15) |
| `icecream up to 3,2` | ICECREAM UP TO 3,2 (16) | name+price sets; rows shifted since import |
| `icecream up to 4.8` | ICECREAM UP TO 4.8 (17) | 〃 |
| ` icecream 4.9 up` | ICECREAM 4.9 UP (18) | 〃 |
| ` UP TO 2,3 MTR FREEZER ` | FREEZER 2.3 METER (19) | 〃 |
| ` UP TO 4.8 MT FREEZER  (2` | FREEZER MEDIUM (20) | 90% row-exact |
| ` 4.9 & UP FREEZER BODY (2` | FREEZER LARGE (21) | 95% row-exact |
| `EXPLOSIVE UP TO 2.7` | EXPLOSIVE UP TO 2.7 (34) | name+price sets |
| `EXPLOSIVE 2.7 TO 4.8` | EXPLOSIVE 2.7 TO 4.8 (37) | 〃 |
| `EXPLOSIVE 4.9 AND UP` | EXPLOSIVE 4.9 AND UP (24) | 〃 + 0046 journal rows on 24 match sheet PU exactly |
| `UP TO 2.3 CHILLER BODY` | CHILLER 2.3 METER (25) | sections+names align, rows +3 |
| `UP TO 5.5 CHILLER AND 2.3 WIDE` | CHILLER MEDIUM (26) | 90% row-exact |
| ` 4.9 & UP CHILLER AND 2.5 WIDE ` | CHILLER LARGE (27) | 89% row-exact (sheet's live table is in cols L..S; A..H are #REF! junk) |
| `BAKERY BODIES` | RIGID DRY FREIGHT (39) | 92% row-exact — see Sheet1 note |
| `SMALL MEAT BODY UP TO 5,2` | MEAT HANGER SMALL-MEDIUM (36) | 93% row-exact |

**Unmapped in-scope sheet:** `AELER PANELS` (12 manifest rows) — no MES trailer
contains its items (no candidate above noise). Per the dispatch it falls out of
scope; its 12 rows are reported in the excluded-scope list, not imported.

**Out of scope (Michael's ruling):** the 5 Manni sheets (map to trailers 3,4,5,6,7 —
131 rows) and `Sheet1` (94 rows). Kept in reconciliation, refused by the import.

**Notes.**
- ADVANTICA BODY (2) is `is_active=false` in MES. Its 7 rows import normally;
  the body stays invisible until reactivated. Flagged for BA.
- `Sheet1` ("BAKERY BODY'S / DRY FREIGHT") and `BAKERY BODIES` BOTH shadow
  trailer 39 (94% vs 92% row-exact). Trailer 39 was almost certainly imported
  from Sheet1 (it has Sheet1's `19MM PHONE BONDED PLYWOOD` spelling). The two
  sheets' September changes are identical on 81 rows and DIFFER on 4:
  two `Rhinotex 1150` (BAKERY) vs `Rhinotex 1150 BW` (Sheet1) name targets, and
  `19MM PHENO BONDED PLYWOOD` priced 46.28 (BAKERY) vs 223.15 (Sheet1). Per the
  ruling the import follows BAKERY BODIES; the conflicts are in the report for
  Burt's Sheet1 decision.

## b. How BOM lines key to sheet rows; where values live

- **Line ↔ row:** `bill_of_materials.source_cell` stores the import-time cell
  (e.g. `H35`); its row number equals the sheet row for sheets not edited since
  import. Where Burt has inserted rows, matching is by
  (trailer, normalised old description), disambiguated by section and
  source-row proximity, pairing duplicates in row order. Result on the 427
  in-scope actionable rows (price and/or desc changed): **426 matched,
  0 ambiguous, 1 unmatched** (BAKERY row 95 `19MM PICTURE FRAME` — the line on
  trailer 39 carries Sheet1's name; reported, not guessed).
- **Prices:** effective unit price = `skin_formula → taping_block → floor_plate
  → mounting_cleat → bill_of_materials.unit_price_override → materials.price_per_unit`
  (routers/trailers.py:189 `get_bom`, same order in the engine). Materials are
  GLOBAL and name-duplicated (six different `EXT GRP SKIN 2*300` rows at
  different prices; per-section `PU` rows shared across bodies).
- **Descriptions:** the line's display name IS `materials.name` — a "description
  change" is a material identity question, not a text field on the line.
- **Overrides:** 825 overrides exist; 182 sit on lines this update touches
  (reset + journal per default 3), the rest survive and are listed per body.
- **Journals already in the schema:** `price_history` (material price moves) and
  `bom_override_history` (override moves, `batch_at`-grouped undo). The import
  reuses both, plus its own CSV journal.
- **"Price updated" chip machinery:** materials carry `last_updated` (7-day
  green chip), `last_bulk_update_at/note` (30-day amber chip) — rendered in
  calculator.js/calculator2.js; colours are ALWAYS visible, only hover tooltips
  are Tips-gated (style.css:684-717). The 30-day self-expiry the badge needs
  already exists at material level.
- **Badge gap → §3.1 migration IS needed (0047):** PU line prices live in
  `unit_price_override` (0046 architecture) and SPLIT-repointed lines can land
  on pre-existing materials, so a material-level stamp cannot mark every
  changed line. 0047 adds nullable `bill_of_materials.price_updated_at`;
  the import stamps every touched line; the calculator shows "Updated Sep 2026"
  while the stamp (or the material bulk stamp) is younger than 30 days,
  independent of the Tips checkbox. No number collision: 0046 is the head,
  0047 unused on any branch.

## c. The 4G factor and PU pricing

- `admin_settings['costings.pu_foam_4g_factor'] = 1.363109048723898` (dev,
  seeded by 0046). September: 32D 4310→4100 and 4G 5875→5400 ⇒ new factor
  **5400/4100 = 1.3170731707317074**. The apply script updates the setting row
  (journaled), dev and prod alike. The CODE constants in
  `app/services/insulation_foam.py` (SHEET_PRICE_32D/4G, FACTOR_4G_DEFAULT)
  deliberately stay on the 4310/5875 pair: they anchor 0046's historical
  classifier and the v1.51 tests, and the runtime fallback they feed only fires
  when the setting ROW is missing — it exists on both databases (dev verified;
  prod confirmed seeded in the v1.51 deploy OUTCOME). Flagged for BA; a one-line
  follow-up can retire them if wanted.
- **Manifest PU rows are 32D-based where the body is 32D-based** — ratio checks
  are exact (`245.73583/258.32230 = 0.9512761 = 4100/4310`, Chester/GRP/
  icecream/freezer/explosive-2.7s). **Exceptions found and handled:**
  - EXPLOSIVE 4.9 AND UP: manifest PU rows move ×5400/5875 (=0.919149) — the
    workbook shows 4G prices, while 0046 normalised those 4 lines to stored 32D
    (journal: 246.485→180.8256). Applying the manifest number verbatim would
    double-count the 4G factor. The import stores `manifest_new ÷ new_factor`,
    cross-checked against `stored_old × 4100/4310`.
  - RHINORANGE TRAILER: the 5 rows 0046 left UNCLASSIFIED (rate 6373.8) move
    ×5400/5875 in the manifest — Burt keeps that body on 4G-flavoured numbers.
    Import applies manifest values verbatim (status quo preserved); the open
    Burt question from v1.51 stands and is restated in the report.
  - FREEZER LARGE rows 32/118: Burt fixed his thickness/typo anomalies; the
    manifest new values are plain 32D and match `stored_old × 4100/4310` —
    verbatim apply.
  Every covered PU line must satisfy one of the three rules within tolerance,
  else it goes to a REVIEW list and is not written.
- **PU lines not covered by the manifest** (sheets show 0 while the option is
  deselected in Burt's saved state): in-scope lines carrying a 32D-stored
  override are rescaled ×4100/4310 (journaled, action-class PU_RESCALE) so a
  chiller quoted with PU insulation prices at September, consistent with the
  bodies whose sheets happened to show PU. The SHARED per-section `PU`
  materials (ids 207/209/211/213/236/292 — thickness-baked defaults, flavours
  unclassifiable, referenced by Manni + deleted bodies too) are NOT touched —
  same guard 0046 applied. Manifest-covered PU lines that today read the shared
  default (Chester pattern) get a per-line override created at the September
  value — the 0046 architecture's home for per-body PU prices.

## d. Independent diff + reconciliation (ratified default 1)

`backend/tools/diff_grp_costings.py` re-derives the diff from the two saved
workbooks (cached values, style-based highlight detection, per-label-row layout
tracking). Proof-of-detection: finds the known `Adv Vacuum panels` row 35
`LVL PICTURE FRAME` 359→409 before anything else is trusted.

**Result: clean.** 919 rows, price=513, desc=213, total=808, highlighted=462 —
flag-, value- (±0.005) and row-identical to the BA manifest
(`independent_diff.csv` committed beside the manifest). The manifest is the
union of changed rows and Burt-highlighted rows: 53 rows are highlight-only
(no change; no import action), 207 in-scope rows are total-only (derived
movement — composite/taping/qty effects; no direct import action; they surface
in the engine-level impact report instead).

**Also surfaced (outside the manifest's row zone, report-only):** 8 changes in
the sheets' header/options blocks, including margin/thickness ladder edits —
`FRONT EPS 0.6→0.55` (UP TO 4.8 FREEZER), `SRD EPS 0.625→0.75` (4.9&UP
FREEZER), `DRD EPS 0.525→0.5` (EXPLOSIVE 2.7-4.8), `FRONT EPS 0.515→0.55`
(DRY FREIGHT TRAILER), `FRONT PU 0.54→0.55` + `ROOF EPS →0.725` (RHINORANGE),
`FRONT EPS 0.54→0.55` (UP TO 2.3 CHILLER), `DRD 0.6→0.65` (Sheet1). These are
NOT part of the ruled scope (prices + descriptions); BA to decide if a
follow-up lane should carry them.

## Pre-existing drift (context for the impact report)

281 of the 426 matched lines already disagree with the manifest's AUGUST value
(DB carries an older price cycle, mostly via overrides — e.g. CHILLER 2.3
FRONT skin: DB 256.50 vs Aug 272.27 vs Sept 213.11). September supersedes both;
the journal records the ACTUAL before-value per line, so the impact report's
deltas are real MES deltas, not sheet deltas.

## Material identity plan (rename/reprice without leaks)

88 distinct materials are referenced by matched lines. 24 are IN_PLACE-safe
(every referencing line is in this update with the same target) → renamed/
repriced in place, `price_history` + bulk stamps written. 64 are SPLIT (also
referenced by Manni lines, deleted bodies, in-scope-but-unchanged lines, or
orphaned rows) → the changed lines are repointed to a found-or-created material
carrying exactly (new name, new price); untouched lines keep the old material
untouched. Every action lands in the dry-run plan CSV before anything writes.
