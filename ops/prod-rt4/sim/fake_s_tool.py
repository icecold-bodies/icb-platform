"""Stand-in for backend/tools/audit_pricing_corrections.py running Manifest S in the rt4_data.sh simulation. Emulates
the real tool's OUTPUT CONTRACT for S (the plan line, the drafts line, the expect_unused_after line, the STOP / ABORT
refusals, exit codes, the journal + revert-record names and the journal's manifest_sha256) over a state folder:
$SIMSTATE/applied_s (0/1). Flags: guard_fail, unused_fail, plan_short.
The real tool is proven against real databases elsewhere (pytest; the mirror proof)."""
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


def applied():
    f = S / "applied_s"
    return int(f.read_text()) if f.exists() else 0


def out_file(stem):
    out = Path(opt("--out-dir"))
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"


if opt("--target") != "prod":
    print("fake: --target prod expected"); sys.exit(3)

if "--revert" in args:
    j = json.loads(Path(opt("--revert")).read_text())
    if not applied():
        print("REVERT ABORTED — nothing written:\n  - bom 793 .section: moved since the apply")
        sys.exit(2)
    (S / "applied_s").write_text("0")
    rp = out_file("pricing_corrections_revert_prod")
    rp.write_text(json.dumps({"lines": j["n"], "drafts": 1}))
    print(f"REVERTED journal: {j['n']} lines restored, 0 bom_override_history rows deleted, 1 draft(s) restored. Record: {rp}")
    sys.exit(0)

m = Path(opt("--manifest"))
text = m.read_text()
n = sum(1 for ln in text.splitlines() if ln == "    field: section")
nd = sum(1 for ln in text.splitlines() if ln.startswith("    old_key: "))
sha = hashlib.sha256(m.read_bytes()).hexdigest()
print(f"database icb_platform (--target prod); manifest {m.name} sha256 {sha[:16]}…, {n} entries")
if (S / "guard_fail").exists():
    print("ABORT — 1 guard mismatch(es); the database is not where the manifest says. Nothing written:")
    print("  - S1 bom=793 MANNI DF / 3MM MILD STEEL FLOOR / 4 MM BEND UP SUB FRAME .section: GUARD — found {'id': 64, ...}")
    sys.exit(2)
todo, done = (0, n) if applied() else (n, 0)
dtodo, ddone = (0, nd) if applied() else (nd, 0)
if (S / "plan_short").exists() and todo:
    todo, done = todo - 1, 1
print(f"\n{todo} to apply, {done} already applied.")
print(f"drafts: {dtodo} to apply, {ddone} already applied.")
if (S / "unused_fail").exists():
    print("STOP — after this manifest a section that must end up unused would still be named. Nothing written:")
    print("  - expect_unused_after: section 83 'DOOR FITTINGS SRD' would still be used by 1 line(s) this manifest "
          "does not move: bom 99999 (body 12)")
    sys.exit(2)
print("expect_unused_after [83, 84, 85]: no other line or draft names them — "
      + ("they are unused now." if not (todo or dtodo) else "they are unused once this applies."))
if not (todo or dtodo):
    print("nothing to apply.")
    sys.exit(0)
if "--apply" not in args:
    print("(DRY RUN — nothing written. Re-run with --apply.)")
    sys.exit(0)
(S / "applied_s").write_text("1")
jp = out_file("pricing_corrections_journal_prod")
jp.write_text(json.dumps({"tool": "audit_pricing_corrections", "manifest_sha256": sha, "n": n}))
print(f"APPLIED {n + nd} changes on {n} lines (0 bom_override_history rows, 1 draft(s)). Journal: {jp}")
