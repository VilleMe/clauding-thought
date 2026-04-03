#!/usr/bin/env python3
"""SessionStart hook: initializes the user-level Clauding Thought directory.

Creates ~/.claude/clauding-thought/ with:
- insights/ directory for cross-project learning
- packs/ directory with copies of bundled rule packs
- version.txt with the current plugin version

Runs on every session start. Idempotent — only updates when versions change.
Fail-open: errors exit 0 so they never block the session.
"""
import json
import os
import shutil
import sys

try:
    # Resolve paths
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not plugin_root:
        # No plugin root available, nothing to do
        sys.exit(0)

    home = os.path.expanduser("~")
    user_dir = os.path.join(home, ".claude", "clauding-thought")
    insights_dir = os.path.join(user_dir, "insights")
    packs_dir = os.path.join(user_dir, "packs")
    version_file = os.path.join(user_dir, "version.txt")

    # Read current plugin version
    plugin_json_path = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    plugin_version = "unknown"
    if os.path.isfile(plugin_json_path):
        with open(plugin_json_path, "r", encoding="utf-8") as f:
            plugin_version = json.load(f).get("version", "unknown")

    # Check if update needed
    current_version = ""
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            current_version = f.read().strip()

    # Create directories
    os.makedirs(insights_dir, exist_ok=True)
    os.makedirs(packs_dir, exist_ok=True)

    # Copy packs if version changed or packs dir is empty
    if current_version != plugin_version:
        source_packs = os.path.join(plugin_root, "packs")
        if os.path.isdir(source_packs):
            for pack_name in os.listdir(source_packs):
                src = os.path.join(source_packs, pack_name)
                dst = os.path.join(packs_dir, pack_name)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)

        # Write version file
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(plugin_version)

    sys.exit(0)

except SystemExit:
    raise
except Exception:
    # Fail open — never block session start
    sys.exit(0)
