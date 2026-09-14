#!/usr/bin/env python3
"""Helper for seed_manni_defaults.sh - identity check / inspect / snapshot / restore of the
prod "Manni RIGIDS CB" configurator draft that tools/set_manni_flag_defaults.py (#184) seeds.

  check    --tid N                 read-only: EXACTLY one trailer carries the tool's trailer
                                   name, it is id N, active and configurator_v2, with a draft
  show     --tid N [--expect] [--snapshot F]
                                   read-only: flagVarDefault on the seeded flag names
                                   (--expect: exit 1 unless every one equals the defaults)
  dump     --tid N OUT.json        read-only: snapshot = trailer id/name, draft id, raw payload,
                                   AND the tool's name + DEFAULTS (so restore never needs the tool)
  restore  --tid N IN.json         WRITE: put the snapshot payload back - refused unless the
                                   draft now equals (snapshot + exactly the seeded defaults)

Names/values come from the tool when it exists (94ed70b) or from the snapshot (any version).
Run from backend/ with the app env loaded (the wrapper does this).
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys


def _tool():
    path = os.path.join(os.getcwd(), "tools", "set_manni_flag_defaults.py")
    if not os.path.exists(path):
        return None, None
    spec = importlib.util.spec_from_file_location("set_manni_flag_defaults", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TRAILER_NAME, dict(mod.DEFAULTS)


def _unique_trailer(db, name, tid):
    from app.database import ConfiguratorDraft, TrailerType
    rows = db.query(TrailerType).filter(TrailerType.name == name).all()
    if len(rows) != 1:
        raise SystemExit(f"ABORT: {len(rows)} trailers are named exactly {name!r} (need exactly 1) - nothing done")
    t = rows[0]
    if t.id != tid:
        raise SystemExit(f"ABORT: the {name!r} trailer is id {t.id}, not the expected {tid} - nothing done")
    if not t.is_active or not getattr(t, "configurator_v2", False):
        raise SystemExit(f"ABORT: trailer {t.id} is_active={t.is_active} configurator_v2={getattr(t, 'configurator_v2', None)} (need both true) - nothing done")
    drafts = db.query(ConfiguratorDraft).filter(ConfiguratorDraft.trailer_type_id == t.id).all()
    if len(drafts) != 1 or not drafts[0].payload:
        raise SystemExit(f"ABORT: trailer {t.id} has {len(drafts)} draft row(s) with payload - need exactly 1 - nothing done")
    return t, drafts[0]


def _seeded_nodes(payload: dict, names) -> dict:
    """Same selection rule as the tool: first flag node per stripped (flagBindingName or label)."""
    out = {}
    for node in (payload.get("nodes") or {}).values():
        if isinstance(node, dict) and node.get("type") == "flag":
            nm = (node.get("flagBindingName") or node.get("label") or "").strip()
            if nm in names and nm not in out:
                out[nm] = node
    return out


def _with_defaults(payload: dict, defaults: dict) -> dict:
    p = copy.deepcopy(payload)
    for nm, node in _seeded_nodes(p, defaults).items():
        node["flagVarDefault"] = defaults[nm]
    return p


def _diff_nodes(a: dict, b: dict) -> list:
    na, nb = a.get("nodes") or {}, b.get("nodes") or {}
    out = [k for k in sorted(set(na) | set(nb)) if na.get(k) != nb.get(k)]
    if {k: v for k, v in a.items() if k != "nodes"} != {k: v for k, v in b.items() if k != "nodes"}:
        out.append("<top-level keys>")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "show", "dump", "restore"):
        sp = sub.add_parser(name)
        sp.add_argument("--tid", type=int, required=True)
        if name == "show":
            sp.add_argument("--expect", action="store_true")
            sp.add_argument("--snapshot", default="")
        if name in ("dump", "restore"):
            sp.add_argument("path")
        if name == "restore":
            sp.add_argument("--check", action="store_true", help="run the guard only; never write")
    args = ap.parse_args()

    sys.path.insert(0, os.getcwd())
    from app.database import SessionLocal

    snap = None
    if args.cmd == "restore" or (args.cmd == "show" and args.snapshot):
        with open(args.path if args.cmd == "restore" else args.snapshot, encoding="utf-8") as f:
            snap = json.load(f)
    tool_name, tool_defaults = _tool()
    trailer_name = snap["tool_trailer_name"] if snap else tool_name
    defaults = snap["defaults"] if snap else tool_defaults
    if not trailer_name or not defaults:
        print("ABORT: tools/set_manni_flag_defaults.py not present and no snapshot given - nothing done")
        return 2

    with SessionLocal() as db:
        trailer, draft = _unique_trailer(db, trailer_name, args.tid)
        payload = json.loads(draft.payload)

        if args.cmd == "check":
            print(f"OK trailer {trailer.id} {trailer.name!r} active v2, draft {draft.id} ({len(draft.payload)} chars)")
            db.rollback()
            return 0

        if args.cmd == "show":
            nodes = _seeded_nodes(payload, defaults)
            print(f"trailer {trailer.id} {trailer.name!r} draft {draft.id} updated_at {draft.updated_at}")
            bad = 0
            for nm in sorted(defaults):
                cur = nodes[nm].get("flagVarDefault") if nm in nodes else "<flag missing>"
                match = isinstance(cur, (int, float)) and abs(float(cur) - float(defaults[nm])) < 1e-12
                print(f"  {nm:10} flagVarDefault={cur!r:<12} default={defaults[nm]}  {'OK' if match else '--'}")
                bad += 0 if match else 1
            db.rollback()
            if args.expect and bad:
                print(f"EXPECTATION FAILED: {bad} flag(s) do not carry the default")
                return 1
            return 0

        if args.cmd == "dump":
            out = {"trailer_id": trailer.id, "trailer_name": trailer.name, "draft_id": draft.id,
                   "updated_at": str(draft.updated_at), "payload": draft.payload,
                   "tool_trailer_name": tool_name, "defaults": tool_defaults}
            with open(args.path, "w", encoding="utf-8") as f:
                json.dump(out, f)
            db.rollback()
            print(f"saved draft {draft.id} of trailer {trailer.id} ({len(draft.payload)} chars) -> {args.path}")
            return 0

        # restore
        if snap.get("trailer_id") != trailer.id or snap.get("draft_id") != draft.id:
            print("ABORT: the snapshot is for a different trailer/draft row - nothing written")
            return 2
        saved = json.loads(snap["payload"])
        if payload == saved:
            print("Nothing to do - the draft already equals the snapshot.")
            return 3 if args.check else 0
        expected_now = _with_defaults(saved, defaults)
        if payload != expected_now:
            print("ABORT: the draft is not exactly 'snapshot + the seeded defaults' - something else changed since the snapshot")
            print("       (an Explorer edit, including a Default thickness change). Differing nodes: " + ", ".join(_diff_nodes(expected_now, payload)))
            print("       Nothing written. Resolve by hand in the Explorer, or take a DB-level decision.")
            return 2
        if args.check:
            db.rollback()
            print("CHECK OK: the draft is exactly 'snapshot + the seeded defaults' - a restore would be accepted (nothing written)")
            return 0
        draft.payload = snap["payload"]
        db.commit()
    with SessionLocal() as db2:                      # re-read in a fresh session
        _t, d2 = _unique_trailer(db2, trailer_name, args.tid)
        if d2.payload != snap["payload"]:
            print("ERROR: after commit the draft payload does NOT equal the snapshot - investigate")
            return 1
        db2.rollback()
    print(f"RESTORED draft {snap['draft_id']} of trailer {snap['trailer_id']}; re-read equals the snapshot byte for byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
