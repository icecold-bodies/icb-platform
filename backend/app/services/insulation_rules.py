"""RT6 — Burt's insulation rules: the ONE pure check every path uses (G1).

    classify_body(rows)                    -> Classification   which choice on this body is which panel x insulation
    selections(cls, payload)               -> set of Selected  what a quote's payload selects, by mechanism
    breaches(rule, cls, payload)           -> list of Breach   the selected insulations the family's rule forbids

PURE: plain values in, plain values out — no database, no ORM, no app import. The routers adapt their BOM rows
(`row_view`) and call it; the audit probe never does (it prices Burt's sheets, whatever they hold), so the check
lives beside `_build_bom_items`, never inside it. The prod discovery kit stages this file unchanged and feeds it
rows read over psycopg, so the classification it reports is exactly the one the guards use.

THE RULE is data on the family (trailer_groups): which insulation is ALLOWED on which panel. None = no rule (every
family but the two Burt ruled on), and nothing is enforced.

HOW A QUOTE SELECTS AN INSULATION (by mechanism — what `_build_bom_items` actually reads):
  1. `body_option_selections[<master id>] = true` — the master row (is_body_option, group = the panel, a name
     naming EPS or PU) is ticked. This is every renderer's own control.
  2. `flag_overrides[<name>] = true` — a Settings-draft flag's alias. `_build_bom_items` adds every true alias to
     the names its `bom_conditions` test, so an alias equal to an insulation master's name (or to a name an
     insulation cost line's condition tests) prices that insulation with no master ticked.
  3. `include_all_items` (Calculator 2, and the legacy replay of a snapshot-less costing): masters are dropped and
     every cost line prices unless the user excluded it, so an included insulation COST LINE is the selection.
A saved THICKNESS with nothing selected (N9937/07/2026) selects nothing: it is not a breach.

CLASSIFYING (masters by mechanism, never by id or a hard-coded list): a candidate is a body-option master that is
in an INSULATION choice group or whose name names EPS or PU. It is classified as (panel, insulation) when its group
is a panel, its name names exactly one insulation and no other panel, and every insulation cost line it gates (its
include conditions, by option id or by name, and the legacy `body_option_linked`) is that insulation. Anything else
is UNCLASSIFIED and reported (an admin warning), never silently passed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PANELS = ("FRONT", "SIDES", "ROOF", "FLOOR", "DRD", "SRD")
INSULATIONS = ("EPS", "PU")
# The cost lines that ARE the insulation: EPS, and services/insulation_foam.PU_FOAM_MATERIAL_NAMES (kept equal by a
# test; this module imports nothing from the app).
_LINE_MATERIAL = {"EPS": "EPS", "PU": "PU", "PU FOAM": "PU"}
_TOKEN = {ins: re.compile(rf"(?<![A-Z0-9]){ins}(?![A-Z0-9])") for ins in INSULATIONS}
_PANEL_WORD = {p: re.compile(rf"(?<![A-Z0-9]){p}(?![A-Z0-9])") for p in PANELS}


def _u(s) -> str:
    return " ".join(str(s or "").upper().split())


def _conditions(raw) -> tuple[str, list[dict]]:
    """(mode, items) of a row's bom_conditions, as `_eval_bom_conditions` reads them."""
    if not raw:
        return "include", []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return "include", []
    if isinstance(parsed, list):
        return "include", [c for c in parsed if isinstance(c, dict)]
    if isinstance(parsed, dict):
        mode = str(parsed.get("mode") or "include").lower()
        return mode, [c for c in (parsed.get("all") or []) if isinstance(c, dict)]
    return "include", []


@dataclass(frozen=True)
class Master:
    id: int
    name: str
    group: str
    panel: str | None
    insulation: str | None
    how: str                                  # how it was classified, or why it could not be


@dataclass
class Classification:
    masters: list[Master] = field(default_factory=list)              # every candidate, classified or not
    by_master_id: dict[int, tuple[str, str]] = field(default_factory=dict)
    by_name: dict[str, tuple[str, str]] = field(default_factory=dict)  # exact names, as the engine compares them
    lines: dict[int, tuple[str, str, str]] = field(default_factory=dict)  # cost line id -> (panel, ins, section)
    unclassified: list[dict] = field(default_factory=list)            # {id, name, reason} — reported, never passed


@dataclass(frozen=True)
class Breach:
    panel: str
    insulation: str
    via: str              # 'selection' (a ticked master), 'flag' (a draft-flag alias) or 'line' (include_all_items)
    ref: str              # the master id, the alias or the line id that selects it

    def as_dict(self) -> dict:
        return {"panel": self.panel, "insulation": self.insulation, "via": self.via, "ref": self.ref,
                "message": message(self.panel, self.insulation)}


