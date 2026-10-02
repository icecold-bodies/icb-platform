"""RT2 window — the page's "All" against the CLI at the same moment (dispatch Part 4, steps 1, 3 and 5). READ ONLY.

    python rt2_all_compare.py <DATABASE_URL> <cli-report-dir> <max-age-minutes>

Reads the newest FINISHED Admin -> Costing audit run with pack 'all' (costing_audit_runs: id, times, status, counts,
golden fingerprint, accepted list and the gzipped report — never started_by / started_by_user_id) and the CLI's
reports for the same four packs (chillers, freezers, icecream, explosive: services/costing_audit_runs.ALL_PACKS —
smoke is a subset of them, so All skips it), and compares them cell by cell on (status, base_status, excel_total,
mes_total to the cent). Prints the per-pack counts (the window's expected-count tables) and PAGE_EQUALS_CLI.
Exit 0 = equal, 1 = they differ, 2 = no usable page run. Writes nothing; the page's report is never written out.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import psycopg

ALL_PACKS = ("chillers", "freezers", "icecream", "explosive")
STATUSES = ("PASS", "ACCEPTED", "SKIP", "UNVERIFIABLE", "EXPIRED", "FLAG", "PRESENCE", "UNMAPPED", "NO_GOLDEN")


def key(c: dict) -> tuple:
    return (c["scenario_id"], c.get("section_excel") or "", c.get("section_mes") or "")


def sig(c: dict) -> tuple:
    r = lambda v: None if v is None else round(float(v), 2)     # noqa: E731
    return (c["status"], c.get("base_status"), r(c.get("excel_total")), r(c.get("mes_total")))


def counts_line(cnt: Counter) -> str:
    return "  ".join(f"{s} {cnt[s]}" for s in STATUSES if cnt.get(s)) + f"  (cells {sum(cnt.values())})"


def main(url: str, cli_dir: str, max_age_min: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        row = cx.execute("""select id, started_at::text, finished_at::text, status, environment, db_name, accepted_list,
                                   golden_fingerprint, count_pass, count_flag, count_accepted, count_expired,
                                   count_unverifiable, report_json_gz,
                                   extract(epoch from (now() - finished_at)) / 60.0
                            from costing_audit_runs
                            where pack = 'all' and finished_at is not null and status in ('passed', 'flagged')
                            order by finished_at desc limit 1""").fetchone()
    if row is None:
        print("PAGE_EQUALS_CLI: no — no finished 'All' run on the page. Click Admin -> Costing audit -> All first.")
        return 2
    (rid, started, finished, status, env, db, acc, gfp, cp, cf, ca, ce, cu, blob, age) = row
    print(f"page run #{rid}: All, {status}, started {started}, finished {finished} ({age:.0f} min ago)")
    print(f"   environment {env} · database {db} · accepted list {acc} · golden {(gfp or '-')[:16]}")
    print(f"   stored counts: PASS {cp}  FLAG {cf}  ACCEPTED {ca}  EXPIRED {ce}  UNVERIFIABLE {cu}")
    if age > float(max_age_min):
        print(f"PAGE_EQUALS_CLI: no — the newest page run finished {age:.0f} min ago (> {max_age_min}): click All again, then re-run")
        return 2
    page = json.loads(gzip.decompress(blob).decode("utf-8"))
    pcells = {key(c): c for c in page["cells"]}

    ccells: dict = {}
    print("\nCLI, per pack (the deployed code's golden, packs and prod list):")
    total = Counter()
    for p in ALL_PACKS:
        f = Path(cli_dir) / f"prod_{p}.json"
        if not f.is_file():
            print(f"PAGE_EQUALS_CLI: no — the CLI report {f.name} is missing")
            return 2
        d = json.loads(f.read_text(encoding="utf-8"))
        cnt = Counter(c["status"] for c in d["cells"])
        total.update(cnt)
        print(f"   {p:<10} {counts_line(cnt)}")
        for c in d["cells"]:
            ccells[key(c)] = c
    print(f"   {'ALL':<10} {counts_line(total)}")
    pcnt = Counter(c["status"] for c in page["cells"])
    print(f"page       {counts_line(pcnt)}")

    only_page = sorted(set(pcells) - set(ccells))
    only_cli = sorted(set(ccells) - set(pcells))
    differ = [k for k in sorted(set(pcells) & set(ccells)) if sig(pcells[k]) != sig(ccells[k])]
    same = len(set(pcells) & set(ccells)) - len(differ)
    print(f"\ncells: page {len(pcells)}, CLI {len(ccells)}, identical {same}, differ {len(differ)}, "
          f"page only {len(only_page)}, CLI only {len(only_cli)}")
    for k in differ[:40]:
        print(f"   DIFF {k[0]} | {k[1] or k[2]}: page {sig(pcells[k])} · CLI {sig(ccells[k])}")
    for k in (only_page + only_cli)[:20]:
        print(f"   ONLY {'page' if k in pcells else 'CLI '} {k[0]} | {k[1] or k[2]}")
    equal = not (differ or only_page or only_cli)
    print(f"PAGE_EQUALS_CLI: {'yes' if equal else 'no'} ({same} of {max(len(pcells), len(ccells))} cells identical)")
    return 0 if equal else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
