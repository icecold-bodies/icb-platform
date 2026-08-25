# v1.51 §3.1 — PU foam classification and data fix

**Lane:** `feat/v1.51-pu-foam-4g` · **Migration:** `0046_pu_foam_4g_normalisation`
**Generated:** 25 Aug 2026, by running the migration's own `_classify()` over the dev `icb` database.

---

## 1. Why the numbers are decidable

Every PU price in Burt's workbook is built the same way:

```
unit_price = sheet_price x (1.22 x 2.44) / 2.98 x thickness
```

Dividing a stored price by the thickness its linked insulation toggle carries therefore yields a
**rate** that names the grade outright:

| Rate (per m² per m) | Meaning | Source |
|---|---|---|
| **4305.3718** | 32D PU FOAM | `4310 x 2.9768 / 2.98` — PU sheet C17 |
| **5868.6913** | 4G FOAM | `5875 x 2.9768 / 2.98` — PU sheet C19 |
| **5849.0635** | 4G FOAM, divided by **2.99** | Burt's typo on the Meat Body sheet |
| **4290.9726** | 32D, divided by 2.99 | same typo, 32D side (not present in the data) |

Price ratio **5875 / 4310 = 1.3631090487**.

**Tolerance = 0.1 %.** Observed data sits within **0.002 %** of its rate, while the two closest
classes (4G vs the 2.99 typo) are **0.335 %** apart — the band absorbs the real rounding and cannot
merge two grades. Locked by a test (`test_classifier_band_separates_the_two_closest_classes`).

## 2. Scan result — 160 PU foam cost rows

| Classification | Rows | Action |
|---|---:|---|
| `SHARED-DEFAULT` (no `unit_price_override`) | 105 | untouched — reads the shared per-section material price |
| `32D` | 40 | untouched — already the 32D side |
| `4G` | 8 | **rewritten** to the 32D value |
| `4G~2.99` | 1 | **rewritten**, typo corrected on the way |
| `UNCLASSIFIED` | 5 | **untouched and reported** |
| `NO-THICKNESS` | 1 | untouched — no linked insulation row to divide by |

## 3. BEFORE / AFTER — the 9 rewritten rows

| Body category | Section | bom_id | Thickness (m) | BEFORE | Rate | Class | AFTER |
|---|---|---:|---:|---:|---:|---|---:|
| EXPLOSIVE 4.9 AND UP | DRD | 3974 | 0.042 | 246.485 | 5868.69 | 4G | **180.8256** |
| EXPLOSIVE 4.9 AND UP | FRONT | 3940 | 0.042 | 246.485 | 5868.69 | 4G | **180.8256** |
| EXPLOSIVE 4.9 AND UP | ROOF | 4005 | 0.042 | 246.485 | 5868.69 | 4G | **180.8256** |
| EXPLOSIVE 4.9 AND UP | SIDES | 3996 | 0.042 | 246.485 | 5868.69 | 4G | **180.8256** |
| MEAT HANGER LARGE | DRD | 5877 | 0.060 | 352.120 | 5868.67 | 4G | **258.3212** |
| MEAT HANGER LARGE | SIDES | 5899 | 0.060 | 352.120 | 5868.67 | 4G | **258.3212** |
| MEAT HANGER LARGE | ROOF | 5910 | 0.100 | 586.870 | 5868.70 | 4G | **430.5378** |
| MEAT HANGER LARGE | FLOOR | 5921 | 0.100 | 586.870 | 5868.70 | 4G | **430.5378** |
| MEAT HANGER LARGE | FRONT | 5842 | 0.060 | 350.940 | 5849.00 | **4G~2.99** | **258.3195** |

Selecting 4G on any of these reproduces the old price to the cent (`x 1.3631090487`), so no quote
changes value by choosing what Burt's sheet used to do automatically.

