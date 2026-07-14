#!/usr/bin/env python3
"""
Live verification helper for MiniMax Code sub-agent disk drop.

Reads the on-disk agent directories and the sqlite.db registry.
Run BEFORE the user opens MiniMax Code, then again AFTER.

Usage:
    python scripts/verify_live_load.py before
    #   <user opens MiniMax Code now and waits ~10s>
    python scripts/verify_live_load.py after

When invoked as `before`, snapshots the disk + DB state to
    ~/.minimax/.fable-mythos/agents-before.txt
When invoked as `after`, snapshots to agents-after.txt and prints a diff.
"""

import sqlite3
import sys
import re
import datetime
from pathlib import Path

DB_WIN = Path.home() / ".minimax" / "sqlite.db"
DISK = Path.home() / ".minimax" / "agents"
SNAP_DIR = Path.home() / ".minimax" / ".fable-mythos"


def snapshot_db():
    try:
        uri = f"file:{DB_WIN}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        cur = con.cursor()
        rows = cur.execute(
            "SELECT agent_name, creation_source, framework_type, updated_at "
            "FROM agents ORDER BY agent_name"
        ).fetchall()
        con.close()
        out = []
        for r in rows:
            out.append(f"  {r}")
        out.append(f"  total: {len(rows)}")
        return "\n".join(out)
    except Exception as e:
        return f"  (DB read failed: {e})"


def snapshot_disk():
    if not DISK.exists():
        return f"  (disk dir missing: {DISK})"
    items = sorted(p.name for p in DISK.iterdir())
    return "\n".join(f"  {n}" for n in items)


def write_snapshot(label):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"agents-{label}.txt"
    body = (
        f"===== {datetime.datetime.now().isoformat(timespec='seconds')} =====\n"
        f"--- DB agents table ---\n{snapshot_db()}\n\n"
        f"--- disk agent dirs ---\n{snapshot_disk()}\n"
    )
    path.write_text(body, encoding="utf-8")
    print(body)
    print(f"Snapshot saved: {path}")


def print_diff():
    before_path = SNAP_DIR / "agents-before.txt"
    after_path = SNAP_DIR / "agents-after.txt"
    if not before_path.exists():
        print("ERROR: no BEFORE snapshot — run `verify_live_load.py before` first", file=sys.stderr)
        sys.exit(1)
    if not after_path.exists():
        print("ERROR: no AFTER snapshot — run `verify_live_load.py after` first", file=sys.stderr)
        sys.exit(1)
    snap_b = before_path.read_text(encoding="utf-8")
    snap_a = after_path.read_text(encoding="utf-8")
    print("===== AFTER (now) =====")
    print(snap_a)
    print("===== Diff vs BEFORE =====")
    m_b = re.search(r"total:\s*(\d+)", snap_b)
    m_a = re.search(r"total:\s*(\d+)", snap_a)
    before = m_b.group(1) if m_b else "?"
    after = m_a.group(1) if m_a else "?"
    print(f"  BEFORE total agents: {before}")
    print(f"  AFTER  total agents: {after}")
    if before.isdigit() and after.isdigit():
        delta = int(after) - int(before)
        print(f"  delta: {delta:+d}")
        if delta >= 11:
            print("  [OK] Mavis picked up 11+ new agents from disk")
        elif delta == 0:
            print("  [MISS] Mavis did NOT register the new agents - check ~/.minimax/logs/")
        else:
            print(f"  [PARTIAL] ({delta} new) - check DB subset")
    print()
    if before == after:
        print("If delta == 0, Mavis did NOT register — check ~/.minimax/logs/ for parse errors.")
    else:
        print(f"If delta >= 11, Mavis picked up the disk drop.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("before", "after"):
        print("usage: verify_live_load.py before|after", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "before":
        write_snapshot("before")
        print()
        print("Now open MiniMax Code and wait ~10s, then re-run:")
        print("  python scripts/verify_live_load.py after")
    else:
        write_snapshot("after")
        print()
        print_diff()


if __name__ == "__main__":
    main()
