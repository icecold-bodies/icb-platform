"""RT10 sims — a stand-in for psycopg, enough for rt10_revisions.py: it answers exactly the three SELECTs the report
sends (and SHOW transaction_read_only) from the fixture rows in $SIMSTATE/fixture.json; anything else raises. The
session is read-only only when the report asked for it (options), as the real server makes it."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Johannesburg")


def _t(v, aware=False):
    if v is None:
        return None
    d = datetime.fromisoformat(v)
    return d.replace(tzinfo=TZ) if aware else d


class _Info:
    timezone = TZ


class _Cursor:
    def __init__(self, conn):
        self.conn, self._rows = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        fx = self.conn.fixture
        calcs = fx["calculations"]
        if sql == "SHOW transaction_read_only":
            self._rows = [("on" if self.conn.read_only else "off",)]
        elif sql.startswith("SELECT count(*), count(*) FILTER (WHERE deleted_at IS NULL)"):
            self._rows = [(len(calcs), sum(1 for c in calcs if not c["deleted_at"]),
                           len({c["quote_number"] for c in calcs if c["quote_number"]}))]
        elif sql.startswith("SELECT c.id, c.quote_number, c.status, c.created_at, c.approved_at, c.deleted_at, "
                            "c.is_repair, c.result_json FROM icb_costings.calculations c WHERE c.quote_number IN"):
            n = {}
            for c in calcs:
                n[c["quote_number"]] = n.get(c["quote_number"], 0) + 1
            sel = sorted((c for c in calcs if c["quote_number"] and n[c["quote_number"]] > 1),
                         key=lambda c: (c["quote_number"], c["id"]))
            self._rows = [(c["id"], c["quote_number"], c["status"], _t(c["created_at"]), _t(c["approved_at"]),
                           _t(c["deleted_at"]), c["is_repair"], json.dumps({"version": c["version"]}
                                                                           if c["version"] is not None else {}))
                          for c in sel]
        elif sql.startswith("SELECT j.id, j.calculation_record_id, j.status, j.accepted_at, j.created_at "
                            "FROM icb_mes.production_jobs j WHERE j.calculation_record_id = ANY(%s)"):
            ids = set(params[0])
            self._rows = [(j["id"], j["calculation_record_id"], j["status"], _t(j["accepted_at"], True),
                           _t(j["created_at"], True)) for j in fx["jobs"] if j["calculation_record_id"] in ids]
        else:
            raise RuntimeError(f"fake psycopg: unexpected SQL: {sql[:120]}")

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, url, options=""):
        if not url.startswith("postgresql://"):
            raise RuntimeError(f"fake psycopg: the URL scheme is not postgresql:// ({url.split(':', 1)[0]})")
        self.read_only = "default_transaction_read_only=on" in (options or "")
        self.info = _Info()
        with open(os.path.join(os.environ["SIMSTATE"], "fixture.json"), encoding="utf-8") as f:
            self.fixture = json.load(f)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cursor(self)

    def rollback(self):
        pass


def connect(url, options=""):
    return _Conn(url, options)
