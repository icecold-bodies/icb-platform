"""v1.52 — September price import: scope filter + PU grade-flavour resolution.

Pure-function tests, no DB (mirrors test_v1_51_insulation_foam.py). The two
things that must hold before the import is allowed near a database:

  1. THE SCOPE FILTER — the five Manni sheets and Sheet1 are refused by code
     (Michael's ruling), AELER PANELS falls away as unmapped, and a sheet the
     §3.0 mapping has never seen aborts the run rather than guessing.
  2. THE PU RULES — a covered PU line stores 32D no matter which grade Burt's
     sheet displays. Every case below is a REAL row from the September
     manifest + the dev DB, including the two traps:
       * EXPLOSIVE 4.9 AND UP displays 4G prices while 0046 stored 32D — the
         manifest value must be divided by the NEW factor, or selecting 4G
         double-counts;
       * FREEZER LARGE rows 32/118 have an (old, new) ratio that LOOKS like
         the 4G sheet move (Burt fixed a thickness on the way) — continuity
         against the stored price must win, keeping them verbatim 32D.
"""
import csv
import importlib.util
import sys
from pathlib import Path

import pytest

# tools/ is not a package — load by path, like the 0046 migration tests do.
_TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


IMP = _load("september_price_import")


# ── constants are the ratified September numbers ─────────────────────────────

def test_the_ratified_september_numbers():
    assert IMP.SHEET_32D_OLD == 4310.0 and IMP.SHEET_32D_NEW == 4100.0
    assert IMP.SHEET_4G_OLD == 5875.0 and IMP.SHEET_4G_NEW == 5400.0
    assert IMP.FACTOR_NEW == pytest.approx(1.3170731707317074, abs=1e-12)
    assert IMP.SCALE_32D == pytest.approx(4100.0 / 4310.0, abs=1e-12)


# ── scope filter (ruling enforced in code) ───────────────────────────────────

def _manifest_csv(tmp_path, sheets):
    p = tmp_path / "m.csv"
    cols = ["sheet", "section", "row", "desc_old", "desc_new", "price_old",
            "price_new", "total_old", "total_new", "desc_changed",
            "price_changed", "total_changed", "highlighted"]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, s in enumerate(sheets):
            w.writerow({"sheet": s, "section": "FRONT", "row": 30 + i,
                        "desc_old": "X", "desc_new": "X", "price_old": "1",
                        "price_new": "2", "total_old": "1", "total_new": "2",
                        "desc_changed": "False", "price_changed": "True",
                        "total_changed": "True", "highlighted": "False"})
    return str(p)


def test_manni_and_sheet1_are_refused_even_when_present(tmp_path):
    path = _manifest_csv(tmp_path, ["Manni RIGIDS CB", "Manni DF", "Sheet1",
                                    "MEAT BODY", "AELER PANELS"])
    in_scope, refused, unmapped = IMP.load_manifest(path)
    assert [r["sheet"] for r in refused] == ["Manni RIGIDS CB", "Manni DF", "Sheet1"]
    assert [r["sheet"] for r in unmapped] == ["AELER PANELS"]
    assert [r["sheet"] for r in in_scope] == ["MEAT BODY"]


def test_every_manni_sheet_is_on_the_refused_list():
    assert {"Manni RIGIDS CB", "Manni RIGIDS FB", "Manni Bakkie Rigids",
            "Manni TRAILERS", "Manni DF", "Sheet1"} == IMP.REFUSED_SHEETS


def test_an_unknown_sheet_aborts_instead_of_guessing(tmp_path):
    path = _manifest_csv(tmp_path, ["A SHEET NOBODY MAPPED"])
    with pytest.raises(SystemExit):
        IMP.load_manifest(path)


def test_sheet_names_keep_their_exact_spelling():
    # Leading/trailing spaces are load-bearing in the workbook tab names.
    assert " UP TO 2,3 MTR FREEZER " in IMP.SHEET_TO_TRAILER
    assert " 4.9 & UP CHILLER AND 2.5 WIDE " in IMP.SHEET_TO_TRAILER
    assert " icecream 4.9 up" in IMP.SHEET_TO_TRAILER


# ── PU rules, on the real September rows ─────────────────────────────────────

def test_pu_32d_body_stores_the_manifest_value_verbatim():
    # CHESTER-family stored=258.321226 (0046-journalled 32D), manifest
    # 258.3223 -> 245.7358 (exact 4100/4310).
    rule, val = IMP.resolve_covered_pu(258.321226, 258.3223087248322, 245.73583892617447)
    assert rule == "PU-32D"
    assert val == pytest.approx(245.73583892617447)


def test_pu_4g_display_body_divides_by_the_new_factor():
    # EXPLOSIVE 4.9 AND UP: stored 32D 180.825591; sheet displays 4G
    # 246.485 -> 226.556. Storing the manifest number verbatim would
    # double-count the factor at calculation time.
    rule, val = IMP.resolve_covered_pu(180.825591, 246.48503355704702, 226.55645637583896)
    assert rule == "PU-4G-DISPLAY"
    assert val == pytest.approx(226.55645637583896 / IMP.FACTOR_NEW)
    # and the derived 4G price equals Burt's displayed September number
    assert val * IMP.FACTOR_NEW == pytest.approx(226.55645637583896)


def test_pu_rhinorange_continuation_stays_verbatim():
    # RHINORANGE: 0046 left these UNCLASSIFIED (rate 6373.8); September moves
    # them by exactly the 4G sheet ratio. Status quo preserved, flagged.
    rule, val = IMP.resolve_covered_pu(637.38, 637.3783557046979, 585.8456375838927)
    assert rule == "PU-4G-CONTINUATION"
    assert val == pytest.approx(585.8456375838927)


