"""Stand-in for ops/prod-rt1/rt1_factor.py in the WSL simulation (no Postgres there): same arguments (incl.
--manifest F|F2), same output contract (the plan line, exit 2 on a guard, the journal / revert file names and keys),
state in $SIMSTATE. The real tool is proven against a real database on the local mirror (MIRROR_PROOF.md §5b / §5c).
Flags in $SIMSTATE: no_journal (apply writes no journal), no_write (apply claims success but changes nothing)."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFESTS = {"F": ("1.3170731707317074", "1.362881562881563"), "F2": ("1.362881562881563", "1.361219512195122")}
S = Path(os.environ["SIMSTATE"])
VAL, UPD = S / "factor_value", S / "factor_updated"


def get():
    v = VAL.read_text().strip() if VAL.exists() else MANIFESTS["F"][0]
    u = UPD.read_text().strip() if UPD.exists() else "2026-09-04 09:00:00.123456"
    return v, u


def put(v, u):
    VAL.write_text(v + "\n"); UPD.write_text(u + "\n")


a = sys.argv[1:]
assert a[:2] == ["--target", "prod"], a
rest = a[2:]
M = "F"
if "--manifest" in rest:
    i = rest.index("--manifest"); M = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
BEFORE, AFTER = MANIFESTS[M]
out = Path(rest[rest.index("--out-dir") + 1]) if "--out-dir" in rest else None
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
v, u = get()
print(f"database icb_platform (--target prod); Manifest {M} (sim stand-in)")
if not rest:
    print(f"  row id 10  value {v!r}  updated_at {u}")
    if v == AFTER:
        print("0 to apply, 1 already applied."); sys.exit(0)
    if v != BEFORE:
        print(f"  REFUSED: the value is {v!r}"); sys.exit(2)
    print(f"  APPLY {BEFORE!r} -> {AFTER!r}")
    print("1 to apply, 0 already applied."); print("(DRY RUN — nothing written. Re-run with --apply.)"); sys.exit(0)
if rest[0] == "--apply":
    if v == AFTER:
        print("0 to apply, 1 already applied."); print("nothing to apply."); sys.exit(0)
    if v != BEFORE:
        print(f"  REFUSED: row id 10 holds {v!r}"); sys.exit(2)
    new_u = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    if not (S / "no_write").exists():
        put(AFTER, new_u)
    if not (S / "no_journal").exists():
        out.mkdir(parents=True, exist_ok=True)
        (out / f"rt1_factor_journal_prod_{ts}.json").write_text(json.dumps(
            {"tool": "rt1_factor", "manifest": M, "target": "prod", "database": "icb_platform", "key": "costings.pu_foam_4g_factor",
             "row_id": 10, "before": {"value": v, "updated_at": u}, "after": {"value": AFTER, "updated_at": new_u}}))
    print("APPLIED 1 change (admin_settings id 10)."); sys.exit(0)
if rest[0] == "--revert":
    j = json.loads(Path(rest[1]).read_text())
    if j.get("tool") != "rt1_factor" or j.get("manifest") != M:
        print(f"REFUSED: not a Manifest {M} journal"); sys.exit(1)
    b, af = j["before"], j["after"]
    if (v, u) == (b["value"], b["updated_at"]):
        print("nothing to revert."); sys.exit(0)
    if (v, u) != (af["value"], af["updated_at"]):
        print("  REFUSED: row id 10 moved since the apply"); sys.exit(2)
    put(b["value"], b["updated_at"])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"rt1_factor_revert_prod_{ts}.json").write_text(json.dumps({"tool": "rt1_factor", "manifest": M, "to": b}))
    print(f"REVERTED byte-exact: value {b['value']!r}, updated_at {b['updated_at']}."); sys.exit(0)
print("usage"); sys.exit(1)
