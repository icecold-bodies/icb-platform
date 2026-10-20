"""RT7 (RT7_RULING_1 Q4): the costing audit runs ALL FIVE packs on every PR (no path filter), on every push to
backport/v1.39-base (the squash commit Michael merges), and on demand — and has no `schedule` (GitHub fires
schedules only from the default branch, so the old nightly never ran for this branch).
RT7_RULING_1B G1: the snapshot is loaded and checked column for column in its own step, BEFORE the pack run."""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "costing-audit.yml"
PACKS = ["smoke", "chillers", "freezers", "icecream", "explosive"]

# The 9017c0b workflow's triggers and matrix (before RT7) — the negative control: the check must refuse it.
BEFORE_RT7 = """
on:
  pull_request:
    paths:
      - "backend/app/formula_engine.py"
      - "backend/tools/costing_audit/**"
  schedule:
    - cron: "30 2 * * *"
  workflow_dispatch:
jobs:
  audit:
    strategy:
      matrix:
        pack: ${{ fromJSON(github.event_name == 'pull_request' && '["smoke"]' || '["smoke","chillers","freezers","icecream","explosive"]') }}
    steps:
      - name: Audit run
        run: python -m tools.costing_audit run --pack ${{ matrix.pack }} --mes-snapshot --env prod
"""


def problems(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    on = doc.get("on", doc.get(True)) or {}            # YAML 1.1 reads a bare `on:` key as boolean True
    out = []
    if "pull_request" not in on:
        out.append("no pull_request trigger")
    elif isinstance(on["pull_request"], dict) and set(on["pull_request"]) & {"paths", "paths-ignore", "branches"}:
        out.append(f"pull_request is filtered: {sorted(on['pull_request'])}")
    push = on.get("push") or {}
    if (push.get("branches") if isinstance(push, dict) else None) != ["backport/v1.39-base"]:
        out.append(f"push must run on exactly backport/v1.39-base, not {push!r}")
    if "workflow_dispatch" not in on:
        out.append("no workflow_dispatch")
    if "schedule" in on:
        out.append("a schedule is configured (it never fires off the default branch)")
    pack = doc["jobs"]["audit"]["strategy"]["matrix"]["pack"]
    if pack != PACKS:
        out.append(f"the matrix is not the five packs on every trigger: {pack!r}")
    runs = [st.get("run", "") for st in doc["jobs"]["audit"].get("steps", [])]
    load = next((i for i, r in enumerate(runs) if "tools.costing_audit load-snapshot" in r), None)
    run = next((i for i, r in enumerate(runs) if "tools.costing_audit run " in r), None)
    if load is None or run is None or load > run:
        out.append("no load-fidelity step (`audit load-snapshot`) before the pack run")
    return out


def test_the_audit_runs_all_five_packs_on_every_pr_and_every_push_to_base():
    assert problems(WORKFLOW.read_text(encoding="utf-8")) == []


def test_negative_control_the_pre_rt7_triggers_are_refused():
    found = problems(BEFORE_RT7)
    assert any("pull_request is filtered" in p for p in found)
    assert any("push must run" in p for p in found)
    assert any("schedule" in p for p in found)
    assert any("matrix is not the five packs" in p for p in found)
    assert any("no load-fidelity step" in p for p in found)
