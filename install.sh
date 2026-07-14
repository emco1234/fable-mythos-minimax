#!/usr/bin/env bash
# Install fable-mythos-minimax sub-agents via Mavis daemon HTTP API.
#
# MiniMax Code's GUI for Custom Subagents only exposes Name (≤20 chars) +
# Description (≤100 chars) + Default working folder — NO system-prompt field
# and no description beyond 100 chars. This installer bypasses that GUI cap
# by calling the daemon's Thrift-gen HTTP endpoint directly:
#
#   POST http://127.0.0.1:<PORT>/minimax-desktop/api/v1/agent
#   Body: { name, displayName, description, systemPrompt, ... }
#
# Source of truth for the endpoint + schema:
#   app.asar :: node_modules/@mavis/thrift-gen/dist/generated/desktop-service/routes.js
#               (createAgent entry, line ~23064)
#   app.asar :: node_modules/@mavis/local-runtime/dist/agent/contract.js
#               (validateCreateAgentInput -> name regex)
#
# The full multi-KB system prompts from sub-agents/*.md are sent in one POST
# per agent, which the daemon persists to the `agents` table and the agent's
# local agent.md overlay file.
#
# Usage:
#   bash install.sh               # POST all 11 sub-agents to the running daemon
#   bash install.sh --dry-run     # parse + validate, no network calls
#   bash install.sh --disk        # fallback: file drop to ~/.minimax/agents/
#   bash install.sh --uninstall   # DELETE each agent via the daemon
#   bash install.sh --port 15321  # explicit daemon port
#
# Requirements:
#   - MiniMax Code must be running (so the Mavis daemon is alive on its port)
#   - Python 3.x with stdlib (no extra deps)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/sub-agents"
PY_SCRIPT="$SCRIPT_DIR/scripts/deploy_subagents_http.py"

# ─── Locate Python ────────────────────────────────────────────────────────
PY_BIN=""
for cand in python python3 py /c/Python313/python.exe; do
  if command -v "$cand" >/dev/null 2>&1; then
    PY_BIN="$(command -v "$cand")"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "ERROR: python not found in PATH (tried python, python3, py, /c/Python313/python.exe)" >&2
  exit 1
fi

# ─── Argument parsing ─────────────────────────────────────────────────────
DRY_RUN=0
DISK_FALLBACK=0
UNINSTALL=0
PORT_ARG=""
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --disk)       DISK_FALLBACK=1 ;;
    --uninstall)  UNINSTALL=1 ;;
    --port)       shift; PORT_ARG="$1" ;;
    --port=*)     PORT_ARG="${arg#--port=}" ;;
    -h|--help)
      sed -n '2,28p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# ─── Pre-flight ───────────────────────────────────────────────────────────
if [[ ! -d "$SRC" ]]; then
  echo "ERROR: sub-agents/ directory not found at $SRC" >&2
  exit 1
fi

