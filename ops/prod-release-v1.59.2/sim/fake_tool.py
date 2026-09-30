"""Stand-in for backend/tools/audit_pricing_corrections.py in the rt1_data.sh simulation. Emulates the real
tool's dry-run / apply / revert OUTPUT CONTRACT (plan line, exit codes, journal + revert-record files) over a
state folder: $SIMSTATE/applied_a|b (0/1). Flags: $SIMSTATE/guard_fail, $SIMSTATE/plan_short."""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

S = Path(os.environ["SIMSTATE"])
args = sys.argv[1:]


def opt(name):
    return args[args.index(name) + 1] if name in args else None


def state(x):
    f = S / f"applied_{x}"
    return int(f.read_text()) if f.exists() else 0


if "--revert" in args:
    j = json.loads(Path(opt("--revert")).read_text())
    x = j["which"]
    if not state(x):
        print("REVERT ABORTED — nothing written:\n  - bom 1 .bom_conditions: moved since the apply")
        sys.exit(2)
    (S / f"applied_{x}").write_text("0")
    out = Path(opt("--out-dir")); out.mkdir(parents=True, exist_ok=True)
    rp = out / f"pricing_corrections_revert_prod_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    rp.write_text(json.dumps({"reverted": x}))
    print(f"REVERTED journal: {j['n']} lines restored. Record: {rp}")
    sys.exit(0)

m = Path(opt("--manifest"))
x = "a" if m.name == "manifest_a.yaml" else "b"
n = sum(1 for ln in m.read_text().splitlines() if ln.startswith("- finding:"))
sha = hashlib.sha256(m.read_bytes()).hexdigest()
print(f"database icb_platform (--target prod); manifest {m.name} sha256 {sha[:16]}…, {n} entries")
if (S / "guard_fail").exists():
    print("ABORT — 1 guard mismatch(es); the database is not where the manifest says. Nothing written:")
    print("  - R1 bom=5961 …: GUARD — found '[...]', manifest expects None")
    sys.exit(2)
todo, done = (0, n) if state(x) else (n, 0)
if (S / "plan_short").exists() and todo:
    todo, done = todo - 1, 1
print(f"\n{todo} to apply, {done} already applied.")
if not todo:
    print("nothing to apply.")
    sys.exit(0)
if "--apply" not in args:
    print("(DRY RUN — nothing written. Re-run with --apply.)")
    sys.exit(0)
(S / f"applied_{x}").write_text("1")
out = Path(opt("--out-dir")); out.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
jp = out / f"pricing_corrections_journal_prod_{ts}.json"
jp.write_text(json.dumps({"tool": "audit_pricing_corrections", "database": "icb_platform", "manifest_sha256": sha,
                          "which": x, "n": n}))
print(f"APPLIED {n} changes on {n} lines (0 bom_override_history rows). Journal: {jp}")
