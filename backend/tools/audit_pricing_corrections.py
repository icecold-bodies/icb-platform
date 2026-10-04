r"""
tools/audit_pricing_corrections.py
──────────────────────────────────
v1.58 — the pricing corrections found by the September costing audit, applied
from ONE manifest (BA dispatch 2, default 3):

    docs/audit/pricing_corrections_2026-09/manifest.yaml

Each manifest entry names one bill_of_materials line by id AND by body /
section / material name, one field, the EXACT current value (the guard) and
the new value:

    - finding: F1
      body_id: 19
      body: FREEZER 2.3 METER
      section: SRD
      bom_id: 3576
      line: PU
      field: formula_expression
      current: 1.22*2.44*2
      new: (1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2

Usage (from backend/, DATABASE_URL set):

    python tools/audit_pricing_corrections.py --target mirror                  dry-run
    python tools/audit_pricing_corrections.py --target mirror --apply          one transaction + journal
    python tools/audit_pricing_corrections.py --target mirror --revert J.json  byte-exact undo

Rules:
  * dry-run by default; --apply writes everything in ONE transaction;
  * every entry is either at its guard (-> changed) or already at its new value
    (-> skipped). Anything else is a guard mismatch and aborts the WHOLE apply
    before a single row is written — never assume the old value (the prod41
    lesson, 8 Sep);
  * idempotent: a second apply finds nothing to do;
  * journaled: the full before-row of every touched line and the id of every
    bom_override_history row written; --revert puts those rows back column for
    column and deletes the history rows (it refuses if a line moved since);
  * --target pins the database NAME (mirror = icb_prodmirror, prod =
    icb_platform, dev = icb, test = *_test): a DATABASE_URL pointing anywhere
    else is refused before anything is read.

A price (`unit_price_override`) change follows the September import: the line's
price_updated_at is stamped with the batch time and a bom_override_history row
is written for the admin trail. Formula and default changes touch nothing else.

v1.58.1 — `bom_conditions` (an item's inclusion rule, the column the Trailer
Designer's rule editor writes). The manifest gives the rule as a YAML list of
{option, equals, option_id}; the tool stores exactly the text the configurator
endpoint would (`json.dumps`, keys in the manifest's order). Guards and the
revert check compare it as CANONICAL JSON (sorted keys, no whitespace), so key
order or spacing never makes a false mismatch; --revert restores the stored text
from the journal's before-row. `body:` may list several names for one body_id
(dev and prod name some bodies differently); body_id stays exact.

Optional per-entry check — `equal_at: {length: 6.7}` evaluates the current and
the new formula through the MES formula engine at those dimensions (plus the
database's global variables and any `vars:` given) and refuses the manifest
unless they agree: the F3 substitutions must equal the literal 6.7 at 6.7 m.

v1.60.1 (RT4 Manifest S) — three more things a manifest can say:

  * `field: section` moves a line to another section. The value is the PAIR
    {id, name} — bom_section_id and the legacy bom_section string — guarded and
    written together, exactly as services.sections.move_rows_to_section writes
    them. The entry's `section:` names the line's current section string; the
    target section row must exist under that id and name.
  * a top-level `drafts:` list re-keys a body's Settings-page draft by the A2
    rule (services.sections.rewrite_draft_key): {finding, body_id, body,
    old_key, new_key, nodes}. Guard: exactly `nodes` category nodes keyed
    old_key and none keyed new_key (done: none old, `nodes` new). The journal
    keeps the whole before-payload; --revert restores it while the draft still
    holds the applied payload. Draft snapshots are never touched.
  * `expect_unused_after: [section ids]` — after the apply no line (by id or
    string) and no draft may name those sections. Before the apply, every line
    and draft naming them must be pending in this manifest; otherwise the run
    STOPs (RT4_RULING_1 Q3: "if any other body or draft still names one, STOP").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BATCH_NOTE = "v1.58 costing-audit pricing corrections (Sept 2026 findings)"
DEFAULT_MANIFEST = (Path(__file__).resolve().parents[2]
                    / "docs" / "audit" / "pricing_corrections_2026-09" / "manifest.yaml")

TARGETS = {"mirror": "icb_prodmirror", "prod": "icb_platform", "dev": "icb", "test": None}
FIELDS = {"formula_expression": str, "unit_price_override": float, "body_option_default": bool,
          "bom_conditions": list, "section": dict}
PRICE_FIELD = "unit_price_override"
CONDITIONS_FIELD = "bom_conditions"
SECTION_FIELD = "section"
REVERT_COLUMNS = ("formula_expression", "unit_price_override", "body_option_default", "bom_conditions",
                  "price_updated_at", "bom_section_id", "bom_section")
DRAFT_KEYS = {"finding", "body_id", "body", "old_key", "new_key", "nodes", "note"}
EQUAL_TOL = 1e-9
ENTRY_KEYS = {"finding", "body_id", "body", "section", "bom_id", "line", "field", "current", "new",
              "equal_at", "vars", "note"}


class ManifestError(SystemExit):
    pass


class GuardMismatch(RuntimeError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Change:
    finding: str
    body_id: int
    body: str
    section: str
    bom_id: int
    line: str
    field: str
    current: object
    new: object
    equal_at: dict | None = None
    vars: dict | None = None
    # every body name the identity guard accepts for body_id — a manifest may list the
    # dev AND prod names of one body (dev still says ICECREAM 4.9 UP where prod says
    # ICECREAM BODY LARGE); body_id itself stays exact
    bodies: tuple = ()

    @property
    def key(self) -> str:
        return f"{self.finding} bom={self.bom_id} {self.body} / {self.section} / {self.line} .{self.field}"


@dataclass(frozen=True)
class DraftChange:
    finding: str
    body_id: int
    body: str
    old_key: str
    new_key: str
    nodes: int

    @property
    def key(self) -> str:
        return f"{self.finding} draft of body {self.body_id} {self.body}: {self.old_key!r} -> {self.new_key!r}"


@dataclass
class Plan:
    todo: list[Change] = field(default_factory=list)
    done: list[Change] = field(default_factory=list)
    rows: dict[int, dict] = field(default_factory=dict)      # bom_id -> full current row
    draft_todo: list[DraftChange] = field(default_factory=list)
    draft_done: list[DraftChange] = field(default_factory=list)
    drafts: dict[int, str] = field(default_factory=dict)     # body_id -> current draft payload


# ── manifest ─────────────────────────────────────────────────────────────────

def _conditions_text(v):
    """A bom_conditions manifest value -> the exact text the configurator endpoint stores
    (trailers.py PATCH /items/{id}/conditions: `json.dumps(cleaned)`, default separators, keys
    in the order given — the manifest writes option, equals, option_id like the endpoint)."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            raise ManifestError(f"bom_conditions: not JSON: {v!r}")
    if isinstance(v, list):
        for c in v:
            if not (isinstance(c, dict) and isinstance(c.get("option"), str) and c.get("equals") in ("Y", "N")):
                raise ManifestError(f"bom_conditions: each condition needs option + equals Y/N, got {c!r}")
    elif not (isinstance(v, dict) and v.get("mode") in ("exclude", "always_exclude")):
        raise ManifestError(f"bom_conditions: expected a list of conditions or an exclude/always_exclude "
                            f"object, got {v!r}")
    return json.dumps(v)


