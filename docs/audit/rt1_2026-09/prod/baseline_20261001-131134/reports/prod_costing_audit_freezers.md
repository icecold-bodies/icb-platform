## Costing audit — pack `freezers` — PASS

- Run: 2026-10-01T11:11:45+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-09-25T14:14:16+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: UNVERIFIABLE 27, ACCEPTED 51, PASS 495, SKIP 117
- Full report: `prod_costing_audit_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unverifiable (27 cells)

- 4.9 & UP FREEZER BODY (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 2,3 MTR FREEZER · DRD · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · FRONT · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · SIDES · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (4 scenarios)

### Known defects — accepted, tracked, awaiting a work order (26 cells)

- UP TO 2,3 MTR FREEZER · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (2)
- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (24)

### Tolerated differences (25 cells)

- 4.9 & UP FREEZER BODY (2 · FRONT · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (3)
- 4.9 & UP FREEZER BODY (2 · ROOF · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (3)
- 4.9 & UP FREEZER BODY (2 · SIDES · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (3)
- UP TO 2,3 MTR FREEZER · FRONT · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (2)
- UP TO 2,3 MTR FREEZER · SIDES · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (2)
- UP TO 4.8 MT FREEZER  (2 · FRONT · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (4)
- UP TO 4.8 MT FREEZER  (2 · ROOF · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (4)
- UP TO 4.8 MT FREEZER  (2 · SIDES · [RULING] Manifests F + F2 (RT1 ruling 3 and addendum): prod prices 4G PU foam at Burt's 21 Sep 4G, R5 581 = the PU material's R4 100 (Burt's corrected 32D) x 5581/4100; the golden is his September workbook (4G R5 400), so every costed 4G PU foam line reads +3.35 % against it (32D matches the golden: both R4 100). A stop-gap: rebuild the golden from the 21 Sep workbooks, then remove this entry. EXPIRED means the golden refresh has not shipped. — review by 2026-10-15 (4)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
