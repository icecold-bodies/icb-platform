"""RT4 (RT4_RULING_1 Q3) — what Manifest S needs from deleted id 41, and who else names sections 83/84/85.
READ ONLY (one read-only session, psycopg only — runs over any code).

    python rt4_export41.py <DATABASE_URL> <out-dir>

Writes export41.json + export41.txt:
  * every line of body 41 in sections 83/84/85 (by FK id or by the legacy string): bom id, material, both section
    columns — the 39 lines S re-points to 26/15/21;
  * body 41's draft payload (never updated_by) and the category keys in it; its draft snapshots (count only);
  * EVERY body with a line in 83/84/85 (by id or string) and EVERY draft whose category keys name one of them —
    the window deletes the three sections, so anything else naming them is a STOP (RT4_RULING_1 Q3).
Selects no customer, contact, user or person column.
"""
import json
import sys
from pathlib import Path

import psycopg

BODY = 41
OLD = {83: "DOOR FITTINGS SRD", 84: "DOOR FITTINGS DRD", 85: "REAR FRAME + FLOOR PLATE"}


def main(url: str, out_dir: str) -> int:
    url = url.replace("postgresql+psycopg://", "postgresql://")
    out = Path(out_dir)
    lines, doc = [], {}
    say = lines.append
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as cx:
        cur = cx.cursor()
        cur.execute("select current_database(), current_setting('default_transaction_read_only')")
        db, ro = cur.fetchone()
        if ro != "on":
            raise SystemExit("the session is not read-only")
        say(f"database / read only: {db} / {ro}")
        cur.execute("select id, name from bom_sections where id = any(%s) order by id", (list(OLD),))
        secs = dict(cur.fetchall())
        doc["sections"] = {str(k): v for k, v in secs.items()}
        say(f"sections: {secs}")
        if secs != OLD:
            say(f"⚠ sections differ from the expected {OLD}")
        names = list(OLD.values())
        cur.execute("""select b.id, b.trailer_type_id, t.name, m.name, b.bom_section_id, b.bom_section, b.is_body_option,
                              b.sort_order
                         from bill_of_materials b left join trailer_types t on t.id = b.trailer_type_id
                         left join materials m on m.id = b.material_id
                        where b.bom_section_id = any(%s) or b.bom_section = any(%s)
                        order by b.trailer_type_id, b.bom_section_id, b.sort_order, b.id""", (list(OLD), names))
        rows = [dict(zip(("bom_id", "body_id", "body", "material", "section_id", "section", "is_master", "sort_order"), r))
                for r in cur.fetchall()]
        doc["lines"] = rows
        others = sorted({(r["body_id"], r["body"]) for r in rows if r["body_id"] != BODY}, key=lambda x: x[0] or 0)
        doc["other_bodies"] = [list(o) for o in others]
        say(f"lines in 83/84/85 (by id or string): {len(rows)} — body {BODY}: "
            f"{sum(1 for r in rows if r['body_id'] == BODY)}; other bodies: {others or 'none'}")
        for r in rows:
            flag = "" if OLD.get(r["section_id"]) == r["section"] else "   ⚠ id/string differ"
            say(f"   bom {r['bom_id']:>6} body {r['body_id']} {r['material'] or '?':<36} id {r['section_id']} "
                f"str {r['section']}{flag}")
        cur.execute("select payload, updated_at from configurator_drafts where trailer_type_id = %s", (BODY,))
        d = cur.fetchone()
        doc["draft41"] = {"payload": d[0] if d else None, "updated_at": str(d[1]) if d else None}
        cur.execute("select count(*) from configurator_draft_snapshots where trailer_type_id = %s", (BODY,))
        doc["draft41_snapshots"] = cur.fetchone()[0]
        upper = {n.upper() for n in names}
        naming = []
        cur.execute("select trailer_type_id, payload from configurator_drafts order by trailer_type_id")
        for tid, payload in cur.fetchall():
            try:
                p = json.loads(payload or "{}")
            except (ValueError, TypeError):
                continue
            keys = sorted({(n.get("sourceCategoryKey") or "").strip().upper() for n in (p.get("nodes") or {}).values()
                           if isinstance(n, dict) and n.get("type") == "category"} & upper)
            if keys:
                naming.append({"body_id": tid, "keys": keys})
        doc["drafts_naming_old"] = naming
        say(f"draft 41: {'yes' if d else 'no'}, snapshots {doc['draft41_snapshots']}; "
            f"drafts naming 83/84/85: {naming or 'none'}")
    (out / "export41.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (out / "export41.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
