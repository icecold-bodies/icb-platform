"""RT7 (RT7_RULING_1A) — the golden's workbook set for Burt's 19 Oct price list: RT2's corrected set + PU!C19.

    python build_c3_set.py <rt2 corrected-set dir> <19 Oct PRICE 2017 MARCH.xlsx> <rt2 corrections.json> <out-dir>

Writes, OUTSIDE git (Burt's files never enter the repo — H1):

    <out>/corrected/     GRP  = RT2's corrected GRP with its link cache resolved to the 19 Oct price list
                         PRICE = Burt's 19 Oct price list, byte for byte (saved 19 Oct 07:43 UTC)
                         FORMULAS = Burt's 21 Sep member, unchanged
    <out>/corrections.json   RT2's provenance + correction 3 + every file's sha256

Why the cache: LibreOffice headless prices every [1] reference from the GRP's OWN cache of the price list
(externalLink1.xml) and never reads the adjacent PRICE file (proven in RT2). "The external link resolved to that
file" therefore means: every cached [1] cell takes the 19 Oct file's value.

Guarded — every check refuses the whole build:
  * the RT2 set is byte-identical to the one the committed golden was built on (its manifest's sha256s);
  * the 19 Oct price list is the file Michael saved (sha256 below), and differs from RT2's corrected price list
    ONLY in PU!C18, PU!C19 and PU!C20 (anything else is a STOP for the BA);
  * of those, the GRP caches only PU!C19, and its cached value is exactly '5581' (F2's 4G rate) -> '5400';
  * the resulting GRP differs from RT2's in exactly that one cached value — no worksheet cell, no other cache cell.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rt2_2026-10" / "golden"))
from build_corrected_set import (FORMULAS, GRP, PRICE, diff_cells, diff_link_cache, price_link_part, rezip,  # noqa: E402
                                 sha)

RT2_CORRECTED = {GRP: "04c774e2a7de631458a67fb9e01663973ae20a621b58157cdeb63d0ef59e70bb",
                 PRICE: "b85f25aefcdffcfc6cef7df3ecf886532be304c6a2fe9de4b6a4d1f32f5cc75e",
                 FORMULAS: "f90db787b47a2f81763a5518fa2e0c1ddbbb4c502b2f828861283aa50e1e2f3f"}
PRICE_19OCT = "088f43dc74bbce098d0afd3344415f95a515595374c576ae1a0075783d973500"
EXPECTED_PRICE_DIFF = {"formula PU!C18: 4358 -> 4590", "value PU!C18: 4358 -> 4590",
                       "formula PU!C19: 5581 -> 5400", "value PU!C19: 5581 -> 5400",
                       "formula PU!C20: 10232 -> 8000", "value PU!C20: 10232 -> 8000"}
C3 = {"file": PRICE, "sheet": "PU", "cell": "C19", "from": "5581", "to": "5400", "what": "4G FOAM sheet price",
      "authority": "Burt's price list PRICE 2017 MARCH.xlsx saved 19 Oct 2026 07:43 UTC (09:43 SAST), PU!C19 4G FOAM "
                   "R5 581 -> R5 400; prod's 4G factor set to 5400/4100 by Michael on 19 Oct (RT7_RULING_1A)"}


def cache_cells(grp: bytes, part: str) -> dict[str, str]:
    xml = zipfile.ZipFile(io.BytesIO(grp)).read(part).decode("utf-8")
    names = re.findall(r'<sheetName val="([^"]+)"', xml)
    out = {}
    for sid, body in re.findall(r'<sheetData sheetId="(\d+)"[^>/]*>(.*?)</sheetData>', xml, re.S):
        for r, v in re.findall(r'<cell r="([A-Z]+[0-9]+)"[^>]*>\s*<v>([^<]*)</v>', body):
            out[f"{names[int(sid)]}!{r}"] = v
    return out


def patch_c3_cache(grp: bytes) -> tuple[bytes, str]:
    part = price_link_part(grp)
    xml = zipfile.ZipFile(io.BytesIO(grp)).read(part).decode("utf-8")
    sid = re.findall(r'<sheetName val="([^"]+)"', xml).index(C3["sheet"])
    m = re.search(rf'<sheetData sheetId="{sid}"[^>]*>(.*?)</sheetData>', xml, re.S)
    if not m:
        raise SystemExit(f"REFUSED: {part} caches nothing for sheet {C3['sheet']!r}")
    old = re.findall(rf'<cell r="{C3["cell"]}"(?: [^>]*)?><v>{C3["from"]}</v></cell>', m.group(1))
    if len(old) != 1:
        raise SystemExit(f"REFUSED: the cached {C3['sheet']}!{C3['cell']} in {part} is not exactly {C3['from']}")
    body = m.group(1).replace(old[0], old[0].replace(f"<v>{C3['from']}</v>", f"<v>{C3['to']}</v>"))
    return rezip(grp, {part: (xml[:m.start(1)] + body + xml[m.end(1):]).encode("utf-8")}), part


def main(rt2_dir: str, price_19oct: str, rt2_prov: str, out_dir: str) -> None:
    src = {n: (Path(rt2_dir) / n).read_bytes() for n in (GRP, PRICE, FORMULAS)}
    for n, want in RT2_CORRECTED.items():
        if sha(src[n]) != want:
            raise SystemExit(f"REFUSED: {rt2_dir}/{n} sha256 {sha(src[n])} is not RT2's corrected {want}")
    price = Path(price_19oct).read_bytes()
    if sha(price) != PRICE_19OCT:
        raise SystemExit(f"REFUSED: {price_19oct} sha256 {sha(price)} is not the 19 Oct price list {PRICE_19OCT}")

    dprice = diff_cells(src[PRICE], price)
    print("== the 19 Oct price list against RT2's corrected one — every cell that differs:")
    print("\n".join(f"   {x}" for x in dprice))
    if set(dprice) != EXPECTED_PRICE_DIFF:
        raise SystemExit(f"STOP: the price list moved in more (or other) cells than PU!C18/C19/C20: "
                         f"{sorted(set(dprice) ^ EXPECTED_PRICE_DIFF)}")
    part = price_link_part(src[GRP])
    cached = cache_cells(src[GRP], part)
    moved = sorted({x.split(" ", 1)[1].split(":")[0] for x in dprice})
    referenced = [c for c in moved if c in cached]
    print(f"== the GRP caches {len(cached)} cells of the price list ({part}); of the moved cells it references: "
          f"{referenced}; not referenced (cannot reach the golden): {[c for c in moved if c not in cached]}")
    if referenced != ["PU!C19"]:
        raise SystemExit(f"STOP: the GRP references {referenced} of the moved cells, not exactly PU!C19")

    grp3, part = patch_c3_cache(src[GRP])
    dgrp = diff_cells(src[GRP], grp3) + diff_link_cache(src[GRP], grp3)
    print("== the GRP, RT2's -> resolved to the 19 Oct price list — every worksheet cell and cached value that differs:")
    print("\n".join(f"   {x}" for x in dgrp))
    want = {f"cache {part.rsplit('/', 1)[-1]} PU!C19: '5581' -> '5400'"}
    if set(dgrp) != want:
        raise SystemExit(f"REFUSED: the GRP changed more (or less) than its cached PU!C19: {dgrp}")

    out = Path(out_dir) / "corrected"
    out.mkdir(parents=True, exist_ok=True)
    files = {GRP: grp3, PRICE: price, FORMULAS: src[FORMULAS]}
    for n, data in files.items():
        (out / n).write_bytes(data)
    prov = json.loads(Path(rt2_prov).read_text(encoding="utf-8"))
    prov["files"]["rt2_corrected"] = prov["files"].pop("corrected")
    prov["corrections"].append(dict(C3, id=3, cells_changed=dprice + dgrp,
                                    applied_to=[f"{PRICE}: Burt's 19 Oct file, byte for byte (sha256 {PRICE_19OCT})",
                                                f"{GRP} {part} cached [1]PU!C19"],
                                    not_in_the_golden="PU!C18 4358 -> 4590 and PU!C20 10232 -> 8000 moved in the price "
                                                      "list too; the GRP references neither (not in its link cache), so "
                                                      "they cannot reach the golden"))
    prov["files"]["corrected"] = {n: sha(d) for n, d in files.items()}
    prov["rt7"] = {"ruling": "RT7_RULING_1A (19 Oct 2026): the golden is regenerated for exactly the 4G change",
                   "price_list_19oct_sha256": PRICE_19OCT}
    (Path(out_dir) / "corrections.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print(f"== wrote {out} and corrections.json")
    print("   corrected  " + " · ".join(f"{n.split()[0]} {sha(d)[:12]}" for n, d in files.items()))


if __name__ == "__main__":
    main(*sys.argv[1:])
