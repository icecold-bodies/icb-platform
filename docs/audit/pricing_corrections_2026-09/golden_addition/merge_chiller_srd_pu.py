"""v1.58 — add the chiller `srd_pu` scenarios to the committed chiller golden, and nothing else.

Why a merge and not `audit golden --pack chillers`: Burt's September workbook on this PC was
saved again on 27 Sep 07:43 (sha256 af64176d…) after the committed chiller golden was built
from it on 25 Sep (d87a5731…, no copy survives). Rebuilding the whole pack from the later save
would move ~375 existing cells (CHILLER MEDIUM's saved SIDES flag is now PU, CHILLER 2.3's FRONT
PU unit price reads 0, the picture-frame price moved). Michael's ruling, 28 Sep: keep the 84
committed scenarios untouched and add only the 14 new ones, recording their source.

Usage (from backend/):
    python -m tools.costing_audit golden --pack tests/costing_audit/packs/chillers.yaml \
        --workbook-dir <copy of the September folder> --golden-dir <SCRATCH> --work-dir <W>
    python ../docs/audit/pricing_corrections_2026-09/golden_addition/merge_chiller_srd_pu.py <SCRATCH>/chillers

The check before merging: outside the SRD section every new scenario must equal the committed
`srd` scenario of the same size within the pack tolerance (1 %) — the only intended difference
is the rear door's insulation. The merge refuses otherwise.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))

from tools.costing_audit.scenarios import load_pack  # noqa: E402

GOLDEN = BACKEND / "tests" / "costing_audit" / "golden" / "chillers"
PACK = BACKEND / "tests" / "costing_audit" / "packs" / "chillers.yaml"
VARIANT = "srd_pu"
TOL_PCT = 1.0


def main(scratch: Path) -> int:
    scratch_manifest = json.loads((scratch / "_manifest.json").read_text(encoding="utf-8"))
    manifest = json.loads((GOLDEN / "_manifest.json").read_text(encoding="utf-8"))
    if any(a.get("variant") == VARIANT for a in manifest.get("additions", [])):
        print(f"already merged ({VARIANT}) — nothing to do")
        return 0
    pack = load_pack(PACK)
    if scratch_manifest.get("pack_fingerprint") != pack.fingerprint():
        print("REFUSED: the scratch golden was not generated from the committed pack file")
        return 2
    added, checks = 0, []
    for sheet, fname in manifest["sheets"].items():
        cur = json.loads((GOLDEN / fname).read_text(encoding="utf-8"))
        new = json.loads((scratch / fname).read_text(encoding="utf-8"))
        have = {s["scenario"]["id"] for s in cur["scenarios"]}
        fresh = [s for s in new["scenarios"] if s["scenario"]["variant"] == VARIANT]
        if any(s["scenario"]["id"] in have for s in fresh):
            print(f"REFUSED: {fname} already holds {VARIANT} scenarios")
            return 2
        by_id = {s["scenario"]["id"]: s for s in cur["scenarios"]}
        for s in fresh:
            sid = s["scenario"]["id"]
            ref = by_id[sid[: -len(VARIANT)] + "srd"]
            for sec, ns in s["sections"].items():
                if sec == "SRD":
                    continue
                a, b = (ref["sections"].get(sec) or {}).get("total"), ns.get("total")
                if not a and not b:
                    continue
                pct = abs((b or 0) - (a or 0)) / abs(a) * 100 if a else float("inf")
                checks.append(pct)
                if pct > TOL_PCT:
                    print(f"REFUSED: {sid} {sec} differs from the committed srd scenario by {pct:.2f} %")
                    return 2
        # insert each new scenario right after its (L, W, H) group's last committed scenario
        out = []
        for s in cur["scenarios"]:
            out.append(s)
            if s["scenario"]["variant"] == "foam_4g":
                stem = s["scenario"]["id"][: -len("foam_4g")]
                out.extend(x for x in fresh if x["scenario"]["id"] == stem + VARIANT)
        if len(out) != len(cur["scenarios"]) + len(fresh):
            print(f"REFUSED: {fname}: could not place every {VARIANT} scenario")
            return 2
        cur["scenarios"] = out
        (GOLDEN / fname).write_text(json.dumps(cur, indent=1, default=str), encoding="utf-8")
        added += len(fresh)
    wb = scratch_manifest["workbook"]
    manifest["pack_fingerprint"] = pack.fingerprint()
    manifest["scenario_count"] = manifest["scenario_count"] + added
    manifest.setdefault("additions", []).append({
        "variant": VARIANT, "scenarios": added,
        "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at": scratch_manifest["generated_at"], "tool_version": scratch_manifest.get("tool_version"),
        "workbook": wb,
        "why": "v1.58: the chillers' SRD PU line had no audit cell (the named srd variant is EPS on every "
               "chiller). The September workbook had been saved again on 27 Sep 07:43, so only these "
               "scenarios come from that save; the other scenarios keep the 25 Sep source above.",
        "check": f"outside SRD every added scenario equals the committed srd scenario of the same size "
                 f"within {TOL_PCT} % (max {max(checks):.2f} % over {len(checks)} section cells)",
    })
    (GOLDEN / "_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(f"merged {added} {VARIANT} scenarios; max non-SRD difference {max(checks):.2f} % "
          f"over {len(checks)} section cells; pack fingerprint {pack.fingerprint()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
