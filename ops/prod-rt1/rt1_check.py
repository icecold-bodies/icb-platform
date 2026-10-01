"""RT1 ruling 3 addendum — READ ONLY checks before F2 and the close (items 1 and 3). One read-only session:

  1. PU foam prices: every material the engine prices as PU foam (name PU / PU FOAM, insulation_foam.py) with its
     price — each must read R4 100 (Burt's corrected 32D) — and every PU foam BOM line on an active body that carries
     its OWN price (it does not follow the material).
  2. The stored 4G factor.
  3. The chillers after Michael's "no PU on any chiller" edit (CHILLER 2.3 METER 25, CHILLER MEDIUM 26, CHILLER LARGE
     27): their insulation / door masters, their PU foam lines, the PU nodes left in their configurator drafts, and a
     dump of their BOM rows (chiller_rows.json, pricing columns only) for the CA's diff against the 09:57 snapshot.
  4. Manifest A's REAR FRAME & FLOOR PLATE rules on every active body: does each condition's option_id still name a
     body-option master of the same body, with that name? (The engine matches conditions by NAME; the Trailer
     Designer's chips use the option_id.)

Selects pricing / configuration columns, the draft payload and its updated_at only — never updated_by or any
customer, contact, user or person column.

    python rt1_check.py <DATABASE_URL> <out-dir>
"""
import json
import re
import sys
from pathlib import Path

import psycopg

PU_FOAM = {"PU", "PU FOAM"}                          # app/services/insulation_foam.py PU_FOAM_MATERIAL_NAMES
CHILLERS = {25: "CHILLER 2.3 METER", 26: "CHILLER MEDIUM", 27: "CHILLER LARGE"}
PU_WORD = re.compile(r"(^|[^A-Z])PU([^A-Z]|$)", re.I)
WANT_32D = 4100.0


