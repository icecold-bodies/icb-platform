# RT10 side-port server: the rt10 worktree's backend on $env:WT_PORT against a LOCAL database ($env:WT_DB, default
# icb_test). Never :8000 (Michael's). Repo dev credentials only (deploy/postgres/init_test.sql) - the dev .env is not
# read. Every outbound channel is off; demo autologin ON (journeys), own origin allowed. The SPA shell is
# $env:WT_DIST (default: the main clone's frontend/dist = the v1.62.0 SPA, index-BBI2d9Oo, until rt10 builds its own).
$ErrorActionPreference = 'Stop'
$db   = if ($env:WT_DB)   { $env:WT_DB }   else { 'icb_test' }
$port = if ($env:WT_PORT) { $env:WT_PORT } else { '8012' }
if ($port -eq '8000') { throw 'refusing :8000 (Michael-only)' }
if ($db -eq 'icb') { throw 'refusing the dev database icb (Michael''s workbench): RT10 writes test rows' }
$env:DATABASE_URL = "postgresql+psycopg://icb_app:icb_app_dev@localhost:5432/$db"
$env:SESSION_SECRET = 'rt10-local-test-not-a-secret'
$env:SMTP_URL = ''
$env:TWILIO_ACCOUNT_SID = ''
$env:TWILIO_AUTH_TOKEN = ''
$env:TWILIO_WHATSAPP_FROM = ''
$env:ANTHROPIC_API_KEY = ''
$env:FEEDBACK_NOTIFY_EMAIL = ''
$env:FEEDBACK_NOTIFY_WHATSAPP = ''
$env:INTEGRATION_API_TOKENS = ''
$env:MES_DEMO_AUTOLOGIN_USER = 'admin'
$env:ALLOWED_ORIGINS = "http://127.0.0.1:$port,http://localhost:$port"
$env:FRONTEND_DIST = if ($env:WT_DIST) { $env:WT_DIST } else { 'C:\Users\micge\Documents\icb-platform\frontend\dist' }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location 'C:\Users\micge\Documents\icb-platform-rt10\backend'
& 'C:\Users\micge\Documents\icb-platform\backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port $port
exit $LASTEXITCODE
