"""RT10 (RT10_RULING_1 Q3 ii) — revisions on prod. READ ONLY; allow-listed reads only (G4).

On today's Costings list, Accept, Decline, the job creation and the row actions of a NEWER revision reach the OLDEST
row with that quote number (CostingsContext's quote → id map). This report says whether that has already happened
on prod, and lists prod's revisions, so the BA knows before any release:

  * every quote number with two or more rows: each row's id, version (and its REV = version − 1), status, created
    and accepted times as stored, deleted yes / no, and the production job built from it (job id, created time);
  * live duplicate versions: two or more LIVE rows of one quote number with the same version;
  * accepted while a newer live revision existed: a row accepted at a time when a later revision of the same quote
    (higher version; a tie goes to the newer created time, then the higher id — the Latest rule) was live;
  * production jobs built from a revision that was not the latest live one when the job was created.

Reads ONLY the columns named below (never a customer, contact, user, rep or description) and, from result_json, ONLY
the "version" key. Prints quote numbers, ids, versions, statuses and times. Prod's own venv python runs it (psycopg);
the database URL arrives in RT10_DB_URL (never printed) and every session is read-only, asserted here.

Usage (rt10_check.sh sets everything): python -I rt10_revisions.py
"""
from __future__ import annotations

import json
import os
import re
import sys

# ── the allow-lists: everything this script reads, and nothing else ──────────
CALC_COLUMNS = ("id", "quote_number", "status", "created_at", "approved_at", "deleted_at", "is_repair",
                "result_json")                                   # icb_costings.calculations
RESULT_KEYS = ("version",)                                       # result_json: this key only
JOB_COLUMNS = ("id", "calculation_record_id", "status", "accepted_at", "created_at")   # icb_mes.production_jobs

#: A column or key that would carry a person is refused at import, whatever list it is on.
_PERSONAL = re.compile(r"customer|contact|user|email|phone|tel|address|rep\b|sales|name|description|notes|vehicle|"
                       r"registration|delivery|payment|_by$|attestation|reason", re.I)


def assert_allowlist_clean(*lists: tuple) -> None:
    """Refuse an allow-list that names anything personal-looking (G4). Runs at import and in its own test."""
    for lst in lists:
        for k in lst:
            if _PERSONAL.search(str(k)):
                raise RuntimeError(f"allow-list carries a personal-looking column or key: {k!r}")


assert_allowlist_clean(CALC_COLUMNS, RESULT_KEYS, JOB_COLUMNS)

SQL_COUNTS = ("SELECT count(*), count(*) FILTER (WHERE deleted_at IS NULL), count(DISTINCT quote_number) "
              "FROM icb_costings.calculations")
SQL_CALCS = ("SELECT " + ", ".join(f"c.{col}" for col in CALC_COLUMNS) + " FROM icb_costings.calculations c "
             "WHERE c.quote_number IN (SELECT quote_number FROM icb_costings.calculations "
             "WHERE quote_number IS NOT NULL GROUP BY quote_number HAVING count(*) > 1) "
             "ORDER BY c.quote_number, c.id")
SQL_JOBS = ("SELECT " + ", ".join(f"j.{col}" for col in JOB_COLUMNS) + " FROM icb_mes.production_jobs j "
            "WHERE j.calculation_record_id = ANY(%s) ORDER BY j.id")


def version_of(result_json) -> "int | None":
    """The stored "version" (result_json, nothing else of it); a row without one is version 1, as the API reads it;
    None when the saved copy cannot be read."""
    try:
        data = json.loads(result_json) if result_json else {}
    except Exception:
        return None
    data = {k: data[k] for k in RESULT_KEYS if isinstance(data, dict) and k in data}
    try:
        return int(data.get("version", 1) or 1)
    except (TypeError, ValueError):
        return None


def _key(r: dict):
    """The Latest rule's order: the higher version, then the newer created time, then the higher id."""
    return (r["version"] if r["version"] is not None else 1, r["created_at"] or 0, r["id"])


def _live_at(r: dict, t) -> bool:
    """Was this row there, and not deleted, at time t?"""
    return (r["created_at"] is not None and r["created_at"] <= t) and (r["deleted_at"] is None or r["deleted_at"] > t)


