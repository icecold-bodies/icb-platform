"""RT2 C11 (RT2_RULING_2) — ops/prod-rt2/rt2_all_compare.py refuses a page run older than the last data change.

In the 2 Oct window `rt2_all.sh afterD` compared the CLI (after Manifest D) with the newest finished page run, which
had been clicked BEFORE D: 48 cells "differed" that were simply D's own movement. The page run must now have STARTED
after the newest Manifest P / D apply or revert journal (rt2_all.sh passes that time), and still have finished within
the age limit. The decision is a pure function, tested here without a database.
"""
import importlib.util
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[2] / "ops" / "prod-rt2" / "rt2_all_compare.py"


def _load():
    spec = importlib.util.spec_from_file_location("rt2_all_compare", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rt2_all_compare"] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load()
APPLY_D = 1_790_933_603.0                     # 2 Oct 2026 11:33:23 SAST (09:33:23Z), the window's apply D


def test_a_page_run_after_the_last_data_change_is_usable():
    assert C.page_run_problem(age_min=2, max_age_min=45, started_epoch=APPLY_D + 60, not_before=APPLY_D) is None


def test_a_page_run_from_before_the_last_data_change_is_refused():
    """The window's case: page run #26 started 11:31:43, D applied 11:33:23."""
    why = C.page_run_problem(age_min=21, max_age_min=45, started_epoch=APPLY_D - 100, not_before=APPLY_D)
    assert why and "click All first" in why and "before the last data change" in why


def test_the_age_limit_still_applies():
    why = C.page_run_problem(age_min=50, max_age_min=45, started_epoch=APPLY_D + 60, not_before=APPLY_D)
    assert why and "click All again" in why


def test_no_data_change_on_record_means_only_the_age_rule():
    assert C.page_run_problem(age_min=10, max_age_min=45, started_epoch=1.0, not_before=0) is None


def test_negative_control_the_rule_is_the_start_not_the_finish():
    """A run that FINISHED after the change but STARTED before it priced (part of) the old data: refused."""
    why = C.page_run_problem(age_min=0, max_age_min=45, started_epoch=APPLY_D - 1, not_before=APPLY_D)
    assert why is not None
