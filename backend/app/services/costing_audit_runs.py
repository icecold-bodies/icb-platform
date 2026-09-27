"""Admin -> Costing audit: run the Excel <-> MES costing audit on demand, in the server
(v1.59, BA dispatch 27 Sep). On prod it audits prod.

The run is the CLI's run (tools/costing_audit: golden -> MES probe -> compare ->
report), called through runner.cost_and_compare — one code path, never a fork.

Guarantees (BA ratified defaults 2, 3):

  * READ-ONLY against pricing data. The probe costs every scenario on its own
    connection opened with default_transaction_read_only=on, inside a transaction
    that also starts with SET TRANSACTION READ ONLY and is always rolled back — a
    write attempted there raises. The run record is the only thing written, in its
    own short sessions.
  * Never on the request thread. start_run() returns a run id at once; the run
    executes on a background daemon thread; the page polls the run record.
  * One run at a time across every worker: a Postgres SESSION advisory lock
    (pg_try_advisory_lock) on a dedicated connection held for the whole run. If the
    worker dies the connection dies and Postgres releases the lock — there is no
    lock row to go stale. A 'running' record left behind by a dead worker is marked
    failed by the next run that takes the lock.
  * Hard timeout TIMEOUT_S: checked before every scenario (and statement_timeout on
    the probe connection); the run is then marked failed with the reason.
"""
from __future__ import annotations

import gzip
import json
import logging
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from .. import database as _db
from ..database import CostingAuditRun

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]

PACKS = ("smoke", "chillers", "freezers", "icecream", "explosive")
ALL = "all"
# smoke's 18 scenarios are a subset of chillers + freezers + icecream, so "All" skips it
ALL_PACKS = ("chillers", "freezers", "icecream", "explosive")
PACK_CHOICES = PACKS + (ALL,)

# Arbitrary but fixed; identical in every worker of every process on this database.
LOCK_KEY = 852_144_059
TIMEOUT_S = 300
STATEMENT_TIMEOUT_MS = 60_000
STALE_GRACE_S = 180            # a 'running' record this far past the timeout is shown as failed
PROGRESS_EVERY_S = 0.5

PROD_DB_NAMES = frozenset({"icb_platform"})
STATUSES = ("running", "passed", "flagged", "failed")
FLAG_STATUSES = ("FLAG", "PRESENCE", "UNMAPPED", "NO_GOLDEN")     # count_flag: unaccepted differences


class UnknownPack(ValueError):
    pass


class AlreadyRunning(RuntimeError):
    pass


class RunTimeout(RuntimeError):
    pass


# ── environment ─────────────────────────────────────────────────────────

def environment_for(db_name: str | None) -> str:
    """'prod' for the production database (icb_platform), 'dev' for anything else."""
    return "prod" if (db_name or "") in PROD_DB_NAMES else "dev"


def current_db_name() -> str:
    return _db.engine.url.database or ""


def environment_label(env: str, db_name: str) -> str:
    if env == "prod":
        return f"Production — the live database ({db_name}). This audits the prices quotes are made from."
    return f"Development — database {db_name}, not the live prices."


