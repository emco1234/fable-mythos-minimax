# Installation Guide — Reliability Harness v2 in MiniMax Code

Complete walkthrough to install the Reliability Harness v2 (formerly Fable-Mythos-Modus + MAP) in MiniMax Code.

## Prerequisites

- **[MiniMax Code](https://minimax.io)** installed and **running** (the Mavis daemon must be alive so the installer can reach it via HTTP)
- **`minimax/MiniMax-M3`** (default) or any of `MiniMax-M2.7`, `MiniMax-M2.7-highspeed` (configured in `~/.minimax/config.yaml`)
- (Windows) **Git Bash** or equivalent Unix-like shell
- Python 3.x reachable as `python`, `python3`, `py`, or `/c/Python313/python.exe` (used by `scripts/deploy_subagents_http.py`)

## Overview

You will install three things:

1. **`AGENTS.md`** — the system prompt (user-level, applies globally)
2. **`fable-mythos-modus/SKILL.md`** — the behavioral priming skill
3. **11 sub-agents** (5 legacy + 6 new orthogonal reliability agents) — installed via **direct HTTP call to the Mavis daemon** (one `POST` per agent to the Thrift-gen endpoint `POST /minimax-desktop/api/v1/agent`). This bypasses the MiniMax Code UI's "New Subagent" form, which limits `description` to 100 chars and exposes no system-prompt field.

Time required: ~10 seconds (`bash install.sh`). The system-prompt and skill install idempotently; the agent deploy is also idempotent (existing agent names return a 409 conflict and are skipped).

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

## Step 3: Install Sub-Agents via the Mavis Daemon HTTP API

The MiniMax Code UI's "Settings → Subagents → New" form only exposes `Name` (≤20 chars), `Description` (≤100 chars), and `Default working folder` — **no system-prompt field at all**. That's a UI limitation, not a Mavis limitation.

The Mavis daemon exposes a richer endpoint at `POST /minimax-desktop/api/v1/agent` (auto-generated from the Thrift IDL by `@mavis/thrift-gen`). That endpoint accepts:

| Field              | Type   | Notes                                          |
|--------------------|--------|------------------------------------------------|
| `name`             | string | kebab-case, ≤20 chars, `^[a-z][a-z0-9_-]*$`     |
| `displayName`      | string | shown in the Sub-Agent list                    |
| `description`      | string | no 100-char limit (GUI cap does not apply)     |
| `systemPrompt`     | string | full multi-KB prompt — no length cap           |
| `persona`          | string | optional                                       |
| `avatar`           | string | optional URL                                   |
| `defaultWorkspaceDir` | string | optional                                       |

This installer POSTs each agent's `name`, `displayName`, `description`, and full `systemPrompt` directly to the daemon. The daemon persists them to the `agents` SQLite table and to `<dataDir>/agents/<name>/agent.md` as an overlay.

### Action

```bash
bash install.sh
```

What `install.sh` does:

1. Auto-discovers the daemon port by scanning `~/.minimax/logs/daemon-*.log` for `Mavis Daemon started port=NNNNN` (last 5 logs).
2. Falls back to probing `127.0.0.1:15321` (default release port).
3. Loads the bearer token from `~/.minimax/local-runtime.auth.json`.
4. For each `sub-agents/*.md`, parses the `## Feld: Name / Description / System prompt` blocks and POSTs:
   ```json
   {
     "name":         "rel-lead",
     "displayName":  "rel-lead",
     "description":  "Lead-Engineer für complex/critical-Tasks...",
     "systemPrompt": "<full multi-KB prompt>"
   }
   ```
5. After all 11 posts, queries the `agents` table from `~/.minimax/sqlite.db` and prints the new rows for visual confirmation.

The installer exits non-zero if the daemon is unreachable. Open MiniMax Code to start the daemon, then re-run.

### Disk-drop fallback (`--disk`)

If the daemon is offline (you launched a fresh shell before opening MiniMax Code, or you're running this in CI), use the prior direct-to-disk fallback. It writes `<dataDir>/agents/<name>/agent.md` files but the daemon only re-reads them at next boot, so restart MiniMax Code afterwards:

```bash
bash install.sh --disk
```

### Dry-run (`--dry-run`)

Parse + validate the 11 source files without touching the filesystem or the network. Useful in CI to assert the source files are still well-formed:

```bash
bash install.sh --dry-run
```

### Explicit port (`--port`)

If auto-discovery picks the wrong log (e.g. you ran a debug build of the daemon), pass the port directly:

```bash
bash install.sh --port 15321
```

### Verify (post-install)

The installer prints the agent table after deploying. You can also re-run:

```bash
python scripts/verify_live_load.py after
```

The `verify_live_load.py` helper snapshots the `agents` table to `~/.minimax/.fable-mythos/agents-after.txt` and prints a diff against the `before` snapshot. If the `delta >= 11`, Mavis picked up all 11 new agents.

### Uninstall

```bash
bash install.sh --uninstall
```

Removes the `<dataDir>/agents/<name>/` directories for all 11 fable-mythos agents. **Note**: the HTTP path only deletes the on-disk files (the agents row in SQLite is left as a soft-delete marker). For a hard-delete via the daemon API, run `DELETE /minimax-desktop/api/v1/agent/<name>` per agent in MiniMax Code's debug console, or send a follow-up PR — this installer intentionally keeps the simple disk-based uninstall to avoid touching the daemon's DELETE endpoint without explicit user confirmation.

### Per-agent `config.yaml` (optional tweaks)

By default the daemon uses the user's default model (usually `minimax/MiniMax-M3`). To pin a specific model for one role, edit the corresponding file under `<dataDir>/agents/<name>/`:

```yaml
# ~/.minimax/agents/rel-verifier/config.yaml
model: minimax/MiniMax-M2.7-highspeed
thinking:
  effort: low
```

The model schema is shared with the platform's Mavis/OpenCode provider definition (see `~/.minimax/config.yaml` for the model list and capabilities).

### Why the names look different in the Sub-Agent list

The agent **directory names** follow the file labels in `sub-agents/*.md`
(e.g. `0-mythos-singleshot-thinking-intelligence.md`) which keep git-history
continuity with `fable-mythos-zcode`. The agent **names** (sent in the HTTP
`name` field and used by the orchestrator) are the kebab-case short names
that fit MiniMax Code's 20-character cap:

```
mythos-thinker        mythos-executor        mythos-verifier
mythos-adversary      mythos-synthesizer
rel-scout             rel-critic             rel-test-des
rel-lead              rel-verifier           rel-adversary
```

### Why this bypasses the GUI's limits

MiniMax Code's UI form is just a thin client that POSTs to the same daemon endpoint we're calling. The form enforces two client-side caps:
1. `description` max 100 chars — easy to bypass by sending the full text via HTTP.
2. No system-prompt field at all — the form simply doesn't render it, but the daemon accepts and persists it.

Both are pure-UI constraints. The underlying RPC has no such limits; the `LocalAgentService.createAgent` method (`app.asar :: node_modules/@mavis/local-runtime/dist/agent/service.js:63`) only validates the agent name regex and the `displayName` non-emptiness.

---

## Troubleshooting

| Symptom                                              | Likely cause                                          | Fix                                                                  |
|------------------------------------------------------|-------------------------------------------------------|----------------------------------------------------------------------|
| `ERROR: Mavis daemon not detected on any expected port.` | MiniMax Code not running, or daemon shut down      | Open MiniMax Code (any user action triggers daemon boot), re-run.   |
| `ERROR: no accessToken in ~/.minimax/local-runtime.auth.json` | First-launch state — not signed in                | Sign in to MiniMax Code once, then re-run.                          |
| `HTTP 409 AGENT_NAME_CONFLICT` per agent              | An agent with that name already exists              | Run `bash install.sh --uninstall`, then re-run.                     |
| `HTTP 400 INVALID_AGENT_NAME`                         | Name in `## Feld: Name` violates `^[a-z][a-z0-9_-]{0,63}$` | Edit the offending `.md` file in `sub-agents/` to fix the name.  |
| Agents appear in disk but not in the Sub-Agent list  | Daemon hasn't rescanned — restart MiniMax Code       | Close + reopen MiniMax Code; the agents show up at next session.   |
| `delta == 0` from `verify_live_load.py`              | Daemon's SQLite reader hasn't seen the new rows yet  | Restart MiniMax Code, then re-run `verify_live_load.py after`.      |

---

## Schema Source of Truth (for maintainers)

The HTTP endpoint, field names, and validation are all generated from the Thrift IDL at build time. If MiniMax Code updates its schema, regenerate this installer against the new IDL:

- **Endpoint**: `app.asar :: node_modules/@mavis/thrift-gen/dist/generated/desktop-service/routes.js` — search `createAgent:` (around line 23064)
- **Validation**: `app.asar :: node_modules/@mavis/local-runtime/dist/agent/contract.js` — `validateCreateAgentInput`, `validateNewAgentName`
- **Service impl**: `app.asar :: node_modules/@mavis/local-runtime/dist/agent/service.js` — `LocalAgentService.createAgent` (line 63)

The auto-discovery reads the daemon's startup log line `Mavis Daemon started port=NNNNN` from `~/.minimax/logs/daemon-*.log` — this string is also generated but has been stable across the 3.0.x series.