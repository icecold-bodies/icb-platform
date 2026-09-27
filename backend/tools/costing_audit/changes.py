"""What changed between two runs of the same pack (v1.59, "changed since the
previous run" — Michael's fix -> re-run -> compare loop).

A cell is one scenario x section, keyed by (scenario id, section). Between the
previous report and this one a cell can:

    status     change status (e.g. FLAG -> PASS, PASS -> FLAG, ACCEPTED -> EXPIRED)
    moved      keep its status while its rand difference (MES - Excel) moved by more
               than the tolerance: |new - old| > tolerance % of the Excel total
               (floor R1, the same floor the line comparison uses)
    new        exist only in this run   (a scenario or section that appeared)
    vanished   exist only in the previous run

Pure: two report dicts in, a list out. It never re-compares Excel with MES —
the comparison rules stay in compare.py.
"""
from __future__ import annotations

KIND_ORDER = {"status": 0, "moved": 1, "new": 2, "vanished": 3}


def _key(c: dict) -> tuple[str, str]:
    sec = c.get("section_excel")
    if sec is None:
        sec = "MES:" + str(c.get("section_mes")) if c.get("section_mes") is not None else "?"
    return (str(c.get("scenario_id")), str(sec))


def _delta(c: dict) -> float | None:
    if c.get("excel_total") is None and c.get("mes_total") is None:
        return None
    return round(float(c.get("mes_total") or 0.0) - float(c.get("excel_total") or 0.0), 2)


def _label(c: dict) -> dict:
    return {"scenario_id": c.get("scenario_id"), "sheet": str(c.get("sheet") or "").strip(),
            "trailer_name": c.get("trailer_name"), "variant": c.get("variant"),
            "length": c.get("length"), "width": c.get("width"), "height": c.get("height"),
            "section": c.get("section_excel") or c.get("section_mes")}


def changes_between(prev: dict, cur: dict, tolerance_pct: float) -> list[dict]:
    """Every cell that changed from report `prev` to report `cur` (both RunReport.to_dict())."""
    old = {_key(c): c for c in prev.get("cells") or []}
    new = {_key(c): c for c in cur.get("cells") or []}
    out: list[dict] = []
    for k, c in new.items():
        o = old.get(k)
        if o is None:
            out.append({"kind": "new", **_label(c), "old_status": None, "new_status": c.get("status"),
                        "old_delta": None, "new_delta": _delta(c)})
            continue
        do, dn = _delta(o), _delta(c)
        if o.get("status") != c.get("status"):
            out.append({"kind": "status", **_label(c), "old_status": o.get("status"), "new_status": c.get("status"),
                        "old_delta": do, "new_delta": dn})
            continue
        if do is None and dn is None:
            continue
        band = max(abs(float(c.get("excel_total") or o.get("excel_total") or 0.0)), 1.0) * tolerance_pct / 100.0
        if abs((dn or 0.0) - (do or 0.0)) > band:
            out.append({"kind": "moved", **_label(c), "old_status": o.get("status"), "new_status": c.get("status"),
                        "old_delta": do, "new_delta": dn})
    for k, o in old.items():
        if k not in new:
            out.append({"kind": "vanished", **_label(o), "old_status": o.get("status"), "new_status": None,
                        "old_delta": _delta(o), "new_delta": None})
    out.sort(key=lambda x: (KIND_ORDER[x["kind"]], x["sheet"], str(x["section"]), str(x["variant"]),
                            x["length"] or 0, x["width"] or 0, x["height"] or 0))
    return out
