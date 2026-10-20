"""RT7 — the reboot guard (RT7_DISPATCH default 8, RT7_RULING_1; G1): every prod kit's first line prints the
machine's BOOT TIME (/proc/stat btime), and a kit that sets KIT_DIR REFUSES when it was staged before the last boot
(KIT_DIR/.staged_at, written by the Windows copy line) or was never stamped, or when the boot time cannot be read.
Prod's unplanned reboot on 11 Oct emptied /tmp under RT6's staged kits.

  1. ops/lib/icb_where.sh, run in bash with a stub /proc/stat: pass, refuse (pre-boot, unstamped, no btime), and the
     negative control — a kit WITHOUT KIT_DIR (RT6's) is not checked;
  2. every RT7 kit sets KIT_DIR (or REBOOT_GUARD=1 for the shared All / door kits), and every RT7 copy line stamps the
     kit — and the same scan flags RT6's kits, which predate the guard (the scan proved on a known miss, B3).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from test_ops_rt6 import BASH, OPS, WHERE, needs_bash, posix, run, stub  # noqa: F401  (shared bash helpers)

BOOT = 1792399373            # an arbitrary boot epoch (2026-10-19); the stamps are placed either side of it


def where(tmp_path: Path, *, stamp: int | None, kit_dir: bool = True, btime: bool = True,
          lane: str = "RT7") -> subprocess.CompletedProcess:
    stat = tmp_path / "stat"
    stat.write_text(f"cpu 1 2 3\n{'btime ' + str(BOOT) if btime else 'nothing 0'}\nprocesses 5\n", encoding="utf-8")
    kit = tmp_path / "kit"
    kit.mkdir(exist_ok=True)
    (kit / ".staged_at").unlink(missing_ok=True)
    if stamp is not None:
        (kit / ".staged_at").write_text(f"{stamp}\n", encoding="utf-8")
    exports = f'ICB_PROC_STAT="{posix(stat)}" ICB_LANE={lane}' + (f' KIT_DIR="{posix(kit)}"' if kit_dir else "")
    return run(f'{exports}; . "{posix(WHERE)}"; icb_where "probe" . ""; icb_where_check; '
               'echo "rc=$?"; echo "why=$WHERE_WHY"')


@needs_bash
def test_the_first_line_prints_the_boot_time_and_a_kit_staged_after_it_passes(tmp_path):
    r = where(tmp_path, stamp=BOOT + 3600)
    first = r.stdout.splitlines()[0]
    assert first.startswith("######## RT7 probe · machine "), first
    assert re.search(r" · boot \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+ · ", first), first
    assert "rc=0" in r.stdout, r.stdout + r.stderr


@needs_bash
def test_a_kit_staged_before_the_last_boot_is_refused(tmp_path):
    r = where(tmp_path, stamp=BOOT - 60)
    assert "rc=1" in r.stdout and "WRONG PLACE" in r.stdout and "before this machine's last boot" in r.stdout
    assert "copy it again" in r.stdout and "nothing was run" in r.stdout


@needs_bash
def test_an_unstamped_kit_is_refused(tmp_path):
    r = where(tmp_path, stamp=None)
    assert "rc=1" in r.stdout and "has no staging stamp" in r.stdout


@needs_bash
def test_an_unreadable_boot_time_is_refused(tmp_path):
    r = where(tmp_path, stamp=BOOT + 60, btime=False)
    assert "rc=1" in r.stdout and "the boot time cannot be read" in r.stdout
    assert " · boot ? · " in r.stdout.splitlines()[0]


@needs_bash
def test_negative_control_a_kit_without_kit_dir_is_not_checked(tmp_path):
    # RT6's kits (no KIT_DIR) keep their old behaviour: the stamp is not looked at, so a pre-boot copy passes — which
    # is exactly the hole the guard closes for every RT7 kit
    r = where(tmp_path, stamp=BOOT - 60, kit_dir=False, lane="RT6")
    assert "rc=0" in r.stdout, r.stdout
    assert r.stdout.splitlines()[0].startswith("######## RT6 probe · ")


# ── every RT7 kit carries the guard ─────────────────────────────────────────
RT7_KITS = [OPS / "prod-rt7" / "rt7_discovery.sh", OPS / "prod-rt7" / "rt7_export.sh",
            OPS / "prod-release-v1.61.1" / "release.sh"]
SHARED_KITS = [OPS / "prod-rt2" / "rt2_all.sh", OPS / "prod-rt2" / "rt2_doors.sh"]
RT7_STAGERS = [OPS / "prod-rt7" / "mkstage_window.sh"]
RT7_COPY_LINES = [OPS / "prod-rt7" / "run_discovery.ps1", OPS / "prod-rt7" / "run_export.ps1",
                  OPS / "prod-rt7" / "run_window_copy.ps1"]


def guard_missing(kit: Path) -> bool:
    return not re.search(r"^KIT_DIR=\$BASE\b", kit.read_text(encoding="utf-8"), re.M)


def test_every_rt7_kit_sets_kit_dir_and_every_copy_line_stamps():
    assert [k.name for k in RT7_KITS if guard_missing(k)] == []
    for k in SHARED_KITS:      # the shared All / door kits turn it on for an RT7 staging
        assert 'if [ "${REBOOT_GUARD:-}" = 1 ]; then KIT_DIR=$BASE; ICB_LANE=RT7; fi' in k.read_text(encoding="utf-8"), k
    for s in RT7_STAGERS:
        assert "REBOOT_GUARD=1" in s.read_text(encoding="utf-8"), s
    for ps in RT7_COPY_LINES:
        text = ps.read_text(encoding="utf-8")
        assert "date +%s > .staged_at" in text and "/^btime/" in text, ps   # stamps the kit; prints prod's boot


def test_negative_control_the_scan_flags_rt6_kits_that_predate_the_guard():
    rt6 = [OPS / "prod-rt6" / "rt6_rules.sh", OPS / "prod-release-v1.61.0" / "release.sh"]
    assert all(guard_missing(k) for k in rt6)
