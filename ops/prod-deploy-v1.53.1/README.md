# WO — v1.53.1 PROD DEPLOY: 04b332f → 94ed70b

**Status:** DRAFT for BA-coordinator / Michael. Scripts simulation-tested and adversarially reviewed; all confirmed findings fixed (§9).

**Why now:** the 14 Sep prod audit (`ops/prod-audit-v1.53.1`, run `20260914-133450`) confirmed that prod serves the #181 shadowing `calculator.js` (sha `5e46664…`). Since 8 Sep that has produced **7 mispriced pending quotes**: 6 over-quoted by R 183–6 112, and **A9992 under-quoted by R 36 532**. This deploy stops new ones. Fixing the 7 existing quotes is a separate remedy WO (§8).

## 1. What lands

| | |
|---|---|
| Prod is at | `04b332f` (detached HEAD). Serves `e5c7837`'s app files, `calculator.js?v=178` |
| Deploy to | **`94ed70b`** — #184 server-side default thicknesses, #185 cache-bust, #186 master-bound flag-shadow fix |
| App files changed | `static/js/calculator.js`, `templates/calculator.html` (`?v=178 → ?v=180`), `templates/admin_visual_configurator_settings.html` (Explorer "Default thickness (m)" field) |
| Also in the range | `backend/tools/set_manni_flag_defaults.py` (used only by the optional §5), two journey tests, docs, screenshots — **27 paths**, pinned in `kit/expected_changes.txt` |
| Python / migration / frontend / deps | **none**, asserted by the change-set guard. Alembic stays `0047`. |
| Restart | **not needed**. Static JS and Jinja templates are read from disk per request, the way v1.46.4 went out. `-Restart` is available; it waits for 4 clean worker boots. |
| Data | **none**. §5 is a separate, deliberate step. |
| Downtime | none (without `-Restart`) |

**Expected after:**
- served `calculator.js?v=180` sha256 = `23f2471931502a40…` on `https://127.0.0.1`, `https://192.168.0.251`, `http://127.0.0.1:8000`, and on the Cloudflare door **after the purge**;
- `_masterBodyVarNameSet` markers = 5; exactly one `calculator.js?v=180` tag in the template.

## 2. How to run (Michael, Windows PC)

```powershell
cd C:\Users\micge\Documents\icb-platform-prod-audit\ops\prod-deploy-v1.53.1
```

| # | Command | Expected |
|---|---|---|
| 1 | `powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action VerifyBaseline` | **Read-only positive control.** Green `completed`, `ALL CHECKS PASSED`: HEAD `04b332f`, served `sha=5e46664…` on the 3 local URLs, alembic `0047`, service active. The Cloudflare door line reads `matches` for `?v=178` (or `WARN … unreachable from the VM`). If this is not green, **do not deploy** — prod differs from the audit. |
| 2 | `powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action Deploy` | Preflight, fetch and guard run, then `PLAN: fast-forward … 04b332f -> 94ed70b` and a prompt — **type `DEPLOY`**. Ends green: `ALL CHECKS PASSED`, `8 DONE`. |
| 3 | **Purge the Cloudflare cache** — dashboard → `mes.icecoldgrp.online` → Caching → Purge Everything | **Mandatory.** Users and old tabs on the domain must not keep an old `calculator.js`. |
| 4 | `powershell -ExecutionPolicy Bypass -File .\run-prod-deploy.ps1 -Action Verify` | Green. Now the Cloudflare door line reads `matches` (or `WARN unreachable from the VM` — then check in a browser, §6). |
| 5 | the click-through, §6 | |
| (opt) | `-Action SeedDryRun`, then `-Action SeedApply` | §5 — only on Michael's or BA's decision |

Add `-User <name>` if you don't log in as `icb`, and `-DryRun` to print the three commands without contacting the VM.

**Prompts:** each action asks for your SSH password 3 times (copy kit, run, fetch log), plus your sudo password on the VM if your account needs one.

