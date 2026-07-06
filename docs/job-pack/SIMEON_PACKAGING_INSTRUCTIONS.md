# How to package your Job Pack project and send it for review

**To:** Simeon
**From:** Michael
**Time needed:** about 20–30 minutes
**Why:** so we can back up your work safely and understand how to connect it to the MES — without changing anything about how you work.

---

## 📋 COPY TO SIMEON

Hi Simeon,

We want to protect your Job Pack work (right now it only exists on your laptop) and look at how the MES can link to it. Nothing changes for you — you stay the owner and keep improving it. Could you package a copy for us? Steps below; if anything is unclear, just call me.

**Step 1 — Find your project folder**

Open File Explorer and go to the folder where you run Claude Code for Job Packs. It's the folder you're "in" when you type your instructions. If you're not sure, open Claude Code the way you normally do and ask it:

> "What folder are we in, and what files are in this project? List everything including hidden folders like .claude"

Copy its answer into an email to me — that alone is very useful.

**Step 2 — Check what's inside**

We need the folder to include, if they exist:

- Any file called `CLAUDE.md` (this is important — it holds your instructions)
- The hidden `.claude` folder (it may contain skills and settings)
- Any scripts or files Claude created for you (`.py`, `.bat`, `.txt`, etc.)
- One or two EXAMPLE finished Job Packs (so we can see the output)
- One or two EXAMPLE input documents/drawings for the same job

We do NOT need (leave these out if the zip gets huge):

- Your whole drawings library — just the examples above
- Anything with passwords or API keys in it (tell me if you're unsure)

**Step 3 — Zip it**

1. Right-click the project folder
2. Click: **Send to → Compressed (zipped) folder**
3. Name it: `jobpack-simeon-2026-07-05.zip`

If the zip is bigger than about 100 MB, the drawings examples are probably too large — remove some and re-zip, and just tell me what you removed.

**Step 4 — Send it**

Whichever is easiest:

- Upload to our shared OneDrive/Google Drive and send me the link, or
- Copy to a USB stick and hand it to me, or
- If small enough, email it to micger123@gmail.com

**Step 5 — Three quick answers in the same email**

1. Which Claude Code account/plan do you use on that laptop?
2. Roughly how many Job Packs have you built with it so far?
3. When you build a pack, do you type fresh instructions each time, or re-use saved commands?

That's it. Thanks — this also means if your laptop ever dies, your work is safe.

Michael

---

## Notes for Michael (not part of the copy block)

- When the zip arrives, drop it into the Cowork workspace and a Code Agent will produce the Phase 1 inventory (see investigation report §9, Phase 1).
- Before the repo push (Phase 0): Code Agent to scan for secrets/API keys and write a `.gitignore` first — do not push the raw zip contents blindly.
- If Simeon's answer to Step 1 shows the drawings library is INSIDE the project folder, that changes Phase 2 planning (Q15) — flag it in the Open Questions Register.