def test_pu_freezer_large_trap_resolves_as_32d_not_4g():
    # FREEZER LARGE rows 32/118: (old, new) ratio 0.92059 sits near the 4G
    # sheet move (0.919149) because Burt also fixed a thickness — but the
    # STORED price continuity (258.32 x 4100/4310 = 245.737) says 32D.
    rule, val = IMP.resolve_covered_pu(258.32, 266.9330523489933, 245.73583892617447)
    assert rule == "PU-32D"
    assert val == pytest.approx(245.73583892617447)


def test_pu_chester_gets_a_new_override_flavoured_from_the_manifest_pair():
    # No stored override (reads the shared per-section default): the manifest
    # pair itself is 32D-flavoured -> create the override at the new value.
    rule, val = IMP.resolve_covered_pu(None, 258.3223087248322, 245.73583892617447)
    assert rule == "PU-32D(new override)"
    assert val == pytest.approx(245.73583892617447)


def test_pu_unresolvable_goes_to_review_not_to_the_db():
    assert IMP.resolve_covered_pu(500.0, 100.0, 90.0) == (None, None)
    assert IMP.resolve_covered_pu(None, None, 90.0) == (None, None)
    assert IMP.resolve_covered_pu(None, 100.0, None) == (None, None)


# ── the 4 Sep prod pairing-shift regression ──────────────────────────────────
#
# Prod's FREEZER MEDIUM FRONT "4MM PF PLYWOOD" line carried a variant name, so
# the group had 4 manifest rows against 3 lines. The old fallback zipped them
# in order, shifting every pairing one section down — the SIDES line took the
# DRD row's R86.58 instead of its own R68.79. With the fix, a deficit group
# pairs strictly by section and the row with no line goes UNMATCHED.

class _FakeDb:
    """Just enough of Db for match_rows: the name-grouped lines + src_row."""

    def __init__(self, lines):
        from collections import defaultdict
        self.by_tt_name = defaultdict(list)
        for b in lines:
            self.by_tt_name[(b["trailer_type_id"], b["_norm_name"])].append(b)

    def src_row(self, b):
        return b.get("_src_row")


def _mrow(sheet, row, section, old, new, p_old, p_new):
    return {"sheet": sheet, "row": str(row), "section": section,
            "desc_old": old, "desc_new": new,
            "price_old": str(p_old), "price_new": str(p_new),
            "price_changed": "True", "desc_changed": "False",
            "total_changed": "True", "highlighted": "False"}


def _line(bid, tid, name, section, src_row):
    return {"id": bid, "trailer_type_id": tid, "material_id": bid + 1000,
            "bom_section": section, "sort_order": bid, "source_cell": f"H{src_row}",
            "_norm_name": name, "_src_row": src_row,
            "is_body_option": False, "unit_price_override": None,
            "skin_formula_id": None, "taping_block_id": None,
            "floor_plate_id": None, "mounting_cleat_id": None,
            "body_option_linked_id": None}


def test_deficit_group_pairs_by_section_never_by_blind_zip():
    sheet = " UP TO 4.8 MT FREEZER  (2"       # trailer 20 in the §3.0 mapping
    rows = [
        _mrow(sheet, 35, "FRONT", "4MM PF PLYWOOD", "4MM PF PLYWOOD", 71.48, 68.79),
        _mrow(sheet, 49, "SRD", "4MM PF PLYWOOD", "4MM PF PLYWOOD", 95.64, 86.58),
        _mrow(sheet, 86, "DRD", "4MM PF PLYWOOD", "4MM PF PLYWOOD", 95.64, 86.58),
        _mrow(sheet, 119, "SIDES", "4MM PF PLYWOOD", "4MM PF PLYWOOD", 71.48, 68.79),
    ]
    # FRONT's line is variant-named on prod, so only 3 lines carry the group name
    lines = [_line(1, 20, "4MM PF PLYWOOD", "SRD", 49),
             _line(2, 20, "4MM PF PLYWOOD", "DRD", 86),
             _line(3, 20, "4MM PF PLYWOOD", "SIDES", 119)]
    matched, unmatched, ambiguous, _ = IMP.match_rows(_FakeDb(lines), rows)

    assert not ambiguous
    # every pairing is section-true — the SIDES line gets the SIDES row (68.79)
    for mr, b in matched:
        assert IMP.norm(mr["section"]) == IMP.norm(b["bom_section"]), \
            f"row {mr['row']} ({mr['section']}) paired onto a {b['bom_section']} line"
    paired = {b["bom_section"]: mr for mr, b in matched}
    assert float(paired["SIDES"]["price_new"]) == 68.79
    # the row whose line is variant-named goes UNMATCHED, not onto a neighbour
    assert [r["section"] for r in unmatched] == ["FRONT"]


def test_equal_count_groups_still_zip_in_row_order():
    # the dev-proven fast path is unchanged: equal counts pair 1:1 in order
    sheet = " UP TO 4.8 MT FREEZER  (2"
    rows = [_mrow(sheet, 30, "FRONT", "X SKIN", "Y SKIN", 272.27, 213.11),
            _mrow(sheet, 44, "SRD", "X SKIN", "Y SKIN", 272.27, 213.11)]
    lines = [_line(1, 20, "X SKIN", "FRONT", 30), _line(2, 20, "X SKIN", "SRD", 44)]
    matched, unmatched, ambiguous, _ = IMP.match_rows(_FakeDb(lines), rows)
    assert not unmatched and not ambiguous
    assert {(mr["section"], b["bom_section"]) for mr, b in matched} == \
        {("FRONT", "FRONT"), ("SRD", "SRD")}
