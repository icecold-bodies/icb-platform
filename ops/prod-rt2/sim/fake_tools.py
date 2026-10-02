"""Stand-in for backend/tools/audit_pricing_corrections.py (Manifest P) AND ops/prod-rt2/rt2_defaults.py (Manifest D)
in the rt2_data.sh simulation. Emulates each real tool's OUTPUT CONTRACT (plan line, exit codes, the "P first" refusal,
the OTHERS_4G line, journal + revert-record names and the fields the wrapper reads) over a state folder:
$SIMSTATE/applied_p|applied_d (0/1). Flags: guard_fail_p, plan_short_p, others_4g.
The real tools are proven against real databases elsewhere (pytest; the mirror)."""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

S = Path(os.environ["SIMSTATE"])
tool, args = sys.argv[1], sys.argv[2:]


def opt(name):
    return args[args.index(name) + 1] if name in args else None


def state(x):
    f = S / f"applied_{x}"
    return int(f.read_text()) if f.exists() else 0


def put(x, v):
    (S / f"applied_{x}").write_text(str(v))


def out_file(stem):
    out = Path(opt("--out-dir"))
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"


if "--target" not in args or opt("--target") != "prod":
    print("fake: --target prod expected"); sys.exit(3)

if tool == "P":
    if "--revert" in args:
        j = json.loads(Path(opt("--revert")).read_text())
        if not state("p"):
            print("REVERT ABORTED — nothing written:\n  - bom 2560 .unit_price_override: moved since the apply")
            sys.exit(2)
        put("p", 0)
        rp = out_file("pricing_corrections_revert_prod")
        rp.write_text(json.dumps({"reverted": j["n"]}))
        print(f"REVERTED journal: {j['n']} lines restored. Record: {rp}")
        sys.exit(0)
    m = Path(opt("--manifest"))
    n = sum(1 for ln in m.read_text().splitlines() if ln.startswith("- finding:"))
    sha = hashlib.sha256(m.read_bytes()).hexdigest()
    print(f"database icb_platform (--target prod); manifest {m.name} sha256 {sha[:16]}…, {n} entries")
    if (S / "guard_fail_p").exists():
        print("ABORT — 1 guard mismatch(es); the database is not where the manifest says. Nothing written:")
        print("  - P1 bom=2560 …: GUARD — found 4095.0, manifest expects 4100.0")
        sys.exit(2)
    todo, done = (0, n) if state("p") else (n, 0)
    if (S / "plan_short_p").exists() and todo:
        todo, done = todo - 1, 1
    print(f"\n{todo} to apply, {done} already applied.")
    if not todo:
        print("nothing to apply."); sys.exit(0)
    if "--apply" not in args:
        print("(DRY RUN — nothing written. Re-run with --apply.)"); sys.exit(0)
    put("p", 1)
    jp = out_file("pricing_corrections_journal_prod")
    jp.write_text(json.dumps({"tool": "audit_pricing_corrections", "database": "icb_platform", "manifest_sha256": sha, "n": n}))
    print(f"APPLIED {n} changes on {n} lines (0 bom_override_history rows). Journal: {jp}")
    sys.exit(0)

# D — rt2_defaults.py
print("database icb_platform (--target prod); Manifest D: icb_costings.trailer_types.default_insulation_foam; tool sha256 fake…")
if "--revert" in args:
    j = json.loads(Path(opt("--revert")).read_text())
    assert j["tool"] == "rt2_defaults"
    if not state("d"):
        print("  done  every journaled body already holds its before-state ('32D')\nnothing to revert."); sys.exit(0)
    put("d", 0)
    rp = out_file("rt2_defaults_revert_prod")
    rp.write_text(json.dumps({"tool": "rt2_defaults", "manifest": "D"}))
    print(f"REVERTED 4 row(s) byte-exact to '32D'. Record: {rp}")
    sys.exit(0)
if not state("d") and not state("p"):
    print("  REFUSED: P first: 3 PU foam line(s) on these bodies still carry their own price (body 24 bom 3946 SIDES own "
          "R234.15; …). A 4G default over them would charge 4G twice — apply Manifest P, then D. "
          "The transaction rolled back; nothing written.")
    sys.exit(2)
others = "OTHERS_4G: 1 — 21 FREEZER LARGE" if (S / "others_4g").exists() else "OTHERS_4G: 0 (every other body opens on 32D)"
todo, done = (0, 4) if state("d") else (4, 0)
if "--apply" in args and todo:
    put("d", 1)
    jp = out_file("rt2_defaults_journal_prod")
    jp.write_text(json.dumps({"tool": "rt2_defaults", "manifest": "D", "database": "icb_platform", "target": "prod",
                              "rows": [{"id": i, "before": "32D", "after": "4G"} for i in (12, 36, 24, 15)]}))
    print(others)
    print(f"APPLIED 4 change(s) (trailer_types ids [12, 15, 24, 36]). Journal: {jp}")
    sys.exit(0)
for i in (12, 36, 24, 15):
    print(f"  {'done ' if state('d') else 'APPLY'} body {i}")
print(others)
print(f"{todo} to apply, {done} already applied.")
print("nothing to apply." if not todo else "(DRY RUN — nothing written. Re-run with --apply.)")
sys.exit(0)
