# v1.58.1 SRD rear frame — §3.0 discovery (CA → BA, 28 Sep 2026)

Lane `data/v1.58.1-srd-rear-frame`, worktree `icb-platform-srd-rear-frame`, cut from `de74796` (#198 merged;
dispatch allows 48231f4 or later). Nothing written anywhere yet. Dev reads were made in a read-only
session; the **prod reads are pending one Michael paste** (§6).

## Summary for the BA

1. **Scope (dev rehearsal):** 17 v2 bodies, **144 REAR FRAME lines**. These are the 12 audited bodies
   (102 lines) plus MEAT HANGER LARGE, MEAT HANGER SMALL-MEDIUM, DRY FREIGHT TRAILER, RHINORANGE (9 lines
   each) and RIGID DRY FREIGHT (6 lines, whose only SRD master is named `SRD`). Every line has NULL
   conditions and `always`. Prod may differ. The prod list comes with the paste.
2. **8 classic bodies are out by mechanism.** The engine evaluates `bom_conditions` only when
   `configurator_v2` is true (`calculator.py:452`). A rule on ADV VACUUM, CHESTER, GRP, MANNI BAKKI / FB /
   TRAILERS / DF or TAUT LINER would be inert. **BA: confirm they stay out.** They would need a different
   mechanism.
3. **Rule shape:** read from the endpoint's code (`trailers.py:3790-3800`). **It could not be authored by
   hand**, because the editor does not offer the SRD flags (point 4). Include mode stores a bare JSON list:
   `[{"option": "SRD EPS", "equals": "N", "option_id": <SRD EPS id>}, {"option": "SRD PU", "equals": "N", "option_id": <SRD PU id>}]`
   It uses `json.dumps` default separators, which is byte-identical in form to the existing SRD-section
   lines. Proposal: author it through the same PATCH the editor calls, on :8011 against dev, then read it
   back and revert it. That keeps default 2's intent.
4. **⚠ PICKER SCOPE — STOP (default 4).** On dev, the SRD flags are **OUT of scope for the REAR FRAME
   category on all 16 drafted v2 bodies**:
   - The flags live at `DOOR TYPE / SRD DOORS / category SRD`. On CHILLER LARGE and DRY FREIGHT they live
     at `DOOR TYPE / category SRD`.
   - REAR FRAME is a root category. On ICECREAM 4.8 it sits inside a folder named `REAR FRAME + FLOOR PLATE`.
   - The editor offers only the FRONT/SIDES/ROOF(/FLOOR) EPS/PU flags there.

   Consequence (`admin_visual_configurator_settings.html:1540-1553`): opening a REAR FRAME item's rule and
   saving it **replaces** the rule with the first offered option, for example `FRONT EPS = N`. The rule
   is not just dropped; it is silently rewritten into a wrong rule. Remedy options for the BA:
   - (a) Michael restructures the drafts so REAR FRAME sits under the DOOR TYPE folder. This risks the
     client-side door-folder exclusion, which is rejected mechanism (a).
   - (b) Accept the exposure and bank it: REAR FRAME rules are tool-owned and never edited in the
     Designer. The CI audit catches any drift.
   - (c) A micro-lane: the editor keeps saved out-of-scope references instead of replacing them. This is
     a code change.

   **CA recommends (b) now and (c) as a follow-on.** The prod picker result comes with the paste.
5. **Bodies where the rule never fires:**
   - RHINORANGE's draft has **no SRD flags**, so the calculator never sends an SRD master there. The rule
     is harmless but fixes nothing on that body.
   - RIGID DRY FREIGHT has **no server draft**, so the rule would be `SRD = N`.
   - Manni RIGIDS CB (section 87) has no masters at all, so it is out.
6. **CHILLER LARGE** has both the `DOOR TYPE SRD` master (7233) and `SRD EPS/PU`. No draft flag is bound
   to `SRD`. Proposal: the EPS/PU pair only, as default 1's main case.
7. **Correction to the dispatch:** ICECREAM LARGE **has** `DRD EPS` (5425). All 12 audited bodies carry all
   four door masters.
8. **Part B:**
   - Both MEAT HANGERs have an `SRD PU` master: 5981 and 6289 on dev, at thickness 0.
   - **Burt's rows exist.** Rows `MEAT BODY!H46` and `SMALL MEAT BODY UP TO 5,2!H46` (the lines'
     `source_cell`, mapping.py sheets → trailers 12/36) are `D*E*C13*PU!C17/2.98 × F × I × 2`. That is the F1
     shape term for term.
   - Both sheets save `SRD PU = N` (cached 0), so the proof sets a thickness and compares the engine with
     Burt's expression evaluated by hand.
   - Dev ≠ prod on 5851/6159. Dev has `1.22*2.44*0*2` × R461.26, while prod is at R24.4k. **The dev guard
     for these two rows will mismatch.** I will report that and not force it, as the dispatch anticipates.
   - 5585 is as expected.
   - Workbook read: `September costings\GRP Costings 2018.xlsx`, sha `af64176d…` (the 27 Sep re-save).
     Only rows 1–70 of these two sheets were read.
