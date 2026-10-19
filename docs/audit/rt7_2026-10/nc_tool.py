"""F6 negative controls for the RT7 tool: patch ONE piece of the fix out of the committed file, run the RT7 tests,
record which fail, restore the file from HEAD (git checkout). Refuses to start on a dirty file."""
import subprocess, sys, re
from pathlib import Path
W = Path(r"C:\Users\micge\Documents\icb-platform-rt7")
B = W / "backend"
PY = r"C:\Users\micge\Documents\icb-platform\backend\.venv\Scripts\python.exe"
NCS = [
  ("the amount pin (compare._pin_failure returns None)", "backend/tools/costing_audit/compare.py",
   "    key, net = pin_key(cell), cell_net(cell)\n    bad = []\n", "    return None\n    key, net = pin_key(cell), cell_net(cell)\n    bad = []\n"),
  ("the strict prod list (accepted._parse never strict)", "backend/tools/costing_audit/accepted.py",
   "        if strict:\n", "        if False:\n"),
  ("the one-sided cell's own reason (reapply drops base_reason)", "backend/tools/costing_audit/compare.py",
   '            d["reason"] = d.get("base_reason")          # the cell\'s own reason, kept when a pin overwrote it\n',
   '            d["reason"] = None\n'),
  ("review_by expiry (Accepted.expired always False)", "backend/tools/costing_audit/accepted.py",
   "        return self.review_by is not None and (today or date.today()) > self.review_by\n", "        return False\n"),
]
def git(*a): return subprocess.run(["git", "-C", str(W), *a], capture_output=True, text=True)
for name, rel, old, new in NCS:
    if git("status", "--porcelain", "--", rel).stdout.strip():
        sys.exit(f"REFUSED: {rel} is not clean")
    p = W / rel; s = p.read_text(encoding="utf-8")
    assert s.count(old) == 1, (name, s.count(old))
    p.write_text(s.replace(old, new), encoding="utf-8", newline="")
    r = subprocess.run([PY, "-m", "pytest", "tests/costing_audit/test_rt7_pins.py", "-o", "addopts=", "-p", "no:cacheprovider", "-q",
                        "--deselect", "tests/costing_audit/test_rt7_pins.py::test_the_committed_prod_list_and_snapshot_are_a_matched_pair"],
                       cwd=B, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1",
                       "DATABASE_URL": "postgresql+psycopg://icb_app:icb_app_dev@localhost:5432/icb_test", "SESSION_SECRET": "x"})
    git("checkout", "--", rel)
    failed = sorted(set(re.findall(r"FAILED tests/costing_audit/test_rt7_pins.py::(\S+)", r.stdout)))
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    print(f"NC: {name}\n    {tail}\n    failing: {failed}")
print("restored:", "clean" if not git("status", "--porcelain", "--", "backend/tools").stdout.strip() else "DIRTY")