def message(panel: str, insulation: str) -> str:
    """The plain-English reason, one panel at a time."""
    where = {"DRD": "the double rear doors", "SRD": "the single rear door"}.get(panel, f"the {panel}")
    return f"{insulation} insulation is not allowed on {where} for this body's family."


def row_view(row) -> dict:
    """The fields the classifier reads, from an ORM BillOfMaterial (or a dict that already has them)."""
    if isinstance(row, dict):
        return row
    mat = getattr(row, "material", None)
    return {
        "id": row.id, "is_body_option": bool(row.is_body_option),
        "body_option_group": row.body_option_group, "body_option_subgroup": row.body_option_subgroup,
        "selection_group": getattr(row, "selection_group", None),
        "material_name": getattr(mat, "name", None) if mat is not None else None,
        "bom_section": row.bom_section, "bom_conditions": row.bom_conditions,
        "body_option_linked": row.body_option_linked,
    }


def classify_body(rows) -> Classification:
    rows = [row_view(r) for r in rows]
    cls = Classification()
    masters = [r for r in rows if r.get("is_body_option")]
    costs = [r for r in rows if not r.get("is_body_option")]
    # the insulation cost lines each master gates: include-mode 'Y' conditions naming it (by id or name), and the
    # legacy body_option_linked (still read by the engine on non-v2 bodies)
    gated: dict[int, list[dict]] = {}
    linked_only: dict[int, int] = {}      # lines tied to the master only by the legacy link (v2 ignores it)
    for m in masters:
        name = m.get("material_name") or ""
        hits, legacy = [], 0
        for c in costs:
            ins = _LINE_MATERIAL.get(_u(c.get("material_name")))
            if not ins:
                continue
            mode, items = _conditions(c.get("bom_conditions"))
            named = mode == "include" and any(
                (str(i.get("option") or "") == name or str(i.get("option_id") or "") == str(m["id"]))
                and str(i.get("equals") or "Y").upper() == "Y" for i in items)
            if named:
                hits.append(c)
            elif (c.get("body_option_linked") or "") == name:
                hits.append(c)
                legacy += 1
        gated[m["id"]] = hits
        linked_only[m["id"]] = legacy

    for m in masters:
        name, grp = m.get("material_name") or "", _u(m.get("body_option_group"))
        nu = _u(name)
        toks = [i for i in INSULATIONS if _TOKEN[i].search(nu)]
        in_ins_group = "INSULATION" in (_u(m.get("body_option_subgroup")), _u(m.get("selection_group")))
        if not toks and not in_ins_group:
            continue                                      # not an insulation choice at all
        why = []
        if len(toks) != 1:
            why.append("its name names no insulation" if not toks else "its name names both EPS and PU")
        if grp not in PANELS:
            why.append(f"its group {grp or '(none)'} is not a panel")
        others = [p for p in PANELS if p != grp and _PANEL_WORD[p].search(nu)]
        if others:
            why.append(f"its name names another panel ({', '.join(others)})")
        mats = sorted({_LINE_MATERIAL[_u(c.get('material_name'))] for c in gated[m["id"]]})
        if toks and len(toks) == 1 and any(x != toks[0] for x in mats):
            why.append(f"it gates a {'/'.join(x for x in mats if x != toks[0])} cost line")
        if why:
            cls.masters.append(Master(m["id"], name, grp, None, None, "; ".join(why)))
            cls.unclassified.append({"id": m["id"], "name": name, "reason": "; ".join(why)})
            continue
        panel, ins = grp, toks[0]
        n, legacy = len(gated[m["id"]]), linked_only[m["id"]]
        how = f"group {grp} + name {ins}" + (" + INSULATION choice group" if in_ins_group else "")
        if n - legacy:
            how += f"; its condition gates {n - legacy} {ins} cost line(s)"
        if legacy:
            how += f"; {legacy} {ins} line(s) tied by the legacy link only (no condition names it)"
        if not n:
            how += "; gates no cost line"
        cls.masters.append(Master(m["id"], name, grp, panel, ins, how))
        cls.by_master_id[m["id"]] = (panel, ins)
        _alias(cls, name, (panel, ins), f"master {m['id']}")
        for c in gated[m["id"]]:
            cls.lines.setdefault(c["id"], (panel, ins, c.get("bom_section") or ""))

    # insulation cost lines no classified master gates: their own section names the panel (include_all_items
    # prices them whatever their conditions say). Their include-condition names become aliases too: a draft flag
    # carrying that name prices the line with no master ticked.
    for c in costs:
        ins = _LINE_MATERIAL.get(_u(c.get("material_name")))
        if not ins:
            continue
        if c["id"] not in cls.lines and _u(c.get("bom_section")) in PANELS:
            cls.lines[c["id"]] = (_u(c.get("bom_section")), ins, c.get("bom_section") or "")
        if c["id"] not in cls.lines:
            continue
        panel, lins, _sec = cls.lines[c["id"]]
        mode, items = _conditions(c.get("bom_conditions"))
        if mode != "include":
            continue
        for i in items:
            opt = str(i.get("option") or "")
            if opt and str(i.get("equals") or "Y").upper() == "Y":
                _alias(cls, opt, (panel, lins), f"condition on line {c['id']}")
    return cls