def _canonical(field_name: str, v):
    """The value a guard compares. bom_conditions compares as canonical JSON (sorted keys, no
    whitespace), so key order or spacing in the stored text never causes a false mismatch. A section
    compares as the pair (id, name) — both columns, never one alone."""
    if field_name == SECTION_FIELD and isinstance(v, dict):
        return (v.get("id"), v.get("name"))
    if field_name != CONDITIONS_FIELD or v is None:
        return v
    try:
        return json.dumps(json.loads(v), sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError):
        return ("<unparseable>", v)          # never equal to a manifest value


def _same(field_name: str, a, b) -> bool:
    return _canonical(field_name, a) == _canonical(field_name, b)


def _coerce(field_name: str, v):
    if v is None:
        return None
    kind = FIELDS[field_name]
    if kind is dict:
        if not (isinstance(v, dict) and set(v) == {"id", "name"} and isinstance(v["id"], int)
                and not isinstance(v["id"], bool) and isinstance(v["name"], str) and v["name"]):
            raise ManifestError(f"{field_name}: expected {{id: <int>, name: <text>}}, got {v!r}")
        return {"id": v["id"], "name": v["name"]}
    if kind is list:
        return _conditions_text(v)
    if kind is bool:
        if not isinstance(v, bool):
            raise ManifestError(f"{field_name}: expected true/false, got {v!r}")
        return v
    if kind is float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ManifestError(f"{field_name}: expected a number or null, got {v!r}")
        return float(v)
    if not isinstance(v, str):
        raise ManifestError(f"{field_name}: expected a string, got {v!r}")
    return v