def _tools() -> SimpleNamespace:
    """Every tools.costing_audit module the RUN path needs, imported on demand (so a
    server without the audit's dependencies still boots; the page then says why).
    None of them imports openpyxl or LibreOffice — test_costing_audit_admin proves it."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from tools.costing_audit import ACCEPTED_FILE, GOLDEN_DIR, PACKS_DIR
    from tools.costing_audit.accepted import load_accepted
    from tools.costing_audit.changes import changes_between
    from tools.costing_audit.mes_probe import MesProbe
    from tools.costing_audit.report import render_csv_doc, render_html_doc
    from tools.costing_audit.runner import cost_and_compare, golden_for, merge_reports
    from tools.costing_audit.scenarios import load_pack
    return SimpleNamespace(**locals())


def accepted_file_for(env: str) -> Path:
    t = _tools()
    return t.ACCEPTED_FILE.with_name("accepted_differences.prod.yaml") if env == "prod" else t.ACCEPTED_FILE


def _packs_of(pack: str) -> tuple[str, ...]:
    if pack == ALL:
        return ALL_PACKS
    if pack in PACKS:
        return (pack,)
    raise UnknownPack(f"unknown pack {pack!r} — expected one of: {', '.join(PACK_CHOICES)}")


def _manifest(pack_name: str) -> dict:
    """The golden manifest only (the sheet files are MBs; the header needs none of them)."""
    p = _tools().GOLDEN_DIR / pack_name / "_manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _golden_header(pack: str) -> dict:
    t = _tools()
    ms = [_manifest(p) for p in _packs_of(pack)]
    fps = {((m.get("workbook") or {}).get("files") or {}).get("GRP Costings 2018.xlsx") for m in ms}
    dates = [str(m["generated_at"]) for m in ms if m.get("generated_at")]
    tol = t.load_pack(t.PACKS_DIR / f"{_packs_of(pack)[0]}.yaml").tolerance_pct
    return {"golden_fingerprint": fps.pop() if len(fps) == 1 else None,
            "golden_generated_at": max(dates) if dates else None,
            "tolerance_pct": tol,
            "scenarios": sum(int(m.get("scenario_count") or 0) for m in ms)}


def overview() -> dict:
    """What the page header shows before (and around) any run."""
    db_name = current_db_name()
    env = environment_for(db_name)
    out = {"environment": env, "environment_label": environment_label(env, db_name), "db_name": db_name,
           "timeout_min": TIMEOUT_S // 60, "packs": [], "tool_error": None}
    try:
        t = _tools()
        acc = accepted_file_for(env)
        out["accepted_list"] = acc.name
        out["accepted_entries"] = len(t.load_accepted(acc))
        for p in PACK_CHOICES:
            h = _golden_header(p)
            out["packs"].append({"name": p, **h,
                                 "golden_fingerprint_short": (h["golden_fingerprint"] or "")[:12] or None})
    except Exception as exc:                       # e.g. PyYAML missing from the venv
        logger.exception("costing audit tool unavailable")
        out["tool_error"] = f"{type(exc).__name__}: {exc}"
    return out


# ── connections ─────────────────────────────────────────────────────────

_engines: dict[str, object] = {}
_engines_lock = threading.Lock()


def _engine(kind: str):
    """A NullPool engine on the app's CURRENT database (switch_db-safe): 'probe' opens
    read-only connections, 'lock' plain autocommit ones. NullPool: close() really
    closes, so a probe connection never returns to a pool and a lock never lingers."""
    url = _db.engine.url
    key = f"{kind}:{url.render_as_string(hide_password=False)}"
    with _engines_lock:
        eng = _engines.get(key)
        if eng is None:
            if kind == "probe":
                eng = create_engine(url, poolclass=NullPool, connect_args={
                    "connect_timeout": 10,
                    "options": f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"})
            else:
                eng = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT",
                                    connect_args={"connect_timeout": 10})
            event.listen(eng, "connect", _db._set_search_path)
            _engines[key] = eng
    return eng


@contextmanager
def _open_probe_session():
    """The session the probe reads pricing data through. Read-only twice over (the
    connection's default and the transaction's own mode) and ALWAYS rolled back."""
    conn = _engine("probe").connect()
    s = Session(bind=conn, autoflush=False)
    try:
        s.execute(text("SET TRANSACTION READ ONLY"))
        yield s
    finally:
        try:
            s.rollback()
        finally:
            s.close()
            conn.close()


# Test seams: tests bind these to one connection inside a transaction they roll back.
probe_session_factory = _open_probe_session


def record_session() -> Session:
    return _db.SessionLocal()


def _try_lock():
    """The run lock's connection, or None if another run holds it."""
    conn = _engine("lock").connect()
    try:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
    except Exception:
        conn.close()
        raise
    if not got:
        conn.close()
        return None
    return conn


def _release(conn) -> None:
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
    except Exception:
        logger.exception("costing audit: unlock failed (closing the connection releases it)")
    finally:
        conn.close()


# ── starting a run ──────────────────────────────────────────────────────

def _local_hhmm(dt: datetime | None) -> str:
    return dt.astimezone().strftime("%H:%M") if dt else "?"


def _running_message(s: Session) -> str:
    r = (s.query(CostingAuditRun).filter(CostingAuditRun.status == "running")
         .order_by(CostingAuditRun.started_at.desc()).first())
    if r is None:
        return "An audit is already running (it started a moment ago) — wait for it to finish, then run again."
    return f"An audit is already running — started by {r.started_by} at {_local_hhmm(r.started_at)}."


def _submit(fn, *args):
    """The background executor: one daemon thread per run (the lock already allows only
    one run at a time). Daemon, so a service restart never waits on an audit — a run cut
    off that way leaves its connections to die with the process, Postgres releases the
    lock, and the next run marks the orphaned 'running' record failed."""
    th = threading.Thread(target=fn, args=args, name=f"costing-audit-run-{args[0]}", daemon=True)
    th.start()
    return th