def analyse(rows: list, jobs: list) -> dict:
    """The report's findings from the allow-listed rows (dicts keyed by CALC_COLUMNS with `version` in place of
    result_json) and jobs (dicts keyed by JOB_COLUMNS). Pure: no database, no output."""
    by_quote: dict = {}
    for r in rows:
        by_quote.setdefault(r["quote_number"], []).append(r)
    job_by_calc = {j["calculation_record_id"]: j for j in jobs}
    quotes, dup_live, older_accepted, older_jobs = [], [], [], []
    for qn in sorted(by_quote):
        chain = sorted(by_quote[qn], key=_key)
        quotes.append({"quote_number": qn, "rows": chain,
                       "jobs": [job_by_calc[r["id"]] for r in chain if r["id"] in job_by_calc]})
        live = [r for r in chain if r["deleted_at"] is None]
        seen: dict = {}
        for r in live:
            seen.setdefault(r["version"], []).append(r["id"])
        for v, ids in sorted(seen.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
            if len(ids) > 1:
                dup_live.append({"quote_number": qn, "version": v, "ids": ids})

        def newer_live_at(r, t):
            return [o for o in chain if o["id"] != r["id"] and _key(o) > _key(r) and _live_at(o, t)]

        for r in chain:
            if r["approved_at"] is not None:
                newer = newer_live_at(r, r["approved_at"])
                if newer:
                    older_accepted.append({"quote_number": qn, "row": r, "newer": max(newer, key=_key)})
            j = job_by_calc.get(r["id"])
            if j is not None and j["created_at"] is not None:
                newer = newer_live_at(r, j["created_at"])
                if newer:
                    older_jobs.append({"quote_number": qn, "row": r, "job": j, "newer": max(newer, key=_key)})
    return {"quotes": quotes, "dup_live": dup_live, "older_accepted": older_accepted, "older_jobs": older_jobs}


def _t(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v is not None else "-"


def _v(r: dict) -> str:
    v = r["version"]
    return f"v{v} REV {v - 1}" if v is not None else "v? REV ?"


def render(counts: tuple, found: dict) -> list:
    """The report as lines: quote numbers, ids, versions, statuses and times only."""
    total, live, distinct = counts
    out = [f"costings: {total} rows ({live} live), {distinct} quote numbers",
           f"quote numbers with 2 or more rows: {len(found['quotes'])}"]
    for q in found["quotes"]:
        out.append(f"  {q['quote_number']}")
        jobs = {j["calculation_record_id"]: j for j in q["jobs"]}
        for r in q["rows"]:
            j = jobs.get(r["id"])
            job = f"job {j['id']} built from this row, created {_t(j['created_at'])}" if j else "no job"
            out.append(f"    id {r['id']:<6} {_v(r):<12} {r['status'] or '-':<18} created {_t(r['created_at'])}"
                       f"  accepted {_t(r['approved_at']):<19}  {'DELETED' if r['deleted_at'] is not None else 'live':<7}"
                       f"  {'repair' if r['is_repair'] else 'body':<6}  {job}")
    out.append(f"live duplicate version numbers: {len(found['dup_live'])}")
    for d in found["dup_live"]:
        out.append(f"  {d['quote_number']}  version {d['version']} on {len(d['ids'])} live rows (ids {', '.join(map(str, d['ids']))})")
    out.append(f"accepted while a newer live revision existed: {len(found['older_accepted'])}")
    for a in found["older_accepted"]:
        r, n = a["row"], a["newer"]
        out.append(f"  {a['quote_number']}  id {r['id']} {_v(r)} accepted {_t(r['approved_at'])}; id {n['id']} {_v(n)}"
                   f" (created {_t(n['created_at'])}) was live then")
    out.append(f"production jobs built from a revision that was not the latest live one when the job was created: "
               f"{len(found['older_jobs'])}")
    for a in found["older_jobs"]:
        r, n, j = a["row"], a["newer"], a["job"]
        out.append(f"  {a['quote_number']}  job {j['id']} (created {_t(j['created_at'])}) from id {r['id']} {_v(r)};"
                   f" id {n['id']} {_v(n)} (created {_t(n['created_at'])}) was live then")
    out.append(f"SUMMARY: {total} costings; {len(found['quotes'])} quote numbers with 2+ rows; "
               f"{len(found['dup_live'])} live duplicate versions; {len(found['older_accepted'])} accepted while a newer "
               f"live revision existed; {len(found['older_jobs'])} jobs built from an older revision")
    return out


def naive(v, tz):
    """One clock for every comparison. The costings' times are `timestamp` (naive: the app's aware UTC value was
    turned into the session zone's wall time on write); the jobs' are `timestamptz` (aware). An aware value is put
    into the session's zone and its offset dropped, so both read as that zone's wall time — the times as stored."""
    if v is not None and getattr(v, "tzinfo", None) is not None:
        return v.astimezone(tz).replace(tzinfo=None) if tz is not None else v.replace(tzinfo=None)
    return v


def read(conn) -> tuple:
    """The three allow-listed SELECTs, in one read-only transaction. Returns (counts, rows, jobs)."""
    tz = getattr(conn.info, "timezone", None)
    with conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        mode = cur.fetchone()[0]
        if mode != "on":
            raise RuntimeError(f"the session is not read-only ({mode}): refusing to read")
        cur.execute(SQL_COUNTS)
        counts = tuple(cur.fetchone())
        cur.execute(SQL_CALCS)
        rows = []
        for rec in cur.fetchall():
            r = dict(zip(CALC_COLUMNS, rec))
            r["version"] = version_of(r.pop("result_json"))
            for k in ("created_at", "approved_at", "deleted_at"):
                r[k] = naive(r[k], tz)
            rows.append(r)
        cur.execute(SQL_JOBS, ([r["id"] for r in rows],))
        jobs = []
        for rec in cur.fetchall():
            j = dict(zip(JOB_COLUMNS, rec))
            for k in ("accepted_at", "created_at"):
                j[k] = naive(j[k], tz)
            jobs.append(j)
    return counts, rows, jobs


def main() -> int:
    import psycopg
    url = os.environ.get("RT10_DB_URL", "").replace("postgresql+psycopg:", "postgresql:", 1)
    if not url:
        print("RT10_DB_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        counts, rows, jobs = read(conn)
        conn.rollback()
    for line in render(counts, analyse(rows, jobs)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
