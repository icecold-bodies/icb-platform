"""Stand-in for ops/prod-rt3/rt3_families.py in the rt3_families.sh simulation. It keeps the real tool's OUTPUT
CONTRACT (the plan line, the template-guard line, the journal file name, the exit codes: 0 ok, 2 refused) and keeps
its state in $SIMSTATE (applied = the families are on). The real tool itself is tested against a database by
backend/tests/test_rt3_families_tool.py and rehearsed on the local mirror (RT3_RETURN_2).

Flags (files in $SIMSTATE): guard_fail (prod moved: the dry-run refuses), plan_short (39 to apply), guard_line_bad
(the guard names another set), apply_refuse (the apply's in-transaction guard refuses), moved (revert refuses).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

S = Path(os.environ["SIMSTATE"])
N = 39 if (S / "plan_short").exists() else 40
GUARD = ("TEMPLATE GUARD: 16 of 16 active bodies keep their resolved template; changed: "
         + ("[11, 22]" if (S / "guard_line_bad").exists() else "[11, 22, 23, 28, 29, 30, 31, 32, 33, 35]")
         + " (allowed: the Q5 soft-deleted copies)")


def applied() -> bool:
    return (S / "applied").exists()


def main(argv) -> int:
    a = argv[1:]
    out = a[a.index("--out-dir") + 1] if "--out-dir" in a else None
    print("database icb_platform (--target prod); RT3 body families; plan sha256 0123456789abcdef…; tool sha256 fake…")
    if (S / "guard_fail").exists():
        print("  REFUSED: body 41 Manni RIGIDS CB is in group 2; the plan expects None (before). The transaction rolled back; nothing written.")
        return 2
    if "--apply" in a:
        if applied():
            print(f"0 to apply, {N} already applied.")
            print("nothing to apply.")
            return 0
        if (S / "apply_refuse").exists():
            print("  REFUSED: THE TEMPLATE GUARD (database, before commit): body 15 RHINORANGE TRAILER (active) ... The transaction rolled back; nothing written.")
            return 2
        (S / "applied").touch()
        Path(out).mkdir(parents=True, exist_ok=True)
        j = Path(out) / f"rt3_families_journal_prod_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        j.write_text(json.dumps({"tool": "rt3_families", "target": "prod", "database": "icb_platform"}), encoding="utf-8")
        print("TEMPLATE GUARD: every active body keeps its resolved template (checked in the database before the commit)")
        print(f"APPLIED {N} change(s). Journal: {j}")
        return 0
    if "--revert" in a:
        if (S / "moved").exists():
            print("  REFUSED: rows moved since the apply: body 12=7. The transaction rolled back; nothing written.")
            return 2
        if not applied():
            print("  done  every journaled row already holds its before-state")
            print("nothing to revert.")
            return 0
        (S / "applied").unlink()
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"rt3_families_revert_prod_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json").write_text("{}", encoding="utf-8")
        print("REVERTED: every journaled row is back; every body prints its pre-apply template.")
        return 0
    # dry-run
    if applied():
        print("TEMPLATE GUARD: 16 of 16 active bodies keep their resolved template; changed: none (allowed: the Q5 soft-deleted copies)")
        print(f"0 to apply, {N} already applied.")
        print("nothing to apply.")
    else:
        print(GUARD)
        print(f"{N} to apply, 0 already applied.")
        print("(DRY RUN — nothing written. Re-run with --apply.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
