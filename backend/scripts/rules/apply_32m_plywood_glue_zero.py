"""Zero 4MM PF PLYWOOD + its paired GLUE LINE at exactly 3.2 m on the two
MEDIUM bodies (Nadie's costing rule, ratified by Michael — Aug 2026).

The rule: on CHILLER MEDIUM ("UP TO 5.5 CHILLER AND 2.3 WIDE") and FREEZER
MEDIUM ("UP TO 4.8 MT FREEZER  2"), when the entered LENGTH is literally
3.2 m, the FRONT and SIDES "4MM PF PLYWOOD" row and the GLUE LINE row
directly BELOW it (BA-ratified pairing) must total R0,00 — rows stay visible
with qty 0, never hidden. Doors (DRD/SRD), FLOOR and OPTIONAL EXTRAS plywood
are deliberately out of scope.

Mechanism — a data-driven guard appended to each pinned row's
``formula_expression``:

    ({original}) * (0 if abs(length - 3.2) < 1e-9 else 1)

``length`` is always in the engine's eval scope (even for FRONT rows whose
base formula doesn't reference it), so the guard zeroes the QUANTITY at
exactly 3.2 (3.20 parses identically; 3.19 / 3.21 cost normally) and the zero
flows to both calculators, previews, exports and newly saved costings. The
red user notice (calculator.js + export builders) keys off this guard text —
apply the guard and the notice lights up with no further wiring.

Matching is by NAME, never id (dev/prod ids may drift): each body resolves
against a whitespace-collapsed, case-insensitive name SET — the imported
original AND the "CHILLER MEDIUM"/"FREEZER MEDIUM" rename — and 0 or >1
active matches fails loud, printing the live template list. The paired glue
row is resolved STRUCTURALLY: the next row below the plywood in the same
section (by sort_order) must be a GLUE LINE, else the section listing is
printed and nothing is written. All-or-nothing: --apply refuses to write
unless every pinned row on every matched body resolves cleanly.

Idempotent: rows whose formula already carries the guard factor report
ALREADY-GUARDED and are skipped, so a re-run on a guarded DB is a no-op.

Dry-run by default — prints every row before/after and exits without touching
the DB. Pass --apply to write.

Run (dev):   .venv\\Scripts\\python backend\\scripts\\rules\\apply_32m_plywood_glue_zero.py [--apply]
Run (prod):  sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; \
               /opt/icb-platform/.venv/bin/python \
               /opt/icb-platform/backend/scripts/rules/apply_32m_plywood_glue_zero.py [--apply]'
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PINNED_LENGTH = "3.2"
GUARD_TAIL = f"* (0 if abs(length - {PINNED_LENGTH}) < 1e-9 else 1)"
# Any length-pinned guard of this shape counts as "already guarded" — matches
# app.services.ZERO_RULE_GUARD_RE and the calculator.js detection regex.
GUARD_MARKER_RE = re.compile(r"\*\s*\(0 if abs\(length - [0-9]*\.?[0-9]+\) < 1e-9 else 1\)")

RULES = [
    {"body": "CHILLER MEDIUM",
     "names": {"CHILLER MEDIUM", "UP TO 5.5 CHILLER AND 2.3 WIDE"}},
    {"body": "FREEZER MEDIUM",
     # The live imported name carries a double space ("FREEZER  2"); norm()
     # collapses whitespace so one spelling here covers both.
     "names": {"FREEZER MEDIUM", "UP TO 4.8 MT FREEZER 2"}},
]
SECTIONS = ("FRONT", "SIDES")
PLY_NAME = "4MM PF PLYWOOD"
GLUE_NAME = "GLUE LINE"


def norm(s) -> str:
    """Whitespace-collapsed, case-insensitive comparison key."""
    return " ".join(str(s or "").split()).upper()


def is_guarded(expr) -> bool:
    return bool(GUARD_MARKER_RE.search(expr or ""))


def guard_formula(expr) -> str:
    return f"({(expr or '1').strip()}) {GUARD_TAIL}"


def collect(db, rules=None):
    """Resolve every pinned row. Returns (actions, already, errors) where
    actions = [{tt, body, section, role, row, before, after}, …],
    already  = [{tt, body, section, role, row}, …]  (guard present, no-op),
    errors   = [str, …]  (any entry ⇒ nothing may be written)."""
    from app.database import BillOfMaterial, TrailerType

    rules = RULES if rules is None else rules
    actions, already, errors = [], [], []

    active_tts = db.query(TrailerType).filter_by(is_active=True).all()
    by_norm: dict[str, list] = {}
    for tt in active_tts:
        by_norm.setdefault(norm(tt.name), []).append(tt)

    for rule in rules:
        want = {norm(n) for n in rule["names"]}
        hits = [tt for key, tts in by_norm.items() if key in want for tt in tts]
        if len(hits) != 1:
            errors.append(
                f"{rule['body']}: {len(hits)} active template(s) match {sorted(want)} — "
                f"expected exactly 1. Active templates: "
                + "; ".join(sorted(t.name for t in active_tts)))
            continue
        tt = hits[0]
        print(f"[MATCH] {rule['body']} -> {tt.name!r} (id {tt.id})")

        rows = (db.query(BillOfMaterial)
                .filter_by(trailer_type_id=tt.id).all())
        for section in SECTIONS:
            sec_rows = sorted((r for r in rows if norm(r.bom_section) == section),
                              key=lambda r: (r.sort_order or 0, r.id))
            def mat_name(r):
                return norm(r.material.name if r.material else "")

            plys = [r for r in sec_rows if mat_name(r) == norm(PLY_NAME)]
            if len(plys) != 1:
                errors.append(
                    f"{tt.name} / {section}: {len(plys)} '{PLY_NAME}' row(s) — expected exactly 1. "
                    f"Section rows: " + "; ".join(
                        f"sort={r.sort_order} id={r.id} {mat_name(r)!r}" for r in sec_rows))
                continue
            ply = plys[0]
            below = [r for r in sec_rows
                     if (r.sort_order or 0, r.id) > ((ply.sort_order or 0), ply.id)]
            glue = below[0] if below else None
            if glue is None or mat_name(glue) != norm(GLUE_NAME):
                errors.append(
                    f"{tt.name} / {section}: the row directly below the plywood "
                    f"(sort={ply.sort_order}) is "
                    f"{'missing' if glue is None else mat_name(glue)!r} — expected '{GLUE_NAME}'. "
                    f"Section rows: " + "; ".join(
                        f"sort={r.sort_order} id={r.id} {mat_name(r)!r}" for r in sec_rows))
                continue

            for role, row in (("plywood", ply), ("glue", glue)):
                entry = {"tt": tt, "body": rule["body"], "section": section,
                         "role": role, "row": row}
                if is_guarded(row.formula_expression):
                    already.append(entry)
                else:
                    entry["before"] = row.formula_expression or ""
                    entry["after"] = guard_formula(row.formula_expression)
                    actions.append(entry)

    return actions, already, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the guards (default: dry-run, no DB writes)")
    args = ap.parse_args()

    from app.database import SessionLocal

    with SessionLocal() as db:
        actions, already, errors = collect(db)

        for e in errors:
            print(f"[ERROR] {e}")
        for a in already:
            r = a["row"]
            print(f"[ALREADY-GUARDED] {a['tt'].name} / {a['section']} / {a['role']} "
                  f"(bom_id {r.id}): guard present — no-op")
        verb = "APPLY" if args.apply else "DRY-RUN"
        for a in actions:
            r = a["row"]
            print(f"[{verb}] {a['tt'].name} / {a['section']} / {a['role']} (bom_id {r.id}):")
            print(f"    before: {a['before']!r}")
            print(f"    after:  {a['after']!r}")

        if errors:
            print(f"\nABORT: {len(errors)} resolution error(s) — nothing "
                  f"{'written' if args.apply else 'would be written'}. Fix the data "
                  f"or the name sets and re-run.")
            return 2

        if args.apply and actions:
            for a in actions:
                a["row"].formula_expression = a["after"]
            db.commit()

        verb = "GUARDED" if args.apply else "WOULD GUARD"
        print(f"\nSummary: {verb} {len(actions)} row(s) · ALREADY-GUARDED "
              f"{len(already)} · errors 0")
        if not args.apply and actions:
            print("Dry-run only — re-run with --apply to write.")
        if not actions and not already:
            print("NOTE: nothing matched at all — check the template name sets.")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
