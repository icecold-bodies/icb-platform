"""RT6 negative controls (F6): each one breaks ONE mechanism in the committed code, runs the tests that must catch
it, expects them to FAIL, then restores the file from git (git checkout -- <file>) and proves the tree is clean.
Run from the RT6 worktree's backend/ through wt6.ps1 (WT_DB=icb_test, MES_BASE=http://127.0.0.1:8018 for the
journey ones; the side port serves JS from disk, so JS controls need no restart)."""
import subprocess
import sys
from pathlib import Path

WT = Path(r"C:\Users\micge\Documents\icb-platform-rt6")
PY = sys.executable
J = "tests/journeys/test_rt6_rules_journey.py"
G = "tests/test_rt6_guards_api.py"

CONTROLS = [
    ("the check: breaches() never finds one", "backend/app/services/insulation_rules.py",
     "    seen, out = set(), []\n", "    seen, out = set(), []\n    return out\n",
     ["tests/test_rt6_insulation_rules.py::test_a_selected_insulation_breaches_exactly_when_the_family_forbids_it"]),
    ("classification: the EPS token is never read", "backend/app/services/insulation_rules.py",
     'toks = [i for i in INSULATIONS if _TOKEN[i].search(nu)]', 'toks = [i for i in INSULATIONS if i == "PU" and _TOKEN[i].search(nu)]',
     ["tests/test_rt6_insulation_rules.py::test_every_insulation_master_on_every_chiller_and_freezer_body_is_classified_as_prod_found"]),
    ("calculate stops warning", "backend/app/routers/calculator.py",
     'result["rule_breaches"] = rule_guard.body_breaches(tt, bom_rows, body)', 'result["rule_breaches"] = []',
     [f"{G}::test_calculate_warns_with_the_breach_and_still_prices"]),
    ("approve stops refusing", "backend/app/routers/calculator.py",
     "    _breaches = rule_guard.body_breaches(tt, bom_rows, body)\n    if _breaches:",
     "    _breaches = []\n    if _breaches:",
     [f"{G}::test_approve_refuses_a_breach_on_every_save_path_for_every_role",
      f"{G}::test_replace_and_overwrite_are_refused_before_they_touch_anything"]),
    ("Accept stops refusing", "backend/app/routers/calculator.py",
     '    rule_guard.refuse_saved(db, rec, "accepted")\n', "",
     [f"{G}::test_accept_refuses_a_saved_costing_that_breaches_the_current_rule",
      f"{G}::test_a_restored_breaching_costing_is_restored_but_not_accepted"]),
    ("a job from a breaching costing is made", "backend/app/services/production_jobs.py",
     '    rule_guard.refuse_saved(db, calc, "sent to production")\n', "",
     [f"{G}::test_the_pre_job_card_and_a_job_from_the_costing_are_refused"]),
    ("a job's pre-job card goes out", "backend/app/services/production_jobs.py",
     '    rule_guard.refuse_saved(db, calc, "sent to the floor")\n', "",
     [f"{G}::test_a_jobs_pre_job_card_is_refused_once_the_current_rule_forbids_its_costing"]),
    ("drafts stop warning", "backend/app/services/rule_guard.py",
     "    found = ir.draft_offers(rule, ir.classify_body(_views(rows)), nodes or {})",
     "    found = []",
     [f"{G}::test_a_draft_that_offers_a_forbidden_choice_is_saved_with_a_warning_and_so_is_its_restore"]),
    ("the family editor accepts a panel with nothing allowed", "backend/app/routers/admin_settings.py",
     "    if empty:\n        raise HTTPException(status_code=400, detail=(", "    if False:\n        raise HTTPException(status_code=400, detail=(",
     [f"{G}::test_the_family_editor_grid_sets_clears_and_refuses_and_an_older_form_leaves_it"]),
    ("the banner treats anything starting 'prod' as prod", "backend/app/env_banner.py",
     'return environment_name() == "prod"', 'return environment_name().startswith("prod")',
     ["tests/test_rt6_env_banner.py::test_anything_but_prod_shows_the_bar_and_the_title"]),
    ("the dashboard badge goes back to the database host", "backend/app/database.py",
     '    if env == "prod":\n        return "PROD (PostgreSQL)", detail, True',
     '    if host not in ("localhost", "127.0.0.1", "::1", ""):\n        return "PROD (PostgreSQL)", detail, True',
     ["tests/test_rt6_env_banner.py::test_the_dashboard_badge_reads_the_same_key_not_the_database_host"]),
    ("the backup helper checks gzip only", "ops/lib/icb_backup.sh",
     '[ "${ps[0]}" = 0 ] && [ "${ps[1]}" = 0 ]', '[ "${ps[1]}" = 0 ]',
     ["tests/test_ops_rt6.py::test_a_failed_pg_dump_stops_the_step"]),
    ("a retired kit is un-retired", "ops/prod-rt3/rt3_families.sh",
     'echo "RETIRED (RT6, 2026-10-06): $(basename "$0") no longer runs — see its header. Nothing was done." >&2; exit 3\n', "",
     ["tests/test_ops_rt6.py::test_no_script_in_ops_pipes_pg_dump_outside_the_helper"]),
    ("the safe paste never refuses", "ops/lib/icb_where.sh",
     '  [ -z "$WHERE_WHY" ] && return 0\n', "  return 0\n",
     ["tests/test_ops_rt6.py::test_a_wrong_machine_database_host_or_head_is_refused"]),
    ("the rules tool overwrites another rule", "ops/prod-rt6/rt6_rules.py",
     '            raise Refused(f"family {name!r} (#{gid}) already carries ANOTHER insulation rule {stored!r}: not overwritten")',
     '            state = "todo"',
     ["tests/test_rt6_rules_tool.py::test_another_rule_is_never_overwritten"]),
    # ── the page (journey; JS served from disk) ──
    ("the panels stop greying", "backend/app/static/js/calculator.js",
     "function _greyRuleForbidden() {\n", "function _greyRuleForbidden() {\n  return;\n",
     [f"{J}::test_pu_is_greyed_in_every_renderer_and_the_foam_picker_hides"]),
    ("the tree row click is no longer blocked", "backend/app/static/js/calculator.js",
     "      row.addEventListener('click', e => { e.preventDefault(); e.stopImmediatePropagation(); }, true);\n", "",
     [f"{J}::test_pu_is_greyed_in_every_renderer_and_the_foam_picker_hides[chill_tree-tree]"]),
    ("a greyed PU still counts as offered (the foam picker)", "backend/app/static/js/calculator.js",
     "const pu = (items || []).filter(it => it.is_body_option && !it.rule_forbidden",
     "const pu = (items || []).filter(it => it.is_body_option",
     [f"{J}::test_pu_is_greyed_in_every_renderer_and_the_foam_picker_hides[chill_draft-draft]"]),
    ("Remove does nothing", "backend/app/static/js/calculator.js",
     "async function removeRuleBreach(b) {\n", "async function removeRuleBreach(b) {\n  return;\n",
     [f"{J}::test_reopen_warns_remove_clears_it_and_the_overwrite_then_saves"]),
    ("the paste applies a forbidden row", "backend/app/static/js/calculator.js",
     "    if (rec.sides[yes[0]].row.rule_forbidden) { plan.skipped.push(_xpRuleRefusal(`${rec.group} ${yes[0]}`)); return; }\n", "",
     [f"{J}::test_paste_from_excel_refuses_the_pu_row_and_applies_the_rest"]),
    ("Switch ALL switches the forbidden panels too", "backend/app/static/js/calculator.js",
     "      if (it.rule_class && skipped.includes(it.rule_class.panel)) return;   // RT6 — leave that panel as it is\n", "",
     [f"{J}::test_switch_all_insulation_skips_the_forbidden_panels_and_says_so"]),
    ("the unused door is not named as such", "backend/app/static/js/calculator.js",
     "(unused ? ' — not used on this quote' : '')", "''",
     [f"{J}::test_a_forbidden_door_insulation_on_the_unused_door_is_named_as_such"]),
]


def pytest(tests):
    r = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-W", "ignore", *tests],
                       cwd=WT / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode


def main():
    out = []
    for name, rel, old, new, tests in CONTROLS:
        f = WT / rel
        text = f.read_text(encoding="utf-8")
        if text.count(old) != 1:
            out.append(f"SETUP  {name}: the anchor occurs {text.count(old)} times in {rel}")
            print(out[-1], flush=True)
            continue
        f.write_text(text.replace(old, new), encoding="utf-8", newline="")
        try:
            rc = pytest(tests)
        finally:
            subprocess.run(["git", "checkout", "--", rel], cwd=WT, check=True)
        ok = rc != 0
        out.append(f"{'CAUGHT' if ok else 'MISSED'} {name}  ({rel}; pytest exit {rc})")
        print(out[-1], flush=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=WT, capture_output=True,
                           text=True).stdout.strip()
    out.append(f"tree after restore: {'CLEAN' if not dirty else 'DIRTY: ' + dirty}")
    print(out[-1])
    caught = sum(1 for o in out if o.startswith("CAUGHT"))
    out.append(f"{caught}/{len(CONTROLS)} caught")
    print(out[-1])
    Path(sys.argv[1]).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