**The typo row.** `MEAT HANGER LARGE / FRONT` is the row the BA flagged as dividing by 2.99 instead
of 2.98. The migration corrects it rather than replicating it, so it lands on **258.3195** —
alongside its correctly-typed DRD/SIDES siblings at 258.3212. The residual **0.0017** is the
rounding already frozen into the stored `350.940`; it is 0.0007 % of the line and is not invented
away.

## 4. UNCLASSIFIED — reported, not rewritten

| Body category | Section | bom_id | Thickness (m) | Price | Rate |
|---|---|---:|---:|---:|---:|
| RHINORANGE TRAILER | FRONT | 1797 | 0.100 | 637.380 | 6373.80 |
| RHINORANGE TRAILER | ROOF | 1840 | 0.100 | 637.380 | 6373.80 |
| RHINORANGE TRAILER | FLOOR | 1848 | 0.100 | 637.380 | 6373.80 |
| RHINORANGE TRAILER | DRD | 1808 | 0.060 | 382.430 | 6373.83 |
| RHINORANGE TRAILER | SIDES | 1830 | 0.051 | 325.060 | 6373.73 |

All five agree on an internal rate of **6373.80** to within 0.002 % — so the category is internally
*coherent*, it is simply built on a base price that is **neither 4310 nor 5875**. It is 8.61 % above
the 4G rate and 48.04 % above the 32D rate; no divisor, typo or thickness reading reconciles it.

The workbook survey says Rhinorange is all-4G. The stored numbers do not support that, and the
ratified guard is explicit — *an unrecognised value is not ours to reinterpret*. So:

* **nothing is written to these five rows;**
* Rhinorange therefore treats its stored price as the 32D side, and selecting 4G will quote
  1.36311 x 6373.80 — higher than anything the workbook ever produced;
* **action for Burt:** restate the Rhinorange PU rate on a known basis (32D or 4G off the current
  price list). Once it classifies, re-running 0046 picks it up automatically — the migration is
  idempotent and skips rows it has already journalled.

## 5. Categories confirmed 32D (rows carrying an explicit override)

EXPLOSIVE UP TO 2.7 · EXPLOSIVE 2.7 TO 4.8 · EXPLOSIVE 2.7 TO 4.8 OLD *(inactive)* ·
FREEZER 2.3 METER · FREEZER MEDIUM · FREEZER LARGE ·
ICECREAM UP TO 3,2 · ICECREAM UP TO 4.8 · ICECREAM 4.9 UP

Everything else (Chester Spec Meat, GRP Trailers, the Chillers, Dry Freight, Meat Hanger
Small-Medium, ADV Vacuum Panels, the deleted Explosive variants) carries **no override** and reads
the shared per-section material price. Those shared prices are common to every body, so rewriting
one would silently reprice categories this lane never classified — they are left alone.

## 6. What changes for Burt

Three categories stop defaulting to 4G and now default to **32D**, like every other body:

* **EXPLOSIVE 4.9 AND UP**
* **MEAT HANGER LARGE** (the "Meat Body" sheet)
* *(RHINORANGE TRAILER is a fourth in the workbook, but its price is unclassifiable — see §4.)*

Quoting any of them at the old price is now one click: **BODY OPTIONS → Insulation foam → 4G FOAM.**

## 7. Scope

This is **not** the August price update. A stale 32D price stays stale — only the *grade* is
normalised. 4G is derived from the stored 32D at calculation time, never stored, so the pair stays
exact through any future repricing of the 32D side.

The ratio itself lives in `admin_settings['costings.pu_foam_4g_factor']`, seeded by 0046 and guarded
so it never overwrites a value someone has set. When the next price list moves **both** sheet
prices, that one row is the thing to update — no deploy needed.

## 8. Reversibility

Every rewrite is journalled into `icb_costings.pu_foam_normalisation` (bom_id, old/new price,
classification, thickness, body, section). `downgrade()` replays the old prices back and drops the
table, so `up → down → up` is exact. The journal is also the live BEFORE/AFTER record on any
database the migration has touched — this document is the dev snapshot of it.
