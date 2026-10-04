"""Check every line of noauth_probe_paths.txt against the local app (no session, read-only DB sessions)."""
import os, sys
assert "default_transaction_read_only=on" in os.environ.get("PGOPTIONS", "")
assert os.environ.get("MES_DEMO_AUTOLOGIN_USER") == ""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
bad = 0
for ln in open(sys.argv[1], encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#"):
        continue
    want, path = ln.split(None, 1)
    client.cookies.clear()
    r = client.get(path, follow_redirects=False)
    ok = str(r.status_code) == want
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} want {want} got {r.status_code} {path} {r.headers.get('location', '')}")
print("mismatches:", bad)
sys.exit(1 if bad else 0)
