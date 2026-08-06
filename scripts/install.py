#!/usr/bin/env python3
"""Install the managed hook and refresh the local Codex plugin."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from managed_policy import install as install_managed_policy


PLUGIN_NAME = "codex-repo-sync"
MARKETPLACE_NAME = "personal"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    marketplace_file = repo_root / ".agents" / "plugins" / "marketplace.json"
    if not marketplace_file.is_file():
        print(f"Missing marketplace manifest: {marketplace_file}", file=sys.stderr)
        return 1

    try:
        hook_path, policy_changed = install_managed_policy(repo_root)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Managed-hook installation failed: {error}", file=sys.stderr)
        return 1

    list_result = run("codex", "plugin", "marketplace", "list")
    if list_result.returncode != 0:
        print(list_result.stderr.strip(), file=sys.stderr)
        return list_result.returncode

    root_text = str(repo_root)
    if root_text not in list_result.stdout:
        add_result = run(
            "codex",
            "plugin",
            "marketplace",
            "add",
            root_text,
            "--json",
        )
        if add_result.returncode != 0:
            print(add_result.stderr.strip() or add_result.stdout.strip(), file=sys.stderr)
            return add_result.returncode

    install_result = run(
        "codex",
        "plugin",
        "add",
        f"{PLUGIN_NAME}@{MARKETPLACE_NAME}",
        "--json",
    )
    if install_result.returncode != 0:
        print(install_result.stderr.strip() or install_result.stdout.strip(), file=sys.stderr)
        return install_result.returncode

    try:
        installed = json.loads(install_result.stdout)
        version = installed.get("version", "installed")
    except (json.JSONDecodeError, AttributeError):
        version = "installed"

    print(f"{PLUGIN_NAME} {version}")
    print(f"Managed hook: {hook_path}")
    print(f"System policy: {'updated' if policy_changed else 'already current'}")
    print("No /hooks review is required. Start a new Codex thread to load the managed hook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