def start_run(pack: str, user, *, submit=None) -> int:
    """Record a new run and start it in the background. Returns the run id at once.
    Raises UnknownPack, or AlreadyRunning while any run holds the lock."""
    _packs_of(pack)
    lock = _try_lock()
    if lock is None:
        s = record_session()
        try:
            raise AlreadyRunning(_running_message(s))
        finally:
            s.close()
    try:
        db_name = current_db_name()
        env = environment_for(db_name)
        header = _golden_header(pack)
        s = record_session()
        try:
            # We hold the lock, so nothing is running: a 'running' record is a dead worker's.
            s.query(CostingAuditRun).filter(CostingAuditRun.status == "running").update(
                {"status": "failed", "finished_at": datetime.now(timezone.utc),
                 "error": "interrupted — the server stopped before this run finished"},
                synchronize_session=False)
            gdate = header["golden_generated_at"]
            run = CostingAuditRun(
                started_at=datetime.now(timezone.utc),
                started_by_user_id=getattr(user, "id", None),
                started_by=str(getattr(user, "username", None) or "?")[:100],
                pack=pack, environment=env, db_name=db_name,
                accepted_list=accepted_file_for(env).name,
                golden_fingerprint=header["golden_fingerprint"],
                golden_generated_at=datetime.fromisoformat(gdate) if gdate else None,
                tolerance_pct=header["tolerance_pct"],
                status="running", progress_done=0, progress_total=header["scenarios"])
            s.add(run)
            s.commit()
            run_id = run.id
        finally:
            s.close()
    except Exception:
        _release(lock)
        raise
    try:
        (submit or _submit)(_execute, run_id, pack, lock)
    except Exception:
        _release(lock)
        _fail(run_id, "could not start the background run")
        raise
    return run_id


# ── the run itself (background thread) ──────────────────────────────────

def _update(run_id: int, **fields) -> None:
    s = record_session()
    try:
        s.query(CostingAuditRun).filter(CostingAuditRun.id == run_id).update(fields, synchronize_session=False)
        s.commit()
    finally:
        s.close()


def _fail(run_id: int, reason: str) -> None:
    try:
        _update(run_id, status="failed", finished_at=datetime.now(timezone.utc), error=reason[:4000])
    except Exception:
        logger.exception("costing audit: could not record the failure of run %s", run_id)


def counts_of(counts: dict) -> dict:
    return {"count_pass": counts.get("PASS", 0),
            "count_flag": sum(counts.get(k, 0) for k in FLAG_STATUSES),
            "count_accepted": counts.get("ACCEPTED", 0),
            "count_expired": counts.get("EXPIRED", 0),
            "count_unverifiable": counts.get("UNVERIFIABLE", 0)}


def encode_report(d: dict) -> bytes:
    return gzip.compress(json.dumps(d, default=str, separators=(",", ":")).encode("utf-8"), 6)


def decode_report(blob: bytes) -> dict:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


def fresh_lookups() -> None:
    """Drop this worker's cached calculator lookups (sections, formulas, globals — a 30 s
    TTL each) so the run audits the data as it is NOW: an admin who fixes a section on
    one worker and re-runs on another must not be audited against the old value. The
    next /api/calculate on this worker simply reloads them."""
    from . import invalidate_formulas, invalidate_global_vars, invalidate_sections
    invalidate_sections()
    invalidate_formulas()
    invalidate_global_vars()


def _execute(run_id: int, pack: str, lock, *, timeout_s: float | None = None) -> None:
    deadline = time.monotonic() + (TIMEOUT_S if timeout_s is None else timeout_s)
    limit = TIMEOUT_S if timeout_s is None else timeout_s

    said = f"{limit / 60:g} minutes" if limit >= 60 else f"{limit:g} seconds"

    def check():
        if time.monotonic() > deadline:
            raise RunTimeout(f"timed out after {said} — the run was stopped")

    try:
        t = _tools()
        db_name = current_db_name()
        env = environment_for(db_name)
        acc_path = accepted_file_for(env)
        accepted = t.load_accepted(acc_path)
        prepared = []
        for name in _packs_of(pack):
            p = t.load_pack(t.PACKS_DIR / f"{name}.yaml")
            manifest, goldens, warnings = t.golden_for(p)
            prepared.append((p, manifest, goldens, warnings))
        total = sum(len(g) for _, _, g, _ in prepared)
        _update(run_id, progress_total=total)
        fresh_lookups()
        mes_source = f"in-process {_db.engine.url.host or 'localhost'}/{db_name} (read-only)"
        state = {"done": 0, "base": 0, "last": 0.0}

        def progress(done_in_pack: int, _total_in_pack: int):
            state["done"] = state["base"] + done_in_pack
            now = time.monotonic()
            if now - state["last"] >= PROGRESS_EVERY_S or state["done"] == total:
                state["last"] = now
                _update(run_id, progress_done=state["done"])

        reports = []
        with probe_session_factory() as ps:
            probe = t.MesProbe(session=ps, log=lambda *_: None)
            for p, manifest, goldens, warnings in prepared:
                reports.append(t.cost_and_compare(
                    p.name, manifest, goldens, probe=probe, accepted=accepted, tolerance_pct=p.tolerance_pct,
                    mes_source=mes_source, warnings=warnings, on_progress=progress, check=check))
                state["base"] += len(goldens)
        rep = reports[0] if len(reports) == 1 else t.merge_reports(reports, pack_name=ALL)
        rep.warnings.append(f"accepted list: {acc_path.name} (environment {env}, database {db_name})")
        d = rep.to_dict()
        _update(run_id, status="flagged" if rep.exit_code else "passed", finished_at=datetime.now(timezone.utc),
                progress_done=total, report_json_gz=encode_report(d), **counts_of(d["counts"]))
    except RunTimeout as exc:
        _fail(run_id, str(exc))
    except Exception as exc:
        logger.exception("costing audit run %s failed", run_id)
        _fail(run_id, f"{type(exc).__name__}: {exc}")
    finally:
        _release(lock)