def main(url, out_dir):
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("select current_database(), current_setting('default_transaction_read_only')")
        print("database / read only:", cur.fetchone())

        print("\n=== 1. PU FOAM PRICES (the engine's PU foam: material named PU / PU FOAM)")
        cur.execute("""select m.id, m.name, m.price_per_unit, m.last_updated::text,
                              (select count(*) from bill_of_materials b join trailer_types t on t.id = b.trailer_type_id
                               where b.material_id = m.id and coalesce(b.is_body_option, false) = false and t.is_active)
                       from materials m where upper(trim(m.name)) = any(%s) order by m.id""", (list(PU_FOAM),))
        bad = []
        for mid, name, price, upd, n in cur.fetchall():
            ok = price is not None and abs(float(price) - WANT_32D) < 1e-9
            bad += [] if ok else [(mid, name, price)]
            print(f"   material {mid:>5} {name!r:<12} R{price}  (last updated {upd}; {n} line(s) on active bodies)  {'OK' if ok else '!! NOT R4 100'}")
        print(f"   SUMMARY: {'every PU foam material reads R4 100' if not bad else f'NOT R4 100: {bad}'}")
        cur.execute("""select t.name, b.id, b.bom_section, m.name, b.unit_price_override, b.formula_expression
                       from bill_of_materials b join materials m on m.id = b.material_id
                       join trailer_types t on t.id = b.trailer_type_id
                       where upper(trim(m.name)) = any(%s) and coalesce(b.is_body_option, false) = false
                         and t.is_active and b.unit_price_override is not null order by t.name, b.id""", (list(PU_FOAM),))
        own = cur.fetchall()
        print(f"   PU foam lines with their OWN price (they do not follow the material): {len(own)}")
        for body, bid, sec, mat, op, f in own:
            print(f"      {body:<28} bom {bid:>5} {sec or '':<22} own R{op}  | {f}")

        print("\n=== 2. STORED 4G FACTOR:", cur.execute("select value from admin_settings where key = 'costings.pu_foam_4g_factor'").fetchone())

        print("\n=== 3. THE CHILLERS")
        dump = {"bill_of_materials": [], "materials": {}}
        for tid, tname in CHILLERS.items():
            cur.execute("select name, is_active, configurator_v2 from trailer_types where id = %s", (tid,))
            print(f"-- {tid} {tname}: {cur.fetchone()}")
            cur.execute("""select b.id, m.name, b.body_option_group, b.body_option_subgroup, b.variable_value, b.body_option_default
                           from bill_of_materials b join materials m on m.id = b.material_id
                           where b.trailer_type_id = %s and b.is_body_option order by b.body_option_group, m.name""", (tid,))
            ms = cur.fetchall()
            pu_ms = [r for r in ms if PU_WORD.search(r[1] or "")]
            print(f"   body-option masters: {len(ms)}; of them named PU: {len(pu_ms)}")
            for r in ms:
                if (r[2] or "") in ("DRD", "SRD", "DOOR TYPE") or PU_WORD.search(r[1] or "") or (r[1] or "").upper().endswith(" EPS"):
                    print(f"      master {r[0]:>5} {r[1]!r:<14} group {r[2]!s:<10} sub {r[3]!s:<11} thickness {r[4]} default {r[5]}")
            cur.execute("""select b.id, b.bom_section, b.formula_expression, b.unit_price_override, b.bom_conditions
                           from bill_of_materials b join materials m on m.id = b.material_id
                           where b.trailer_type_id = %s and upper(trim(m.name)) = any(%s) and not coalesce(b.is_body_option, false)
                           order by b.bom_section, b.id""", (tid, list(PU_FOAM)))
            lines = cur.fetchall()
            print(f"   PU foam lines: {len(lines)}")
            for r in lines:
                print(f"      bom {r[0]:>5} {r[1]!s:<12} own {r[3]} | {r[2]} | rules {r[4]}")
            cur.execute("select payload, updated_at::text from configurator_drafts where trailer_type_id = %s", (tid,))
            d = cur.fetchone()
            if not d:
                print("   draft: none")
            else:
                payload = json.loads(d[0]) if isinstance(d[0], str) else (d[0] or {})
                nodes = payload.get("nodes") or {}
                hits = []
                for k, n in nodes.items():
                    if not isinstance(n, dict):
                        continue
                    text = " | ".join(f"{a}={v}" for a, v in n.items() if isinstance(v, str) and PU_WORD.search(v))
                    if text:
                        state = {a: n.get(a) for a in ("type", "folderMode", "folderValue", "selectionMode", "selectionValue",
                                                       "hidden", "disabled", "enabled", "value") if a in n}
                        hits.append((k, text, state))
                print(f"   draft saved {d[1]}: {len(nodes)} node(s); nodes that name PU: {len(hits)}")
                for k, text, state in hits[:40]:
                    print(f"      node {k}: {text[:120]} {state}")
            cur.execute("""select b.id, b.trailer_type_id, b.material_id, b.bom_section, b.formula_expression, b.waste_percentage,
                                  b.unit_price_override, b.is_body_option, b.body_option_group, b.body_option_subgroup,
                                  b.body_option_default, b.variable_value, b.bom_conditions, b.selection_mode, b.selection_group,
                                  b.taping_block_id, b.skin_formula_id, b.floor_plate_id, b.mounting_cleat_id
                           from bill_of_materials b where b.trailer_type_id = %s order by b.id""", (tid,))
            cols = [c.name for c in cur.description]
            for r in cur.fetchall():
                dump["bill_of_materials"].append(dict(zip(cols, r)))
        mids = sorted({r["material_id"] for r in dump["bill_of_materials"]})
        cur.execute("select id, name, price_per_unit from materials where id = any(%s)", (mids,))
        dump["materials"] = {str(i): {"name": n, "price_per_unit": p} for i, n, p in cur.fetchall()}
        (out / "chiller_rows.json").write_text(json.dumps(dump, indent=1, default=str), encoding="utf-8")
        print(f"   chiller_rows.json: {len(dump['bill_of_materials'])} BOM rows of the three chillers (pricing columns only)")

        print("\n=== 4. REAR FRAME & FLOOR PLATE RULES -> their masters (every active body)")
        cur.execute("""select b.id, b.trailer_type_id, t.name, m.name, b.bom_conditions
                       from bill_of_materials b join trailer_types t on t.id = b.trailer_type_id
                       join materials m on m.id = b.material_id
                       where t.is_active and b.bom_conditions is not null and b.bom_conditions not in ('', '[]', 'null')
                         and upper(b.bom_section) like 'REAR FRAME%%' order by t.name, b.id""")
        rows = cur.fetchall()
        cur.execute("""select b.id, b.trailer_type_id, m.name, b.is_body_option from bill_of_materials b
                       join materials m on m.id = b.material_id where b.is_body_option""")
        masters = {i: (t, n, o) for i, t, n, o in cur.fetchall()}
        by_body_name = {(t, (n or "").strip().upper()) for t, n, o in masters.values()}
        tally = {}
        for bid, tid, tname, mat, raw in rows:
            try:
                conds = json.loads(raw)
            except ValueError:
                print(f"   !! bom {bid} {tname}: unparseable rule {raw!r}"); continue
            conds = conds if isinstance(conds, list) else (conds.get("all") or [])
            for c in conds:
                oid, opt = c.get("option_id"), (c.get("option") or "")
                m = masters.get(oid)
                if m is None:
                    st = "MISSING (no master with that option_id)"
                elif m[0] != tid:
                    st = f"OTHER BODY ({m[0]})"
                elif (m[1] or "").strip().upper() != opt.strip().upper():
                    st = f"NAME MISMATCH (the master is {m[1]!r})"
                else:
                    st = "OK"
                by_name = (tid, opt.strip().upper()) in by_body_name
                key = (tname, opt, oid, st, by_name)
                tally[key] = tally.get(key, 0) + 1
        for (tname, opt, oid, st, by_name), n in sorted(tally.items()):
            print(f"   {tname:<28} {opt!r:<10} option_id {oid!s:<6} x{n:<2} {st}"
                  + ("" if by_name else "  | !! no master of that NAME on the body (the engine matches by name: always 'N')"))
        problems = sum(n for (t, o, i, st, b), n in tally.items() if st != "OK")
        print(f"   SUMMARY: {len(rows)} rule row(s); {sum(tally.values())} condition(s); {problems} not OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