**Launcher messages:**
- green `'<Action>' completed` — done. Tell Claude "`<Action>` done"; it reads `.\out\<stamp>-<Action>\`.
- `ssh failed (exit 255)` — nothing ran or nothing was fetched. Run `-Action Verify` (or `VerifyBaseline`) before retrying.
- `did NOT complete` — read the `STOP:` line above it before doing anything else.
- `NOT from this run` — ignore that folder.

### VM-local form (if you are already in a shell on the VM)

First copy the kit from the PC. In **Git Bash**, from this folder, run these two commands. They overwrite the top-level scripts and never nest a `kit/` folder:

```bash
ssh icb@192.168.0.251 mkdir -p icb-deploy-v1531
```

```bash
scp kit/*.sh kit/*.py kit/*.txt icb@192.168.0.251:icb-deploy-v1531/
```

If a script complains about `$'\r'`, run `sed -i 's/\r$//' ~/icb-deploy-v1531/*` on the VM. Then, on the VM:

```bash
bash ~/icb-deploy-v1531/verify.sh baseline
```

```bash
bash ~/icb-deploy-v1531/deploy.sh
```

```bash
bash ~/icb-deploy-v1531/verify.sh target
```

```bash
bash ~/icb-deploy-v1531/rollback.sh
```

```bash
bash ~/icb-deploy-v1531/seed_manni_defaults.sh dry-run
```

`seed_manni_defaults.sh apply` and `seed_manni_defaults.sh restore ~/icb-deploy-v1531/manni_draft_before_<run>.json` work the same way. Each run's log is in `~/icb-deploy-v1531/out-latest/`.

## 3. What `deploy.sh` does, and what to expect

| Step | Action | Expected | If not |
|---|---|---|---|
| 1 preflight | HEAD, local changes (untracked build artefacts ignored, except at paths the release adds), service, alembic — all read-only | `HEAD 04b332f…` · `tracked modifications: 0` · `active since Fri 2026-09-11 06:16:21 SAST` (or later) · `0047 (head)` · served `sha=5e46664…` | STOP, nothing changed. **Already at `94ed70b`:** verification only; with `-Restart` it prints a PLAN and asks you to type `RESTART` first. **Other HEAD:** STOP (prod moved). **Changes are classified by content.** Files already holding their exact `94ed70b` content (left by an interrupted fast-forward, tracked or untracked) → STOP, pointing to `-Action Rollback`, which restores or removes exactly those, then Deploy again. Anything else (a hand edit) → STOP; it is never destroyed. **alembic unreadable** (for example a sudo password typo): its own message; nothing changed. |
| 2 fetch | `git fetch --progress origin` as `icb` | progress lines; `94ed70b fetched, on origin/backport/v1.39-base, fast-forwardable from 04b332f`; 4 commits: `94ed70b`, `41d5986`, `197863f`, `5622a5a` | STOP, nothing changed |
| 3 guard | `04b332f..94ed70b` equals `expected_changes.txt`; no app `.py`, alembic, frontend or requirements paths | `27 paths, exactly as reviewed`, then the 7 non-screenshot paths | STOP, nothing changed |
| 4 confirm | prints PLAN | type `DEPLOY` | STOP, nothing changed |
| 5 fast-forward | `git merge --ff-only 94ed70b` as `icb`; Ctrl-C and hang-up ignored during this command | `HEAD = 94ed70b…` | STOP: run `-Action Verify` to see the state, then `-Action Rollback` |
| 6 restart | only with `-Restart`: restart, wait up to 90 s for 4 `Application startup complete`, 0 `BOOTSTRAP FAILED`, new ActiveEnterTimestamp | `skipped` | See **Step 6 failure** below |
| 7 verify | HEAD; on-disk sha, tag and markers; served sha on 3 URLs; Cloudflare door (probed only now that the disk matches: FAIL if it serves other bytes); health; alembic; service | all `OK`, `ALL CHECKS PASSED`, `service not restarted` | `N CHECK(S) FAILED` → new files are on disk. Read the FAIL lines. A Cloudflare mismatch → purge, then `-Action Verify`. Anything else → `-Action Verify` again, or `-Action Rollback`. |
| 8 record | `~/icb-deploy-v1531/DEPLOYED_94ed70b` naming the verified HEAD, written **only after step 7 passed** (cleared before step 5) | `8 DONE` | — |

**Step 6 failure (only with `-Restart`):** first check whether the app is up, with `sudo systemctl is-active icb-backend` and `https://192.168.0.251/health`.
- Not active: `sudo systemctl start icb-backend`, then read `sudo journalctl -u icb-backend -n 100`.
- `BOOTSTRAP FAILED`: stop and ask the CA before users log in (role grants).
- Once healthy: `-Action Deploy -Restart` again. It is already at the target, so it restarts and re-asserts.

## 4. Rollback — `-Action Rollback`

This is code only; no network or restart. It handles three cases:
- prod at `94ed70b`, clean: the normal case;
- prod at `04b332f` with files left by an interrupted fast-forward (each byte-identical to its `94ed70b` version): it lists them, restores the tracked ones and removes untracked copies of files the release adds, then confirms nothing is left behind;
- already clean at `04b332f`: verify only.

Any change whose content is not the release (a hand edit) is refused and never destroyed. Tracked edits are also saved to `modified_before_rollback.patch` in the run folder; untracked files stay where they are.

**Very unlikely states the kit refuses rather than guesses** (all interruptible git steps ignore Ctrl-C and hang-up):
- A hard kill (`kill -9` or power loss) *while git was writing a file* leaves a truncated release file. Deploy and Rollback both refuse it as "not byte-identical".
- A killed rollback leaves HEAD at `94ed70b` while the files are already `04b332f`. Both scripts refuse it as a hand edit.

In either case, stop and ask the CA. The usual manual recovery is `sudo -u icb git -C /opt/icb-platform checkout --detach -f 04b332f`, then `-Action VerifyBaseline`. Type `ROLLBACK`; it then checks out `04b332f` as `icb` and verifies against the **baseline** (served sha `5e46664…`, `?v=178`, markers 0). Afterwards, purge the Cloudflare cache and hard-reload.

Rolling back the code does **not** undo §5. If you seeded, `-Action SeedRestore` works **before or after** the rollback. The seeded defaults do nothing on `04b332f`, whose calculator never reads them.

## 5. Optional — seed the #184 default thicknesses on prod "Manni RIGIDS CB"

This writes **one database row**: the configurator draft of prod trailer **41**, the active v2 Manni body. Before any step, the helper proves:
- exactly one trailer is named exactly `Manni RIGIDS CB`;
- it is id 41, active and `configurator_v2`, with exactly one draft row.

The inactive classic `MANNI RIGIDS CB` (trailer 3) can never match. Values come from the tool at `94ed70b`: FRONT PU 0.062 · DRD PU 0.038 · SIDES PU 0.038 · ROOF PU 0.038 · FLOOR PU 0.076. SRD PU is deliberately unseeded.

**Effect:** fresh browsers on Manni RIGIDS CB inherit those thicknesses instead of showing "(set thickness)". A browser's own values and explicit zeros still win.

1. **`-Action SeedDryRun`** (needs `94ed70b` and a clean tree, so the tool on disk is the reviewed file) — the session is forced read-only. It lists `+ FRONT PU: None -> 0.062` and so on, and ABORTs if a flag is missing.
2. **`-Action SeedApply`** (needs `94ed70b`) — after the plan, type `SEED`. Then:
   - a fresh `icb-pg-backup` dump (must be newer than 10 minutes);
   - a snapshot of the draft to `~/icb-deploy-v1531/manni_draft_before_<run>.json`;
   - the identity re-checked, then apply;
   - read-only verify that every flag carries its default.
3. **`-Action SeedRestore -RestoreFile ~/icb-deploy-v1531/manni_draft_before_<run>.json`** (works at `94ed70b` or `04b332f`). A read-only check runs **first**: if the restore would be refused, it stops before any prompt or backup. Otherwise type `RESTORE`; it takes a fresh backup, then writes the snapshot back **only if the draft is exactly "snapshot + the seeded defaults"**. Any other change, including an Explorer "Default thickness" edit, makes it refuse and list the differing nodes. It re-reads the row and confirms it equals the snapshot byte for byte.

## 6. Post-deploy (Michael, in a browser on the domain door)

1. After the Cloudflare purge, **hard-reload** (Ctrl+F5).
2. **Check the loaded script:** DevTools → Network → `calculator.js?v=180` is loaded, not `?v=178`.
3. **FREEZER 2.3 METER:** right-click **Rhinotex 1150 BW** (FRONT) and choose *Edit formula*.
   - **Body variables:** one blue set with SIDES PU 0.062 · ROOF EPS 0.076 · FLOOR EPS 0.076. The only teal chips are the kick-plate / ALU-floor names.
   - *Variables in this formula* resolves those values, not 0.000.
   - Cancel — don't Save.
4. **Radio flip:** flip SIDES PU → SIDES EPS and TOTAL COST moves; flip it back.
5. **Manni RIGIDS CB:** behaves as today unless §5 was applied. After §5, a fresh browser shows blue suffixes (0.062 / 0.038 / 0.076).

## 7. CA verification (after Michael says "Deploy done")

- Read `.\out\<stamp>-Deploy\deploy.log`; it ends with `=== deploy COMPLETE … ===`.
- Independently, from Git Bash on this PC: `curl -sk "https://192.168.0.251/static/js/calculator.js?v=180" | tr -d '\r' | sha256sum` must print `23f2471931502a40d0f49dab93dfd0e70b648b7db54ac4335448f39eba4e1bd0`.
- Update the release ledger.

## 8. Not in this deploy — the 7 mispriced pending quotes (separate remedy WO)

Calcs 93, 97–102 (A9985, A9989–A9994/09/2026). Their saved `body_variables` carry the zeros, and **edit mode re-pins saved values by design**, so reopening and saving does NOT fix them. Inside the edit, the insulation pair must be flipped or the thickness re-entered (copy-zero updates the pin), or a new version made. BA to decide per quote. **A9992 (+R 36 532) first**, and confirm whether the 9 Sep 14:17–14:39 burst was real customer work.

## 9. Kit contents and testing

- `run-prod-deploy.ps1` — Windows launcher (pure ASCII; actions VerifyBaseline / Verify / Deploy / Rollback / SeedDryRun / SeedApply / SeedRestore).
- `kit/lib.sh` — pinned SHAs, hashes and tags; helpers; the log is published only after tee has flushed.
- `kit/checks.sh` — read-only verification; the Cloudflare probe is gated.
- `kit/deploy.sh`, `kit/rollback.sh`, `kit/verify.sh` — the actions.
- `kit/seed_manni_defaults.sh` + `kit/manni_draft.py` — §5.
- `kit/expected_changes.txt` — the reviewed 27-path change set; `kit/expected_added.txt` — the 16 paths it adds (used by the interrupted-fast-forward handling).

**Testing:**
- **Simulation** (fake prod clone, static server, fake systemd, `icb_test` for §5) — every path: baseline and target verify, refused confirm, deploy, re-deploy at target, dirty-tree refusal, rollback, change-set guard, wrong HEAD, RUN_ID reuse, `--restart`, and seed dry-run / apply / restore / refusal, with the read-only session proven unable to write.
- **Adversarial review:** 20 findings, all fixed. They include:
  - a pre-deploy Verify that would have cached the OLD bundle at Cloudflare under `?v=180`;
  - a restore guard blind to Explorer default edits;
  - an unrecoverable seed after rollback;
  - `-Restart` being ignored at target;
  - an alembic error misreported as a schema change;
  - the fetched log missing its final banner.
- **Simulation re-run after the fixes** (round 2): every requested scenario passed, plus new ones: Cloudflare gating against a separate edge server, a stale and an unreachable edge, restart at target, interrupted fast-forward, record semantics, the log banner, seed identity, the restore guard against Explorer edits, and restore after rollback. It exposed one more defect: untracked files the release adds could survive a rollback and loop. Content-based classification now fixes it, and round 3 re-verified the final kit.

## OUTCOME — deployed 14 Sep 2026 15:59:51 SAST, all checks green

| Step | Result |
|---|---|
| VerifyBaseline (15:44) | ALL CHECKS PASSED — HEAD `04b332f`; `5e46664…` served on all 3 local URLs and on Cloudflare `?v=178`; alembic `0047`; service active since Fri 11 Sep 06:16 |
| Deploy run `20260914-155933` | Preflight clean → fetch: `04b332f..94ed70b` (4 commits) → guard: 27 paths exactly as reviewed → `DEPLOY` typed → ff-only `Updating 04b332f..94ed70b`, 27 files → no restart → ALL CHECKS PASSED → record `head=94ed70b… from=04b332f… restart=0` |
| Served after | `calculator.js?v=180` sha `23f2471931502a40…`, 526 535 bytes, `_masterBodyVarNameSet` = 5, on `https://127.0.0.1`, `https://192.168.0.251`, `http://127.0.0.1:8000` and the Cloudflare door |
| Verify run `20260914-160016` | ALL CHECKS PASSED; deploy record matches HEAD |
| CA check from the Windows PC (16:4x) | LAN `https://192.168.0.251/…?v=180` and domain `https://mes.icecoldgrp.online/…?v=180` both `sha=23f2471931502a40`, domain `cf-cache-status: HIT` (edge holds the NEW bundle); `/health` `{"status":"ok"}` |
| Schema / service | alembic `0047` before and after; service not restarted (still since Fri 11 Sep 06:16:21) — zero downtime |

**Still open:**
- Browser click-through on the domain (§6).
- Optional §5 Manni seeding — Michael's decision.
- The 7 mispriced pending quotes (§8) — remedy WO.
