"""RT1 ruling 1 §3 — sweep by mechanism (E3), READ ONLY. Every ACTIVE body on the database, not just the 14:

  1. SWEEP: each BOM line that INHERITS a PU material (no own price), whose formula has NO THICKNESS TERM (no
     `{… PU}` / `{… EPS}` variable: it counts sheets or m²). Since 29 Sep the six shared PU materials hold Burt's 32D
     price per m³ (R4 095), so such a line prices sheets at a cubic-metre price. A "PU material" is any material a PU
     line prices from: the name is PU as a word (PU, PU FOAM, 32D PU, …) — every one found is printed.
     Known hit: before Manifest M the sweep MUST find the 11 MEAT HANGER lines; after M it must find none of them.
  2. Manifest M's lines as they are now (its guards), and 6229 (MEAT HANGER SMALL-MEDIUM FLOOR, own price, out of M),
     plus each MEAT HANGER's insulation masters' thicknesses.
  3. The rear-door masters of CHILLER LARGE and ICECREAM BODY LARGE as they are now (the window's hand fix).
  4. The stored 4G factor (admin_settings costings.pu_foam_4g_factor).
  5. Impact, quote numbers only: saved costings on a body with a swept line, saved on or after 29 Sep, with the saved
     cost of the swept lines.

Selects pricing/config columns and quote numbers only — never a customer, contact, end-user, user or person column.
One read-only session (default_transaction_read_only).

    python rt1_sweep.py <DATABASE_URL>
"""
import json
import re
import sys

import psycopg

M_LINES = {5842, 5851, 5877, 5899, 5910, 5921, 6150, 6159, 6185, 6207, 6218}
OUT_OF_M = 6229
DOOR_BODIES = {27: "CHILLER LARGE", 18: "ICECREAM BODY LARGE"}
PU_WORD = re.compile(r"(^|[^A-Z])PU([^A-Z]|$)", re.I)
THICKNESS = re.compile(r"\{[^}]*\b(PU|EPS)\s*\}", re.I)      # {FRONT PU}, {SRD EPS}, {SIDES PU} …


