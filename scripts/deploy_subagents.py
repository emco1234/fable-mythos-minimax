#!/usr/bin/env python3
"""
deploy_subagents.py — Internal helper for install.sh.

Reads sub-agents/*.md files (each carrying ## Feld: Name / Description /
System prompt blocks), and drops one <DST>/<name>/agent.md +
<DST>/<name>/config.yaml per agent.

The file format (sub-agents/*.md) is the human-edited source. The drop
format (~/.minimax/agents/<name>/agent.md) is what MiniMax Code / Mavis
parses at boot per create-agent SKILL.md guidance.

Idempotent: skips agents whose target directory already exists.
"""

import re
import sys
from pathlib import Path

FENCE = re.compile(r"^```\s*$")


def get_field(text: str, field_name: str) -> str:
    """Find `## Feld: <name>`, then return content between the next two ``` fences.
    Returns '' if not found."""
    lines = text.splitlines()
    capture = False  # we just saw the header, expect opening fence next
    content_mode = False  # we are inside the fenced block
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


def deploy(src: Path, dst_root: Path) -> int:
    count = 0
    skipped = []
    for f in sorted(src.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        name = get_field(text, "Name").strip()
        desc_full = get_field(text, "Description").strip()
        prompt = get_field(text, "System prompt")
        # Description: use the first line of the block (folded YAML >-)
        desc_first = desc_full.split("\n", 1)[0].strip() if desc_full else ""
        if not name:
            print(f"  SKIP {f.name}: empty Name field", file=sys.stderr)
            continue
        agent_dir = dst_root / name
        if agent_dir.exists():
            skipped.append(name)
            continue
        agent_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = f'---\nname: {name}\ndescription: >-\n  {desc_first}\n---'
        body = f"# {name} — Reliability Harness v2\n\n{prompt}\n"
        (agent_dir / "agent.md").write_text(frontmatter + "\n\n" + body, encoding="utf-8")
        (agent_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
        print(f"  {f.name:55s} -> {name:20s}  desc[{len(desc_first):3d}]  prompt[{len(prompt):4d}]")
        count += 1
    return count


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: deploy_subagents.py <src_dir> <dst_root>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if not src.is_dir():
        print(f"ERROR: src not a directory: {src}", file=sys.stderr)
        return 1
    dst.mkdir(parents=True, exist_ok=True)
    n = deploy(src, dst)
    return 0 if n > 0 else 0  # 0 even if all skipped (idempotent)


if __name__ == "__main__":
    sys.exit(main())
