#!/usr/bin/env python3
"""
deploy_subagents_http.py — HTTP-API deployer for fable-mythos-minimax.

Bypasses the MiniMax Code GUI's 100-char Description + no-system-prompt
limitation by calling the Mavis daemon's Thrift-gen HTTP endpoint directly:

    POST http://127.0.0.1:<PORT>/minimax-desktop/api/v1/agent
    Authorization: Bearer <accessToken from ~/.minimax/local-runtime.auth.json>
    Body: JSON { name, displayName, description, systemPrompt, defaultWorkspaceDir }

Source of truth for the field schema:
    app.asar  ::  node_modules/@mavis/thrift-gen/dist/generated/desktop-service/routes.js
                  createAgent entry (line ~23064) -> requestSchema fields:
                    name (opt), displayName (opt), persona (opt),
                    systemPrompt (opt), description (opt), avatar (opt),
                    defaultWorkspaceDir (opt), baseReq (opt struct)
    app.asar  ::  node_modules/@mavis/local-runtime/dist/agent/contract.js
                  validateCreateAgentInput -> validateNewAgentName ->
                  /^[a-z][a-z0-9_-]{0,63}$/  (20-char cap on local names)
    app.asar  ::  node_modules/@mavis/local-runtime/dist/agent/service.js
                  LocalAgentService.createAgent -> validates displayName
                  + calls assertConfigFieldsSafe on the user-controlled text
                  (no length cap on systemPrompt here, only at the GUI form).

Reads the same sub-agents/*.md field format as deploy_subagents.py, but
instead of writing <name>/agent.md files it POSTs each agent to the daemon.

The disk-drop format is kept as a fallback (so users can still use the
prior install.sh path): pass --method disk to use the file drop, or
--method http (default) to use the daemon API.

Usage:
    python deploy_subagents_http.py <src_dir>
    python deploy_subagents_http.py --method disk <src_dir> <dst_root>
"""

import argparse
import json
import os
import re
import socket
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ─── Path constants (MiniMax Code / Mavis convention) ─────────────────────
DATA_DIR = Path(os.environ.get("MAVIS_DATA_DIR", Path.home() / ".minimax"))
AGENTS_DIR = DATA_DIR / "agents"
AUTH_FILE = DATA_DIR / "local-runtime.auth.json"
DB_FILE = DATA_DIR / "sqlite.db"
LOG_DIR = DATA_DIR / "logs"