9. **Negative-control risk checked:**
   - The audit's `drd` / `all_eps` / `all_pu` / custom variants set the non-quoted door's panel to `none`
     (`scenarios.py:224-255`). So no SRD master is sent on a DRD cell.
   - Whether real UI payloads ever send an SRD master on a DRD quote cannot be read on dev. None of dev's
     18 saved v2 costings carries door sections. The prod paste answers it (section C: *DRD + "rule WOULD
     ZERO RF" must be 0*).
10. **Side note:** a soft-excluded line keeps its `quantity` and only its cost is 0. The comment at
    `calculator.py:587` says the quantity is zeroed; it is not. Every export strips excluded lines
    (`services/__init__.py:154`, `quote_document.py:171`), so check (c) should pass. It will be proven at §3.3.

## Prod paste (read only) — needs Michael's OK to stage

These files are staged at `ops/prod-srd-rear-frame/` (LF, SHA256SUMS, `bash -n` clean):
- `srd_discovery.py`: sections A–D, one `default_transaction_read_only` session, no people columns.
- `srd_discovery.sh`: sudo wrapper that checks the db name.

The CA copies them to `/tmp/icb-srd-discovery` over the `icb@` key, then Michael runs:

    sudo bash /tmp/icb-srd-discovery/srd_discovery.sh

and sends back the output folder name.

---

## After BA ruling 6a (29 Sep) — interim, before the prod paste

**⚠ CHILLER LARGE: the pair rule from ruling §3 would zero REAR FRAME on real double-door quotes.**
- On CHILLER LARGE the door is picked by the DOOR TYPE masters (7232 DRD / 7233 SRD). The SRD insulation radio
  stays ticked next to it: on :8011 with DRD picked the payload carries `7232: true, 3435 SRD EPS: true`.
- On dev, the saved double-door quotes A32795 (×2) and A32817 carry `SRD EPS = true` with DRD. Re-priced with the
  pair rule, their REAR FRAME goes R5 518.57 → R0 (`!! DRD CHANGED`).
- **CA proposal:** on a body with a DOOR TYPE `SRD` master, use `SRD is not selected` (7233). With that rule, all
  18 saved dev double-door quotes are unchanged to the cent. The discovery script now builds that rule for
  CHILLER LARGE. **BA: please confirm.**

**§3 check:** the calculator does reach 7233 (it is the DOOR TYPE radio in the draft). A CHILLER LARGE SRD quote
prices SRD + SRD DOOR FITTINGS and drops DRD + DRD DOOR FITTINGS (:8011, dev). **No CHILLER LARGE defect.**

**§4 check:** RIGID DRY FREIGHT's server tree offers DOOR TYPE (PICK ONE) → SRD. With SRD picked: `6645 SRD: true`,
SRD + SRD DOOR FITTINGS priced, DRD dropped. `SRD is not selected` will fire.

**Door-folder body spot check (FREEZER MEDIUM):** with DRD, both SRD masters are false. With SRD DOORS,
`SRD PU = true`. The pair rule is right for folder bodies.

**B2 sweep (dev):** 230 existing item rules on drafted v2 bodies, **all in scope**. None is exposed today, so only
the new REAR FRAME rules would be.

**Dev scope:** 16 bodies, 135 REAR FRAME lines (the 12 audited = 102, MEAT HANGER L 9 + SM 9, DRY FREIGHT 9,
RIGID DRY FREIGHT 6). Active classic bodies that offer SRD (for the BA's separate item): ADV VACUUM PANELS,
CHESTER SPEC MEAT BODY, GRP TRAILERS, MANNI BAKKI RIGIDS, MANNI DF, MANNI RIGIDS FB, MANNI TRAILERS.

**Side effect, repaired:** switching the door on :8011 carried the rear-door thickness into the dev Body Templates
of FREEZER MEDIUM (2535 → 2537) and CHILLER LARGE (3433 → 3435), which is the banked door-toggle trap. Both were
switched back to DRD in the calculator. The DB was verified: 2535 = 0.06, 3433 = 0.06, and the SRD masters are 0.

**Prod paste:** the kit is v2 (sha in `ops/prod-srd-rear-frame/SHA256SUMS`). The auto-mode classifier refused the
CA's own copy to the VM's `/tmp`, so Michael copies it (see the CA's message).