def _alias(cls: Classification, name: str, pi: tuple[str, str], source: str) -> None:
    have = cls.by_name.get(name)
    if have is None:
        cls.by_name[name] = pi
    elif have != pi:
        cls.by_name.pop(name, None)
        cls.unclassified.append({"id": None, "name": name,
                                 "reason": f"the name selects both {have[1]} on {have[0]} and {pi[1]} on {pi[0]} ({source})"})


def _ids(v) -> set[int]:
    out = set()
    for x in v or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def selections(cls: Classification, payload: dict) -> list[tuple[str, str, str, str]]:
    """[(panel, insulation, via, ref)] — every insulation this payload selects, by the three mechanisms."""
    p = payload or {}
    out: list[tuple[str, str, str, str]] = []
    if p.get("include_all_items"):
        excl, cats = _ids(p.get("user_excluded_bom_ids")), set(p.get("excluded_categories") or [])
        for lid, (panel, ins, sec) in sorted(cls.lines.items()):
            if lid not in excl and sec not in cats:
                out.append((panel, ins, "line", str(lid)))
        return out
    for k, v in (p.get("body_option_selections") or {}).items():
        try:
            mid = int(k)
        except (TypeError, ValueError):
            continue
        if v is True or (isinstance(v, (int, float)) and bool(v)):
            if mid in cls.by_master_id:
                panel, ins = cls.by_master_id[mid]
                out.append((panel, ins, "selection", str(mid)))
    for name, v in (p.get("flag_overrides") or {}).items():
        if bool(v) and str(name) in cls.by_name:
            panel, ins = cls.by_name[str(name)]
            out.append((panel, ins, "flag", str(name)))
    return out


def normalise_rule(raw) -> dict[str, frozenset] | None:
    """The stored rule -> {panel: allowed insulations}; None = no rule. Raises ValueError on a malformed rule (the
    editor and the data step refuse to store one)."""
    if raw in (None, "", {}):
        return None
    d = json.loads(raw) if isinstance(raw, str) else raw
    allowed = (d or {}).get("allowed") if isinstance(d, dict) else None
    if not isinstance(allowed, dict) or set(allowed) != set(PANELS):
        raise ValueError(f"an insulation rule lists every panel exactly once: {', '.join(PANELS)}")
    out = {}
    for panel, ins in allowed.items():
        if not isinstance(ins, list) or not set(ins) <= set(INSULATIONS):
            raise ValueError(f"{panel}: the allowed insulation is a list of {', '.join(INSULATIONS)}")
        out[panel] = frozenset(ins)
    return out


def breaches(rule, cls: Classification, payload: dict) -> list[Breach]:
    """The selected insulations the rule forbids — one per (panel, insulation), first mechanism wins. No rule, no
    breach: a family without a rule is never blocked."""
    allowed = normalise_rule(rule) if not isinstance(rule, dict) or "allowed" in rule else rule
    if not allowed:
        return []
    seen, out = set(), []
    for panel, ins, via, ref in selections(cls, payload):
        if ins in allowed.get(panel, frozenset(INSULATIONS)) or (panel, ins) in seen:
            continue
        seen.add((panel, ins))
        out.append(Breach(panel, ins, via, ref))
    return out


def forbidden_choices(rule, cls: Classification) -> dict:
    """What the panels grey out: {'master_ids': [...], 'names': [...]} — every classified choice the rule forbids."""
    allowed = normalise_rule(rule) if not isinstance(rule, dict) or "allowed" in rule else rule
    if not allowed:
        return {"master_ids": [], "names": []}
    bad = lambda pi: pi[1] not in allowed.get(pi[0], frozenset(INSULATIONS))  # noqa: E731
    return {"master_ids": sorted(m for m, pi in cls.by_master_id.items() if bad(pi)),
            "names": sorted(n for n, pi in cls.by_name.items() if bad(pi))}
