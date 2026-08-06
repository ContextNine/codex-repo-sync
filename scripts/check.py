#!/usr/bin/env python3
"""Run repository-local structural validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    plugin_root = root / "plugins" / "codex-repo-sync"
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if manifest.get("name") != "codex-repo-sync":
        errors.append("plugin name must be codex-repo-sync")
    if "hooks" in manifest:
        errors.append("hooks must use default discovery, not the unsupported manifest field")
    if (plugin_root / "hooks" / "hooks.json").exists():
        errors.append("plugin hooks must not be auto-discovered; managed policy owns registration")

    compile_result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(plugin_root / "scripts" / "session_start.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    if compile_result.returncode != 0:
        errors.append(compile_result.stderr.strip())

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("repository checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