FENCE = re.compile(r"^```\s*$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


# ─── Field parser (same 3-state machine as deploy_subagents.py) ───────────
def get_field(text: str, field_name: str) -> str:
    """Return the fenced block content under `## Feld: <field_name>`."""
    lines = text.splitlines()
    capture = False
    content_mode = False
    out = []
    for line in lines:
        s = line.rstrip()
        if not capture:
            if s == f"## Feld: {field_name}":
                capture = True
            continue
        if not content_mode:
            if FENCE.match(s):
                content_mode = True
            continue
        if FENCE.match(s):
            break
        out.append(line)
    return "\n".join(out)


# ─── Daemon port discovery ────────────────────────────────────────────────
def discover_port() -> int | None:
    """Find the port of the running Mavis daemon by:
    1. Reading the latest daemon log for "Mavis Daemon started port=NNNNN".
    2. Falling back to localhost probing 15321 (default release port).

    Returns None if no daemon is detected.
    """
    if LOG_DIR.is_dir():
        logs = sorted(LOG_DIR.glob("daemon-*.log"), key=lambda p: p.stat().st_mtime)
        for log in reversed(logs[-5:]):  # only check the 5 most recent
            try:
                text = log.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = re.search(r"Mavis Daemon started port=(\d+)", text)
            if m:
                port = int(m.group(1))
                if _probe_port(port):
                    return port
    # Fallback: try the default release port.
    for port in (15321, 15322, 15323):
        if _probe_port(port):
            return port
    return None


def _probe_port(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def load_access_token() -> str | None:
    """Read the JWT access token from ~/.minimax/local-runtime.auth.json."""
    if not AUTH_FILE.is_file():
        return None
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return data.get("auth", {}).get("accessToken")
    except (json.JSONDecodeError, OSError):
        return None


# ─── HTTP API call ────────────────────────────────────────────────────────
def post_create_agent(port: int, token: str, body: dict, timeout: float = 8.0) -> tuple[int, str]:
    """POST a CreateAgent request to the daemon.

    Returns (status_code, response_body).
    """
    url = f"http://127.0.0.1:{port}/minimax-desktop/api/v1/agent"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return 0, f"URLError: {e.reason}"


# ─── DB read for verification ─────────────────────────────────────────────
def read_agents_table() -> list[tuple]:
    try:
        uri = f"file:{DB_FILE}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        cur = con.cursor()
        rows = cur.execute(
            "SELECT agent_name, creation_source, framework_type FROM agents "
            "ORDER BY agent_name"
        ).fetchall()
        con.close()
        return rows
    except Exception as e:
        return [("__error__", str(e), "")]


# ─── Per-agent deploy via HTTP ────────────────────────────────────────────
def deploy_http(src: Path, port: int, token: str) -> int:
    ok, fail, skip = 0, 0, 0
    for f in sorted(src.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        name = get_field(text, "Name").strip()
        desc_full = get_field(text, "Description").strip()
        prompt = get_field(text, "System prompt")
        desc_first = desc_full.split("\n", 1)[0].strip() if desc_full else ""

        if not name:
            print(f"  SKIP  {f.name}: empty Name", file=sys.stderr)
            skip += 1
            continue
        if not NAME_RE.match(name):
            print(f"  SKIP  {f.name}: name '{name}' fails /^[a-z][a-z0-9_-]{{0,63}}$/",
                  file=sys.stderr)
            skip += 1
            continue

        body = {
            "name": name,
            "displayName": name,
            "description": desc_first,
            "systemPrompt": prompt,
        }
        status, resp = post_create_agent(port, token, body)
        flag = "OK " if status == 200 else f"HTTP {status}"
        print(f"  {flag:7s} {name:18s} desc[{len(desc_first):3d}] prompt[{len(prompt):4d}]  -> {resp[:80]}")
        if status == 200:
            ok += 1
        else:
            fail += 1
    print()
    print(f"  Summary: {ok} created, {fail} failed, {skip} skipped")
    return ok


# ─── Per-agent deploy via disk-drop (fallback) ─────────────────────────────
def deploy_disk(src: Path, dst_root: Path) -> int:
    count = 0
    for f in sorted(src.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        name = get_field(text, "Name").strip()
        desc_full = get_field(text, "Description").strip()
        prompt = get_field(text, "System prompt")
        desc_first = desc_full.split("\n", 1)[0].strip() if desc_full else ""
        if not name or not NAME_RE.match(name):
            print(f"  SKIP {f.name}: invalid name '{name}'", file=sys.stderr)
            continue
        agent_dir = dst_root / name
        if agent_dir.exists():
            print(f"  EXIST {name} (skip)")
            continue
        agent_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = f"---\nname: {name}\ndescription: >-\n  {desc_first}\n---"
        body = f"# {name}\n\n{prompt}\n"
        (agent_dir / "agent.md").write_text(frontmatter + "\n\n" + body, encoding="utf-8")
        (agent_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
        print(f"  WROTE {name:18s} prompt[{len(prompt):4d}]")
        count += 1
    return count


# ─── Entry point ──────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Deploy fable-mythos-minimax sub-agents.")
    p.add_argument("src", help="Path to sub-agents/ directory")
    p.add_argument("--method", choices=("http", "disk"), default="http",
                   help="http = POST to daemon API (default), disk = file drop")
    p.add_argument("--dst", default=str(AGENTS_DIR),
                   help="Disk-drop target root (only used with --method disk)")
    p.add_argument("--port", type=int, default=None,
                   help="Daemon HTTP port (auto-discovered if omitted)")
    args = p.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"ERROR: src not a directory: {src}", file=sys.stderr)
        return 1

    if args.method == "disk":
        print(f"Disk-drop deploy to {args.dst}")
        deploy_disk(src, Path(args.dst))
        return 0

    # HTTP-API path
    port = args.port or discover_port()
    if port is None:
        print("ERROR: Mavis daemon not detected on any expected port.", file=sys.stderr)
        print("  Start MiniMax Code (the daemon must be running), or use --method disk",
              file=sys.stderr)
        return 2
    token = load_access_token()
    if not token:
        print(f"ERROR: no accessToken in {AUTH_FILE}", file=sys.stderr)
        return 3

    print(f"HTTP-API deploy -> http://127.0.0.1:{port}/minimax-desktop/api/v1/agent")
    print(f"  auth token: {token[:24]}...{token[-12:]} (length {len(token)})")
    deploy_http(src, port, token)

    # Verify by reading the agents table.
    print()
    print("Verifying agents table:")
    for row in read_agents_table():
        print(f"  {row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())