# ── reading runs ────────────────────────────────────────────────────────

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def summary(r: CostingAuditRun, now: datetime | None = None, *, report_bytes: int | None = -1) -> dict:
    now = now or datetime.now(timezone.utc)
    if report_bytes == -1:
        report_bytes = len(r.report_json_gz) if r.report_json_gz else None
    status, error = r.status, r.error
    if status == "running" and r.started_at and now - r.started_at > timedelta(seconds=TIMEOUT_S + STALE_GRACE_S):
        status, error = "failed", "no longer running — the server stopped before this run finished"
    end = r.finished_at or now
    return {"id": r.id, "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
            "elapsed_s": round((end - r.started_at).total_seconds(), 1) if r.started_at else None,
            "started_by": r.started_by, "pack": r.pack, "environment": r.environment, "db_name": r.db_name,
            "accepted_list": r.accepted_list, "golden_fingerprint": r.golden_fingerprint,
            "golden_generated_at": _iso(r.golden_generated_at), "tolerance_pct": r.tolerance_pct,
            "status": status, "progress_done": r.progress_done, "progress_total": r.progress_total,
            "counts": {"pass": r.count_pass, "flag": r.count_flag, "accepted": r.count_accepted,
                       "expired": r.count_expired, "unverifiable": r.count_unverifiable},
            "error": error, "report_bytes": report_bytes}


def list_runs(s: Session, limit: int = 50) -> list[dict]:
    """Newest first. The report blobs are never loaded here — only their size."""
    from sqlalchemy import func
    from sqlalchemy.orm import defer
    rows = (s.query(CostingAuditRun, func.octet_length(CostingAuditRun.report_json_gz))
            .options(defer(CostingAuditRun.report_json_gz))
            .order_by(CostingAuditRun.started_at.desc(), CostingAuditRun.id.desc()).limit(limit).all())
    return [summary(r, report_bytes=n) for r, n in rows]


def get_run(s: Session, run_id: int) -> CostingAuditRun | None:
    return s.get(CostingAuditRun, run_id)


def report_of(r: CostingAuditRun) -> dict | None:
    return decode_report(r.report_json_gz) if r.report_json_gz else None


def previous_run(s: Session, r: CostingAuditRun) -> CostingAuditRun | None:
    """The run before `r` of the same pack in the same environment that produced a report."""
    return (s.query(CostingAuditRun)
            .filter(CostingAuditRun.pack == r.pack, CostingAuditRun.environment == r.environment,
                    CostingAuditRun.status.in_(("passed", "flagged")), CostingAuditRun.id != r.id,
                    CostingAuditRun.started_at < r.started_at)
            .order_by(CostingAuditRun.started_at.desc(), CostingAuditRun.id.desc()).first())


def changes_since_previous(s: Session, r: CostingAuditRun) -> dict:
    cur = report_of(r)
    if cur is None:
        return {"previous": None, "changes": [], "counts": {}}
    prev_run = previous_run(s, r)
    if prev_run is None:
        return {"previous": None, "changes": [], "counts": {}}
    changes = _tools().changes_between(report_of(prev_run), cur, r.tolerance_pct)
    counts: dict[str, int] = {}
    for c in changes:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    return {"previous": {"id": prev_run.id, "started_at": _iso(prev_run.started_at),
                         "started_by": prev_run.started_by, "status": prev_run.status},
            "changes": changes, "counts": counts}


def render_html(r: CostingAuditRun) -> str:
    return _tools().render_html_doc(report_of(r))


def render_csv(r: CostingAuditRun) -> str:
    return _tools().render_csv_doc(report_of(r))
