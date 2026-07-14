# Installation Guide — Reliability Harness v2 in MiniMax Code

Complete walkthrough to install the Reliability Harness v2 (formerly Fable-Mythos-Modus + MAP) in MiniMax Code.

## Prerequisites

- **[MiniMax Code](https://minimax.io)** installed and running
- **minimax m3-pro** as the configured model (default model is `minimax/MiniMax-M3`; see `~/.minimax/config.yaml` for available models)
- (Windows) **Git Bash** or equivalent Unix-like shell — PowerShell works but path syntax differs
- Python 3.x reachable as `python`, `python3`, `py`, or `/c/Python313/python.exe` (used by `scripts/deploy_subagents.py`)

## Overview

You will install three things:

1. **`AGENTS.md`** — the system prompt (user-level, applies globally)
2. **`fable-mythos-modus/SKILL.md`** — the behavioral priming skill
3. **11 sub-agents** (5 legacy + 6 new orthogonal reliability agents) — installed via **direct-to-disk drop** (one `agent.md` per agent in `~/.minimax/agents/<name>/`). This bypasses the MiniMax Code UI's "New Subagent" form, which limits `description` to 100 chars and exposes no system-prompt field.

Time required: ~10 seconds (`bash install.sh`). All 11 sub-agents + the system prompt + the skill land in one shot. The system-prompt and skill blocks install idempotently; the agent drop is also idempotent (existing agent directories are skipped).

---

## Step 1: Install the System Prompt (`AGENTS.md`)

The `AGENTS.md` is the central system prompt file that MiniMax Code loads in every session. It contains:

- The 8 hard rules (Evaluation Blindness, Auditability, task-specific authorization, Anti-Concealment, Anti-Reward-Hacking, Anti-Sycophancy, Least Privilege, distrust-by-default)
- The compact 14-point Runtime-Core
- The Sub-Agent Permission Table (Least Privilege)
- The Executor-Standard (mandatory self-verification)
- The Deterministic Done-Gate (Phase 5)
- Dynamic Routing by `risk_tier`

### Action (idempotent via managed-block markers)

The **entire body** of this repo's `AGENTS.md` is wrapped between managed-block markers (`<!-- reliability-harness:start -->` … `<!-- reliability-harness:end -->`). The installer merges ONLY that block into your `~/.minimax/AGENTS.md`, preserving any personal instructions you keep outside the markers. Re-running it never duplicates content.

```bash
# All platforms (Git Bash / macOS / Linux). Requires awk (preinstalled on macOS/Linux; ships with Git Bash on Windows).
mkdir -p ~/.minimax

SRC=AGENTS.md            # this repo's file
DST=~/.minimax/AGENTS.md   # your user-level MiniMax Code system prompt

# Back up an existing file the first time.
[ -f "$DST" ] && [ ! -f "$DST.backup" ] && cp "$DST" "$DST.backup"

# Idempotent marker-aware merge: replace only the managed block in $DST
# (creates $DST with the block if it does not exist yet).
awk -v src="$SRC" '
  BEGIN { while ((getline line < src) > 0) srcLines[++n] = line; inSrcBlock=0; started=0; sawSrcStart=0 }
  /^<!-- reliability-harness:start -->$/ {
    started=1; print; inSrcBlock=1
    for (i=1; i<=n; i++) {
      if (srcLines[i] ~ /^<!-- reliability-harness:start -->$/) { sawSrcStart=1; continue }
      if (srcLines[i] ~ /^<!-- reliability-harness:end -->$/)   { break }
      if (sawSrcStart) print srcLines[i]
    }
    next
  }
  /^<!-- reliability-harness:end -->$/ { if (started) { print; inSrcBlock=0; next } }
  { if (!inSrcBlock) print }
' "$DST" 2>/dev/null > "$DST.tmp" || true

# If DST did not exist yet, the awk above produced nothing — seed it with the block.
if [ ! -s "$DST.tmp" ]; then cp "$SRC" "$DST.tmp"; fi
mv "$DST.tmp" "$DST"
echo "Merged managed block into $DST."
```

**Windows explicit path:** `C:\Users\<<YOUR_USER>\.minimax\AGENTS.md`

**Why not plain `cp`?** A bare `cp AGENTS.md ~/.minimax/AGENTS.md` overwrites the whole file and destroys any personal instructions you keep there. The marker-aware merge above only touches the harness block.

**Verify the markers are present and well-formed** after install:

```bash
grep -c "reliability-harness:\(start\|end\)" ~/.minimax/AGENTS.md   # expect: 2
```

---

## Step 2: Install the Mythos Skill

```bash
# Create the skill directory
mkdir -p ~/.minimax/skills/fable-mythos-modus

# Copy the skill
cp fable-mythos-modus/SKILL.md ~/.minimax/skills/fable-mythos-modus/SKILL.md

# Optional: agent-framework compatibility
mkdir -p ~/.agents/skills/fable-mythos-modus
cp fable-mythos-modus/SKILL.md ~/.agents/skills/fable-mythos-modus/SKILL.md
```

### Verify

Check the frontmatter is intact:

```bash
head -4 ~/.minimax/skills/fable-mythos-modus/SKILL.md
```

Expected output:

```
---
name: fable-mythos-modus
description: Reliability-First-Modus für minimax m3-pro. Strikte Anwendung von Task Contract, ...
---
```

The folder name (`fable-mythos-modus`) must exactly match the `name:` field. If they don't match, the skill won't be discovered.

---

## Step 3: Install Sub-Agents via Direct-to-Disk Drop

The MiniMax Code UI's "Settings → Subagents → New" form only exposes `Name`,
`Description` (≤100 chars), and `Default working folder` — no system-prompt
field. That's a UI limitation, not a Mavis limitation. Custom Subagents are
loaded from `<dataDir>/agents/<name>/agent.md` (see the built-in
`~/.minimax/.builtin-skills/create-agent/SKILL.md`), and the system prompt is
the **Markdown body** of `agent.md`, which can be arbitrarily long.

This step drops all 11 sub-agents into `~/.minimax/agents/<name>/` directly.

```bash
# default: installs to ~/.mavis/agents/ (which symlinks to ~/.minimax/agents/ on
# your machine). Override with MAVIS_DATA_DIR=<path> if needed.
bash install.sh
```

What `install.sh` does:

1. Resolves `<dataDir>` (defaults to `~/.mavis/`, with symlink fallback to
   `~/.minimax/` on Windows). Override with `MAVIS_DATA_DIR=/some/path bash install.sh`.
2. Creates `<dataDir>/agents/<name>/agent.md` per sub-agent.
   - `agent.md` has YAML frontmatter (`name: <name>` + `description: >- <one-line description>`)
   - The Markdown body **IS** the full system prompt (no length cap).
3. Creates `<dataDir>/agents/<name>/config.yaml` as `{}` (uses platform default
   model; edit this file later to pin a specific `model:`).
4. Skips any agent directory that already exists (idempotent reinstall safe).

After `install.sh` finishes, **restart MiniMax Code** (or use Settings → Subagents
→ Reload if available). All 11 agents should appear in the Sub-Agent list,
alongside the four built-ins (`coder`, `general`, `mavis`, `verifier`).

### Verify

```bash
ls ~/.minimax/agents/   # should list: coder general mavis verifier + 11 new dirs
cat ~/.minimax/agents/rel-lead/agent.md  # name: rel-lead, body = full prompt
```

### Uninstall

```bash
bash install.sh --uninstall
```

Removes all 11 fable-mythos agent directories; built-ins stay untouched.

### Per-agent `config.yaml` (optional tweaks)

By default `config.yaml` is `{}`, which inherits the user's default model
(usually `minimax/MiniMax-M3`). To pin a specific model for one role:

```yaml
# ~/.minimax/agents/rel-verifier/config.yaml
model: minimax/MiniMax-M2.7-highspeed
thinking:
  effort: low
```

Schema is shared with the platform's Mavis/OpenCode provider definition
(see `~/.minimax/config.yaml` for the model list and capabilities).

### Why the names look different in the Sub-Agent list

The agent **directory names** follow the file labels in `sub-agents/*.md`
(e.g. `0-mythos-singleshot-thinking-intelligence.md`) which keep git-history
continuity with `fable-mythos-zcode`. The agent **names** (used by the
orchestrator) are the kebab-case `name:` fields from the YAML frontmatter —
the canonical short names that fit MiniMax Code's 20-character cap:

```
mythos-thinker        mythos-executor        mythos-verifier
mythos-adversary      mythos-synthesizer
rel-scout             rel-critic             rel-test-des
rel-lead              rel-verifier           rel-adversary
```

`install.sh` writes the `name:` exactly as above; the orchestrator sees these
short names, not the file labels.