def load_manifest(path: Path) -> tuple[list[Change], str]:
    """(changes, sha256 of the manifest bytes). Refuses unknown keys/fields,
    duplicate (bom_id, field) pairs and no-op entries."""
    import yaml
    raw_bytes = Path(path).read_bytes()
    doc = yaml.safe_load(raw_bytes.decode("utf-8"))
    entries = doc.get("changes") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ManifestError(f"{path}: no `changes:` list")
    out: list[Change] = []
    seen: set[tuple[int, str]] = set()
    for i, e in enumerate(entries):
        where = f"{path.name} entry {i + 1}"
        if not isinstance(e, dict):
            raise ManifestError(f"{where}: not a mapping")
        extra = set(e) - ENTRY_KEYS
        missing = {"finding", "body_id", "body", "section", "bom_id", "line", "field", "current", "new"} - set(e)
        if extra or missing:
            raise ManifestError(f"{where}: unknown keys {sorted(extra)} / missing keys {sorted(missing)}")
        if e["field"] not in FIELDS:
            raise ManifestError(f"{where}: field {e['field']!r} is not one this tool writes {sorted(FIELDS)}")
        cur = _coerce(e["field"], e["current"])
        new = _coerce(e["field"], e["new"])
        names = e["body"] if isinstance(e["body"], list) else [e["body"]]
        if not names or not all(isinstance(n, str) and n for n in names):
            raise ManifestError(f"{where}: body must be a name or a list of names")
        if _same(e["field"], cur, new):
            raise ManifestError(f"{where}: current == new ({cur!r}) — a no-op entry is a manifest mistake")
        k = (int(e["bom_id"]), e["field"])
        if k in seen:
            raise ManifestError(f"{where}: bom {k[0]} field {k[1]} appears twice")
        seen.add(k)
        if e.get("equal_at") is not None and e["field"] != "formula_expression":
            raise ManifestError(f"{where}: equal_at only applies to formula_expression")
        if e["field"] == SECTION_FIELD and str(e["section"]) != cur["name"]:
            raise ManifestError(f"{where}: `section:` {e['section']!r} must be the line's current section "
                                f"string {cur['name']!r}")
        out.append(Change(finding=str(e["finding"]), body_id=int(e["body_id"]), body=" | ".join(names),
                          section=str(e["section"]), bom_id=int(e["bom_id"]), line=str(e["line"]),
                          field=e["field"], current=cur, new=new,
                          equal_at=e.get("equal_at"), vars=e.get("vars"), bodies=tuple(names)))
    return out, hashlib.sha256(raw_bytes).hexdigest()


def load_drafts(path: Path) -> list[DraftChange]:
    """The manifest's optional top-level `drafts:` list (v1.60.1)."""
    import yaml
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    entries = (doc.get("drafts") if isinstance(doc, dict) else None) or []
    if not isinstance(entries, list):
        raise ManifestError(f"{path}: `drafts:` must be a list")
    out, seen = [], set()
    need = {"finding", "body_id", "body", "old_key", "new_key", "nodes"}
    for i, e in enumerate(entries):
        where = f"{Path(path).name} drafts entry {i + 1}"
        if not isinstance(e, dict) or set(e) - DRAFT_KEYS or need - set(e):
            raise ManifestError(f"{where}: needs exactly finding, body_id, body, old_key, new_key, nodes (+ note)")
        if not (isinstance(e["nodes"], int) and not isinstance(e["nodes"], bool) and e["nodes"] > 0):
            raise ManifestError(f"{where}: nodes must be a positive integer")
        if str(e["old_key"]).strip().upper() == str(e["new_key"]).strip().upper():
            raise ManifestError(f"{where}: old_key == new_key — a no-op entry is a manifest mistake")
        k = (int(e["body_id"]), str(e["old_key"]).strip().upper())
        if k in seen:
            raise ManifestError(f"{where}: body {k[0]} key {k[1]!r} appears twice")
        seen.add(k)
        out.append(DraftChange(finding=str(e["finding"]), body_id=int(e["body_id"]), body=str(e["body"]),
                               old_key=str(e["old_key"]), new_key=str(e["new_key"]), nodes=int(e["nodes"])))
    return out