# ─── Dry-run path: parse and print, no writes ─────────────────────────────
if [[ $DRY_RUN -eq 1 ]]; then
  echo "DRY-RUN: parsing $SRC/*.md (no files written, no HTTP calls)"
  echo
  for f in "$SRC"/*.md; do
    echo "── $(basename "$f") ──"
    "$PY_BIN" - "$f" <<'PY'
import re, sys
FENCE = re.compile(r"^```\s*$")
text = open(sys.argv[1], encoding="utf-8").read()
capture = content_mode = False
out = []
field = None
for line in text.splitlines():
    s = line.rstrip()
    if not capture:
        m = re.match(r"^## Feld: (\S+)", s)
        if m:
            field = m.group(1); capture = True
        continue
    if not content_mode:
        if FENCE.match(s): content_mode = True
        continue
    if FENCE.match(s):
        body = "\n".join(out).strip()
        if field in ("Name", "Description"):
            preview = body.split("\n", 1)[0]
            print(f"  {field:12s} {preview[:80]}")
        else:
            print(f"  {field:12s} ({len(body)} chars)")
        capture = content_mode = False
        field = None
        out = []
        continue
    out.append(line)
PY
  done
  exit 0
fi

# ─── Uninstall path ───────────────────────────────────────────────────────
if [[ $UNINSTALL -eq 1 ]]; then
  echo "Uninstalling fable-mythos-minimax sub-agents via daemon..."
  echo "(This calls DELETE /minimax-desktop/api/v1/agent/<name> for each)"
  echo
  PORT_FLAG=""
  [[ -n "$PORT_ARG" ]] && PORT_FLAG="--port $PORT_ARG"
  # The python helper doesn't have an uninstall path yet — fall back to
  # disk removal so the agents don't reappear on next daemon boot.
  DATA_DIR="${MAVIS_DATA_DIR:-$HOME/.mavis}"
  AGENTS_DIR="$DATA_DIR/agents"
  if command -v python >/dev/null 2>&1; then
    AGENTS_DIR="$(python -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$AGENTS_DIR" 2>/dev/null || echo "$AGENTS_DIR")"
  fi
  for name in mythos-thinker mythos-executor mythos-verifier mythos-adversary \
              mythos-synthesizer rel-scout rel-critic rel-test-des \
              rel-lead rel-verifier rel-adversary; do
    if [[ -d "$AGENTS_DIR/$name" ]]; then
      echo "  rm $AGENTS_DIR/$name"
      rm -rf "$AGENTS_DIR/$name"
    else
      echo "  skip $name (not present)"
    fi
  done
  echo
  echo "Done. Restart MiniMax Code to refresh its agent list."
  exit 0
fi

# ─── Install path ─────────────────────────────────────────────────────────
echo "fable-mythos-minimax installer"
echo "============================="
echo

# Find the daemon log to discover the port (auto-discovery).
DAEMON_LOG="$HOME/.minimax/logs"
if [[ -d "$DAEMON_LOG" ]]; then
  latest_log="$(ls -t "$DAEMON_LOG"/daemon-*.log 2>/dev/null | head -1 || true)"
  if [[ -n "$latest_log" ]]; then
    detected_port="$(grep -oE "Mavis Daemon started port=[0-9]+" "$latest_log" | tail -1 | cut -d= -f2 || true)"
    if [[ -n "$detected_port" && -z "$PORT_ARG" ]]; then
      PORT_ARG="$detected_port"
      echo "Auto-detected daemon port: $PORT_ARG (from $(basename "$latest_log"))"
    fi
  fi
fi

if [[ -n "$PORT_ARG" ]]; then
  echo "Using port: $PORT_ARG"
else
  echo "(No daemon port detected yet; the python helper will probe 15321 and scan logs.)"
fi
echo

# ─── Disk fallback (still useful for offline / daemon-not-running) ───────
if [[ $DISK_FALLBACK -eq 1 ]]; then
  echo "Disk-drop fallback: writing <dataDir>/agents/<name>/agent.md files"
  DST="${MAVIS_DATA_DIR:-$HOME/.mavis}/agents"
  if command -v python >/dev/null 2>&1; then
    DST="$(python -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DST" 2>/dev/null || echo "$DST")"
  fi
  echo "  DST=$DST"
  echo
  "$PY_BIN" "$PY_SCRIPT" --method disk --dst "$DST" "$SRC"
  echo
  echo "Disk drop complete. To activate, restart MiniMax Code."
  exit 0
fi

# ─── HTTP API path (primary) ─────────────────────────────────────────────
PORT_FLAG=""
[[ -n "$PORT_ARG" ]] && PORT_FLAG="--port $PORT_ARG"

echo "Deploying 11 sub-agents via POST /minimax-desktop/api/v1/agent"
echo "(this bypasses the GUI's 100-char / no-system-prompt limits)"
echo
"$PY_BIN" "$PY_SCRIPT" --method http $PORT_FLAG "$SRC"
rc=$?

echo
if [[ $rc -eq 0 ]]; then
  echo "Done. The agents should appear in MiniMax Code's Sub-Agent list"
  echo "alongside the built-ins (coder, general, mavis, verifier)."
  echo
  echo "If the daemon was not running, re-run with the MiniMax Code app open:"
  echo "  bash install.sh"
fi
exit $rc