# reset the scratch mirror icb_prodmirror to a fresh `alembic upgrade head` (RT1's reset: the app schemas dropped)
$env:PGPASSWORD = 'icb_app_dev'
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
& $psql -h localhost -U icb_app -d icb_prodmirror -w -X -q -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS icb_costings CASCADE" -c "DROP SCHEMA IF EXISTS icb_mes CASCADE" -c "DROP SCHEMA IF EXISTS icb_sap CASCADE" -c "CREATE SCHEMA icb_costings AUTHORIZATION icb_app" -c "CREATE SCHEMA icb_mes AUTHORIZATION icb_app"
if ($LASTEXITCODE) { throw "reset failed" }
$env:WT_DB = 'icb_prodmirror'
& pwsh -NoProfile -File (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'wt7.ps1') -m alembic upgrade head *> $null
& $psql -h localhost -U icb_app -d icb_prodmirror -w -XAtc "select 'alembic ' || version_num || ', bom rows ' || (select count(*) from icb_costings.bill_of_materials) || ', factor ' || (select id || '=' || value from icb_costings.admin_settings where key = 'costings.pu_foam_4g_factor') from icb_costings.alembic_version"
