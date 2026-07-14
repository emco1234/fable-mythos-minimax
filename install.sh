#!/usr/bin/env bash
# Install fable-mythos-minimax sub-agents via direct-to-disk drop.
#
# MiniMax Code / Mavis loads Custom Subagents from <dataDir>/agents/<name>/agent.md
# (where <dataDir> defaults to ~/.mavis/ which on Windows symlinks to ~/.minimax/).
# A Custom Agent just needs:
#   - agent.md   with YAML frontmatter (name: + description:) + Markdown body
#                The Markdown body IS the system prompt (length is unlimited).
#   - config.yaml empty `{}` works (uses platform default model)
#
# The UI's "New Subagent" form has a 100-char Description limit, but loading
# via disk drop bypasses that. The Description in YAML may be longer than 100
# chars; Mavis stores it as-is.
#
# Usage:
#   bash install.sh           # deploy all 11 to ~/.minimax/agents/
#   bash install.sh --uninstall
#   bash install.sh --dry-run # print actions without doing them
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/sub-agents"
# Default to ~/.mavis/agents/ which on Windows is a symlink to ~/.minimax/agents/.
# This is the Mavis convention (see built-in create-agent SKILL: <dataDir>/agents/<name>/).
# Override with `MAVIS_DATA_DIR=/path bash install.sh`.
DST="${MAVIS_DATA_DIR:-$HOME/.mavis}/agents"

# Resolve symlinks (e.g. on Windows where ~/.mavis -> ~/.minimax) so writes go to
# the real on-disk location. Falls back to un-resolved path if Python is not yet
# available; the deploy script later re-resolves when invoked.
if command -v python >/dev/null 2>&1; then
  RESOLVED="$(python -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DST" 2>/dev/null || echo "$DST")"
  if [[ -n "$RESOLVED" ]]; then DST="$RESOLVED"; fi
elif command -v python3 >/dev/null 2>&1; then
  RESOLVED="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DST" 2>/dev/null || echo "$DST")"
  if [[ -n "$RESOLVED" ]]; then DST="$RESOLVED"; fi
fi

DRY_RUN=0
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

run() {
  echo "+ $*"
  [[ $DRY_RUN -eq 0 ]] && "$@"
}

# ---- Uninstall ----
if [[ $UNINSTALL -eq 1 ]]; then
  echo "Uninstalling fable-mythos-minimax sub-agents from $DST..."
  for name in mythos-thinker mythos-executor mythos-verifier mythos-adversary \
              mythos-synthesizer rel-scout rel-critic rel-test-des \
              rel-lead rel-verifier rel-adversary; do
    run rm -rf "$DST/$name"
  done
  echo "Done. Restart MiniMax Code to reload agent list."
  exit 0
fi

# ---- Pre-flight ----
if [[ ! -d "$SRC" ]]; then
  echo "ERROR: sub-agents/ directory not found at $SRC" >&2
  exit 1
fi
mkdir -p "$DST"

# ---- Per-agent deploy (Python parser, robust against YAML frontmatter) ----
PY_BIN=""
for candidate in python python3 py /c/Python313/python.exe; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_BIN="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "ERROR: python not found in PATH (tried python, python3, py, /c/Python313/python.exe)" >&2
  exit 1
fi

if [[ $DRY_RUN -eq 0 ]]; then
  "$PY_BIN" "$SCRIPT_DIR/scripts/deploy_subagents.py" "$SRC" "$DST"
else
  echo "+ dry-run: would run $PY_BIN $SCRIPT_DIR/scripts/deploy_subagents.py $SRC $DST"
fi

echo ""
echo "Installed all 11 sub-agents under $DST."
echo ""
echo "Each agent is a directory containing:"
echo "  agent.md      # YAML frontmatter (name + description) + Markdown system prompt body"
echo "  config.yaml   # {} (empty — uses platform default model)"
echo ""
echo "Restart MiniMax Code to load the agents. They will appear in"
echo "the Sub-Agent list alongside the four built-in agents (coder,"
echo "general, mavis, verifier)."
echo ""
echo "If a name looks truncated in the UI, check that the YAML"
echo "frontmatter's name: field matches the directory name."