def main(url):
    url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("select current_database(), current_setting('default_transaction_read_only')")
        print("database / read only:", cur.fetchone())

        # ---- 1. the sweep ----------------------------------------------------------------------------
        cur.execute("SELECT id, name, price_per_unit FROM materials ORDER BY id")
        pu_mats = {i: (n, p) for i, n, p in cur.fetchall() if n and PU_WORD.search(n)}
        print("\n=== 1. SWEEP — PU materials (name has PU as a word):")
        for i, (n, p) in sorted(pu_mats.items()):
            print(f"   material {i:>5} {n!r:<28} R{p}")
        cur.execute("""
            SELECT t.id, t.name, t.configurator_v2, b.id, b.bom_section, b.material_id, b.formula_expression,
                   b.bom_conditions, b.selection_mode
              FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
             WHERE t.is_active AND NOT coalesce(b.is_body_option, false)
               AND b.unit_price_override IS NULL AND b.material_id = ANY(%s)
             ORDER BY t.name, b.bom_section, b.id""", (list(pu_mats),))
        rows = cur.fetchall()
        hits = [r for r in rows if not THICKNESS.search(r[6] or "")]
        print(f"\nlines inheriting a PU material on active bodies: {len(rows)}; of them WITHOUT a thickness term: {len(hits)}")
        print("body | v2 | section | bom | material (price) | formula | conditions")
        for tid, tname, v2, bid, sec, mid, f, cond, mode in hits:
            n, p = pu_mats[mid]
            c = (cond or "")[:70]
            print(f"   {tid:>3} {tname:<28} | {'Y' if v2 else 'N'} | {sec:<24} | {bid:>6} | {mid} {n} R{p} | {f} | {c}")
        found = {r[3] for r in hits}
        m_found = found & M_LINES
        others = sorted(found - M_LINES)
        if m_found == M_LINES:
            print(f"\nKNOWN HIT: all 11 Manifest M lines found (M is not on this database yet)")
        elif not m_found:
            print(f"\nM APPLIED: none of the 11 Manifest M lines is left")
        else:
            print(f"\n!! PARTIAL: {len(m_found)} of the 11 Manifest M lines found: {sorted(m_found)} — tell the CA")
        print(f"SUMMARY: {len(others)} swept line(s) OUTSIDE Manifest M" + (f": {others}" if others else " (expected: none)"))

        # ---- 2. Manifest M's lines now, 6229, and the MEAT HANGER thicknesses ---------------------------
        print("\n=== 2. MANIFEST M LINES AS THEY ARE NOW (the guards) + 6229")
        cur.execute("""SELECT b.id, t.name, b.bom_section, m.id, m.name, m.price_per_unit, b.unit_price_override,
                              b.formula_expression, b.bom_conditions
                         FROM bill_of_materials b JOIN trailer_types t ON t.id = b.trailer_type_id
                         JOIN materials m ON m.id = b.material_id
                        WHERE b.id = ANY(%s) ORDER BY t.name, b.id""", (sorted(M_LINES | {OUT_OF_M}),))
        for bid, tname, sec, mid, mname, mp, own, f, cond in cur.fetchall():
            tag = "OUT OF M" if bid == OUT_OF_M else "M"
            print(f"   {tag:<8} {bid:>5} {tname:<26} {sec:<7} material {mid} {mname} R{mp} | own {own} | {f} | {cond}")
        cur.execute("""SELECT b.trailer_type_id, b.id, m.name, b.variable_value, b.body_option_default
                         FROM bill_of_materials b JOIN materials m ON m.id = b.material_id
                        WHERE b.is_body_option AND b.trailer_type_id IN (12, 36)
                          AND m.name ~ '(EPS|PU)$' ORDER BY 1, 2""")
        print("   MEAT HANGER insulation masters (body, id, name, thickness, default):")
        for r in cur.fetchall():
            print("     ", r)

        # ---- 3. the rear-door masters to fix by hand in the window --------------------------------------
        print("\n=== 3. REAR-DOOR MASTERS NOW (CHILLER LARGE, ICECREAM BODY LARGE)")
        cur.execute("""SELECT b.trailer_type_id, b.id, m.name, coalesce(g.name, b.body_option_group), b.variable_value
                         FROM bill_of_materials b JOIN materials m ON m.id = b.material_id
                         LEFT JOIN body_option_groups g ON g.id = b.body_option_group_id
                        WHERE b.is_body_option AND b.trailer_type_id = ANY(%s)
                          AND coalesce(g.name, b.body_option_group) IN ('DRD', 'SRD', 'DOOR TYPE') ORDER BY 1, 2""",
                    (list(DOOR_BODIES),))
        for tid, mid, name, grp, var in cur.fetchall():
            print(f"   {DOOR_BODIES[tid]:<20} master {mid:>5} {name:<8} group {grp:<9} thickness {var}")

        # ---- 4. the stored 4G factor --------------------------------------------------------------------
        cur.execute("SELECT value FROM admin_settings WHERE key = 'costings.pu_foam_4g_factor'")
        print("\n=== 4. STORED 4G FACTOR:", cur.fetchone())

        # ---- 5. impact: quote numbers only --------------------------------------------------------------
        print("\n=== 5. IMPACT — saved costings on a body with a swept line, saved on/after 29 Sep (quote numbers only;")
        print("    the PU materials moved at 08:12 SAST that day — a quote saved before then shows per-sheet line costs)")
        bodies = sorted({r[0] for r in hits})
        if not bodies:
            print("   (no swept lines: nothing to list)")
            return 0
        cur.execute("""SELECT quote_number, trailer_type_id, created_at, result_json FROM calculations
                        WHERE deleted_at IS NULL AND coalesce(is_repair, false) = false
                          AND trailer_type_id = ANY(%s) AND created_at >= timestamp '2026-09-29 00:00'
                        ORDER BY created_at""", (bodies,))
        n = 0
        for qn, tid, created, rj in cur.fetchall():
            n += 1
            try:
                items = (json.loads(rj) if isinstance(rj, str) else (rj or {})).get("items") or []
            except (ValueError, TypeError):
                items = []
            swept = [(int(it.get("bom_id") or 0), round(float(it.get("line_cost") or 0), 2)) for it in items
                     if int(it.get("bom_id") or 0) in found and not it.get("excluded")]
            print(f"   {qn} | body {tid} | saved {created:%Y-%m-%d %H:%M} | swept lines priced: "
                  f"{sum(c for _, c in swept):,.2f} {swept}")
        print(f"   {n} costing(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