def load_expect_unused(path: Path) -> list[int]:
    """The manifest's optional `expect_unused_after:` section ids (v1.60.1)."""
    import yaml
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    ids = (doc.get("expect_unused_after") if isinstance(doc, dict) else None) or []
    if not (isinstance(ids, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
        raise ManifestError(f"{path}: `expect_unused_after:` must be a list of section ids")
    return ids


def manifest_note(path: Path) -> str:
    """The manifest's own top-level `note:` (journaled), else the v1.58 batch note."""
    import yaml
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    note = doc.get("note") if isinstance(doc, dict) else None
    return str(note) if note else BATCH_NOTE


def check_equivalences(changes: list[Change], global_vars: dict) -> list[str]:
    """Every `equal_at` entry: current and new formula agree at those dims."""
    from app.formula_engine import build_geometry, evaluate_formula
    bad = []
    for c in changes:
        if not c.equal_at:
            continue
        ctx = build_geometry(c.equal_at)
        variables = {**global_vars, **(c.vars or {})}
        unknown: list = []
        a = evaluate_formula(c.current, ctx, variables, _unknown=unknown)
        b = evaluate_formula(c.new, ctx, variables, _unknown=unknown)
        if unknown:
            bad.append(f"{c.key}: unresolved token(s) {sorted(set(unknown))} in the equivalence check")
        elif abs(a - b) > EQUAL_TOL:
            bad.append(f"{c.key}: at {c.equal_at} current={a!r} new={b!r}")
    return bad


# ── database ────────────────────────────────────────────────────────────────

def assert_target(target: str) -> str:
    from app.config import settings
    from app.db_guard import resolve_db_name
    name = resolve_db_name(settings.DATABASE_URL)
    want = TARGETS[target]
    ok = name.endswith("_test") if want is None else name == want
    if not ok:
        raise SystemExit(f"REFUSED: --target {target} expects database "
                         f"{want or '*_test'!r} but DATABASE_URL resolves to {name!r}")
    return name


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _fetch_rows(conn, bom_ids) -> dict[int, dict]:
    import sqlalchemy as sa
    if not bom_ids:
        return {}
    res = conn.execute(sa.text("""
        SELECT b.*, t.name AS _trailer_name, m.name AS _material_name
          FROM bill_of_materials b
          LEFT JOIN trailer_types t ON t.id = b.trailer_type_id
          LEFT JOIN materials m ON m.id = b.material_id
         WHERE b.id = ANY(:ids)"""), {"ids": sorted(set(bom_ids))}).mappings().all()
    return {r["id"]: dict(r) for r in res}


def _global_vars(conn) -> dict:
    import sqlalchemy as sa
    return {r[0]: r[1] for r in conn.execute(sa.text("SELECT name, value FROM global_variables"))}


def build_plan(conn, changes: list[Change]) -> Plan:
    """Read the lines and sort every change into todo / done. Raises
    GuardMismatch (listing EVERY problem) if any line is not where the manifest
    says it is — identity or value."""
    rows = _fetch_rows(conn, [c.bom_id for c in changes])
    plan = Plan(rows=rows)
    problems: list[str] = []
    for c in changes:
        r = rows.get(c.bom_id)
        if r is None:
            problems.append(f"{c.key}: line not found")
            continue
        ident = {"body_id": (r["trailer_type_id"] == c.body_id, r["trailer_type_id"]),
                 "body": (r["_trailer_name"] in (c.bodies or (c.body,)), r["_trailer_name"]),
                 "line": (r["_material_name"] == c.line, r["_material_name"])}
        if c.field != SECTION_FIELD:      # a section move guards the section as its VALUE (both columns)
            ident["section"] = (r["bom_section"] == c.section, r["bom_section"])
        wrong = [f"{k} is {have!r}" for k, (ok, have) in ident.items() if not ok]
        if wrong:
            problems.append(f"{c.key}: identity mismatch — " + ", ".join(wrong))
            continue
        have = _value(r, c.field)
        if _same(c.field, have, c.current):
            plan.todo.append(c)
        elif _same(c.field, have, c.new):
            plan.done.append(c)
        else:
            problems.append(f"{c.key}: GUARD — found {have!r}, manifest expects {c.current!r} (new {c.new!r})")
    problems += _target_section_problems(conn, [c for c in changes if c.field == SECTION_FIELD])
    if problems:
        raise GuardMismatch(problems)
    return plan


def _value(row: dict, field_name: str):
    """A line's current value for a manifest field — a section is the pair of columns."""
    if field_name == SECTION_FIELD:
        return {"id": row["bom_section_id"], "name": row["bom_section"]}
    return row[field_name]


def _target_section_problems(conn, moves: list[Change]) -> list[str]:
    """Every section a move points at must exist under exactly that id AND name."""
    import sqlalchemy as sa
    if not moves:
        return []
    have = dict(conn.execute(sa.text("SELECT id, name FROM bom_sections WHERE id = ANY(:i)"),
                             {"i": sorted({c.new["id"] for c in moves})}).all())
    return [f"{c.key}: target section {c.new['id']} is {have.get(c.new['id'])!r}, manifest says {c.new['name']!r}"
            for c in moves if have.get(c.new["id"]) != c.new["name"]]


def build_draft_plan(conn, plan: Plan, drafts: list[DraftChange]) -> None:
    """Sort every draft change into plan.draft_todo / draft_done; GuardMismatch lists every problem."""
    import sqlalchemy as sa
    from app.services.sections import draft_category_count
    if not drafts:
        return
    ids = sorted({d.body_id for d in drafts})
    rows = dict(conn.execute(sa.text("SELECT trailer_type_id, payload FROM configurator_drafts "
                                     "WHERE trailer_type_id = ANY(:t)"), {"t": ids}).all())
    names = dict(conn.execute(sa.text("SELECT id, name FROM trailer_types WHERE id = ANY(:t)"), {"t": ids}).all())
    problems = []
    for d in drafts:
        if names.get(d.body_id) != d.body:
            problems.append(f"{d.key}: body {d.body_id} is {names.get(d.body_id)!r}")
            continue
        payload = rows.get(d.body_id)
        if payload is None:
            problems.append(f"{d.key}: the body has no draft")
            continue
        plan.drafts[d.body_id] = payload
        n_old, n_new = draft_category_count(payload, d.old_key), draft_category_count(payload, d.new_key)
        if (n_old, n_new) == (d.nodes, 0):
            plan.draft_todo.append(d)
        elif (n_old, n_new) == (0, d.nodes):
            plan.draft_done.append(d)
        else:
            problems.append(f"{d.key}: GUARD — the draft has {n_old} node(s) keyed old and {n_new} keyed new; "
                            f"the manifest expects {d.nodes} / 0 (or 0 / {d.nodes} once applied)")
    if problems:
        raise GuardMismatch(problems)


def unused_after_problems(conn, section_ids: list[int], plan: Plan) -> list[str]:
    """`expect_unused_after`: once THIS manifest is fully applied, no line and no draft may name those sections.
    Every line / draft still naming them must be pending in this plan — anything else is a STOP."""
    import sqlalchemy as sa
    from app.services.sections import draft_category_count
    if not section_ids:
        return []
    secs = dict(conn.execute(sa.text("SELECT id, name FROM bom_sections WHERE id = ANY(:i)"),
                             {"i": section_ids}).all())
    problems = [f"expect_unused_after: section {i} does not exist" for i in section_ids if i not in secs]
    moving = {c.bom_id for c in plan.todo if c.field == SECTION_FIELD}
    rekeying = {(d.body_id, d.old_key.strip().upper()) for d in plan.draft_todo}
    drafts = conn.execute(sa.text("SELECT trailer_type_id, payload FROM configurator_drafts")).all()
    for sid, name in sorted(secs.items()):
        lines = conn.execute(sa.text("SELECT id, trailer_type_id FROM bill_of_materials "
                                     "WHERE bom_section_id = :i OR bom_section = :n ORDER BY id"),
                             {"i": sid, "n": name}).all()
        stay = [f"bom {b} (body {t})" for b, t in lines if b not in moving]
        if stay:
            problems.append(f"expect_unused_after: section {sid} {name!r} would still be used by "
                            f"{len(stay)} line(s) this manifest does not move: {', '.join(stay[:10])}")
        named = [t for t, p in drafts
                 if draft_category_count(p, name) and (t, name.strip().upper()) not in rekeying]
        if named:
            problems.append(f"expect_unused_after: section {sid} {name!r} would still be named by the draft of "
                            f"body {', '.join(str(t) for t in named)}")
    return problems


def apply_plan(conn, plan: Plan, *, target: str, dbname: str, manifest_sha: str,
               batch: datetime | None = None, note: str = BATCH_NOTE) -> dict:
    """Write plan.todo on `conn` (the caller owns the transaction). Returns the journal."""
    import sqlalchemy as sa
    batch = batch or datetime.now(timezone.utc)
    touched = sorted({c.bom_id for c in plan.todo})
    journal = {"tool": "audit_pricing_corrections", "note": note, "batch_at": batch.isoformat(),
               "target": target, "database": dbname, "manifest_sha256": manifest_sha,
               "changes": [], "before_rows": {}, "override_history_ids": []}
    for bid in touched:
        row = {k: _jsonable(v) for k, v in plan.rows[bid].items() if not k.startswith("_")}
        journal["before_rows"][str(bid)] = row
    for c in plan.todo:
        r = plan.rows[c.bom_id]
        if c.field == PRICE_FIELD:
            conn.execute(sa.text("UPDATE bill_of_materials SET unit_price_override=:v, price_updated_at=:now "
                                 "WHERE id=:i"), {"v": c.new, "now": batch, "i": c.bom_id})
            ohid = conn.execute(sa.text("""
                INSERT INTO bom_override_history
                    (bom_id, material_id, trailer_type_id, trailer_type_name, material_name,
                     old_price, new_price, changed_at, batch_at)
                VALUES (:b, :m, :t, :tn, :mn, :o, :n, :now, :now) RETURNING id"""),
                {"b": c.bom_id, "m": r["material_id"], "t": r["trailer_type_id"],
                 "tn": r["_trailer_name"], "mn": r["_material_name"],
                 "o": c.current, "n": c.new, "now": batch}).scalar()
            journal["override_history_ids"].append(ohid)
        elif c.field == SECTION_FIELD:
            conn.execute(sa.text("UPDATE bill_of_materials SET bom_section_id=:s, bom_section=:n WHERE id=:i"),
                         {"s": c.new["id"], "n": c.new["name"], "i": c.bom_id})
        else:
            conn.execute(sa.text(f"UPDATE bill_of_materials SET {c.field}=:v WHERE id=:i"),
                         {"v": c.new, "i": c.bom_id})
        journal["changes"].append({"finding": c.finding, "bom_id": c.bom_id, "body": c.body,
                                   "section": c.section, "line": c.line, "field": c.field,
                                   "before": c.current, "after": c.new})
    if plan.draft_todo:
        from app.services.sections import rewrite_draft_key
        journal["drafts"] = []
        for body_id in sorted({d.body_id for d in plan.draft_todo}):
            before = plan.drafts[body_id]
            payload = before
            for d in [x for x in plan.draft_todo if x.body_id == body_id]:
                status, new_payload, n = rewrite_draft_key(payload, d.old_key, d.new_key)
                if status != "rewritten" or n != d.nodes:       # the plan's guard said otherwise: never write
                    raise GuardMismatch([f"{d.key}: the A2 rule answered {status!r} ({n} node(s))"])
                payload = new_payload
                journal["changes"].append({"finding": d.finding, "draft_body_id": body_id, "body": d.body,
                                           "field": "draft_key", "before": d.old_key, "after": d.new_key,
                                           "nodes": n})
            conn.execute(sa.text("UPDATE configurator_drafts SET payload=:p WHERE trailer_type_id=:t"),
                         {"p": payload, "t": body_id})
            journal["drafts"].append({"body_id": body_id, "before_payload": before,
                                      "after_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()})
    return journal


def revert_journal(conn, journal: dict) -> dict:
    """Put every touched line back column for column; delete the history rows.
    Refuses (GuardMismatch) if a line no longer carries the journal's after-value."""
    import sqlalchemy as sa
    bids = [int(b) for b in journal["before_rows"]]
    rows = _fetch_rows(conn, bids)
    problems = []
    for ch in journal["changes"]:
        if "bom_id" not in ch:            # a draft entry — checked below, by the whole payload
            continue
        r = rows.get(ch["bom_id"])
        if r is None:
            problems.append(f"bom {ch['bom_id']}: line not found")
        elif not _same(ch["field"], _value(r, ch["field"]), ch["after"]):
            problems.append(f"bom {ch['bom_id']} .{ch['field']}: found {_value(r, ch['field'])!r}, "
                            f"journal applied {ch['after']!r} — moved since the apply")
    for dj in journal.get("drafts") or []:
        have = conn.execute(sa.text("SELECT payload FROM configurator_drafts WHERE trailer_type_id=:t"),
                            {"t": dj["body_id"]}).scalar()
        if have is None or hashlib.sha256(have.encode("utf-8")).hexdigest() != dj["after_sha256"]:
            problems.append(f"draft of body {dj['body_id']}: changed since the apply (or gone)")
    hist = journal.get("override_history_ids") or []
    if hist:
        have = {r[0] for r in conn.execute(sa.text("SELECT id FROM bom_override_history WHERE id = ANY(:ids)"),
                                           {"ids": hist})}
        for h in hist:
            if h not in have:
                problems.append(f"bom_override_history {h}: missing")
    if problems:
        raise GuardMismatch(problems)
    for bid, before in journal["before_rows"].items():
        stamp = before["price_updated_at"]
        conn.execute(sa.text("UPDATE bill_of_materials SET formula_expression=:f, unit_price_override=:o, "
                             "body_option_default=:d, bom_conditions=:c, price_updated_at=:p, "
                             "bom_section_id=:si, bom_section=:sn WHERE id=:i"),
                     {"f": before["formula_expression"], "o": before["unit_price_override"],
                      "d": before["body_option_default"], "c": before["bom_conditions"],
                      "p": datetime.fromisoformat(stamp) if stamp else None,
                      "si": before["bom_section_id"], "sn": before["bom_section"], "i": int(bid)})
    for dj in journal.get("drafts") or []:
        conn.execute(sa.text("UPDATE configurator_drafts SET payload=:p WHERE trailer_type_id=:t"),
                     {"p": dj["before_payload"], "t": dj["body_id"]})
    if hist:
        conn.execute(sa.text("DELETE FROM bom_override_history WHERE id = ANY(:ids)"), {"ids": hist})
    return {"reverted_at": datetime.now(timezone.utc).isoformat(), "journal_batch_at": journal["batch_at"],
            "lines": len(journal["before_rows"]), "override_history_deleted": len(hist),
            "drafts": len(journal.get("drafts") or [])}


# ── report ───────────────────────────────────────────────────────────────────

def _fmt(v) -> str:
    return "null" if v is None else repr(v)


def print_plan(plan: Plan, changes: list[Change]) -> None:
    by_finding: dict[str, list[str]] = {}
    for c in changes:
        state = "APPLY" if c in plan.todo else "done "
        by_finding.setdefault(c.finding, []).append(
            f"  {state} bom={c.bom_id:<6} {c.body} / {c.section} / {c.line}  .{c.field}\n"
            f"          {_fmt(c.current)}\n       -> {_fmt(c.new)}")
    for d in plan.draft_todo + plan.draft_done:
        state = "APPLY" if d in plan.draft_todo else "done "
        by_finding.setdefault(d.finding, []).append(
            f"  {state} draft of body {d.body_id} {d.body}: {d.nodes} category node(s)\n"
            f"          {d.old_key!r}\n       -> {d.new_key!r}")
    for f in sorted(by_finding):
        print(f"── {f}")
        for line in by_finding[f]:
            print(line)


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v1.58 costing-audit pricing corrections (manifest-driven)")
    ap.add_argument("--target", required=True, choices=sorted(TARGETS),
                    help="pins the database name: mirror=icb_prodmirror prod=icb_platform dev=icb test=*_test")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument("--revert", metavar="JOURNAL_JSON", help="undo one apply, byte-exact")
    ap.add_argument("--out-dir", default=".", help="where the journal is written (default: cwd)")
    a = ap.parse_args(argv)

    dbname = assert_target(a.target)
    from app.database import engine
    out_dir = Path(a.out_dir)

    if a.revert:
        jpath = Path(a.revert)
        journal = json.loads(jpath.read_text(encoding="utf-8"))
        if journal.get("database") != dbname:
            raise SystemExit(f"REFUSED: journal {jpath.name} was written on {journal.get('database')!r}, "
                             f"this is {dbname!r}")
        with engine.connect() as conn:
            try:
                res = revert_journal(conn, journal)
            except GuardMismatch as g:
                conn.rollback()
                print("REVERT ABORTED — nothing written:")
                for p in g.problems:
                    print("  -", p)
                return 2
            conn.commit()
        rpath = out_dir / f"pricing_corrections_revert_{a.target}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        out_dir.mkdir(parents=True, exist_ok=True)
        rpath.write_text(json.dumps({**res, "journal": jpath.name, "database": dbname}, indent=2), encoding="utf-8")
        print(f"REVERTED {jpath.name}: {res['lines']} lines restored, "
              f"{res['override_history_deleted']} bom_override_history rows deleted, "
              f"{res['drafts']} draft(s) restored. Record: {rpath}")
        return 0

    changes, sha = load_manifest(Path(a.manifest))
    print(f"database {dbname} (--target {a.target}); manifest {Path(a.manifest).name} sha256 {sha[:16]}…, "
          f"{len(changes)} entries")
    import sqlalchemy as sa
    # connect(): nothing is committed unless the apply path says so; leaving the
    # block rolls back. A dry-run is also READ ONLY, so on prod it cannot write.
    with engine.connect() as conn:
        if not a.apply:
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        bad = check_equivalences(changes, _global_vars(conn))
        if bad:
            print("ABORT — an equal_at check failed (manifest mistake); nothing written:")
            for b in bad:
                print("  -", b)
            return 2
        try:
            plan = build_plan(conn, changes)
            build_draft_plan(conn, plan, load_drafts(Path(a.manifest)))
        except GuardMismatch as g:
            print(f"ABORT — {len(g.problems)} guard mismatch(es); the database is not where the manifest "
                  f"says. Nothing written:")
            for p in g.problems:
                print("  -", p)
            return 2
        print_plan(plan, changes)
        n_todo = len(plan.todo) + len(plan.draft_todo)
        n_done = len(plan.done) + len(plan.draft_done)
        print(f"\n{n_todo} to apply, {n_done} already applied.")
        unused = load_expect_unused(Path(a.manifest))
        bad = unused_after_problems(conn, unused, plan)
        if bad:
            print("STOP — after this manifest a section that must end up unused would still be named. "
                  "Nothing written:")
            for b in bad:
                print("  -", b)
            return 2
        if unused:
            print(f"expect_unused_after {unused}: no other line or draft names them — "
                  + ("they are unused now." if not n_todo else "they are unused once this applies."))
        if not n_todo:
            print("nothing to apply.")
            return 0
        if not a.apply:
            print("(DRY RUN — nothing written. Re-run with --apply.)")
            return 0
        journal = apply_plan(conn, plan, target=a.target, dbname=dbname, manifest_sha=sha,
                             note=manifest_note(Path(a.manifest)))
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.fromisoformat(journal["batch_at"]).strftime("%Y%m%dT%H%M%SZ")
        jpath = out_dir / f"pricing_corrections_journal_{a.target}_{ts}.json"
        jpath.write_text(json.dumps(journal, indent=2, default=str), encoding="utf-8")
        try:
            conn.commit()
        except Exception:
            jpath.unlink(missing_ok=True)
            raise
    print(f"APPLIED {len(journal['changes'])} changes on {len(journal['before_rows'])} lines "
          f"({len(journal['override_history_ids'])} bom_override_history rows, "
          f"{len(journal.get('drafts') or [])} draft(s)). Journal: {jpath}")
    print(f"Undo: python tools/audit_pricing_corrections.py --target {a.target} --revert {jpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
