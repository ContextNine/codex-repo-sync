#!/usr/bin/env python3
"""Install or verify Codex Repo Sync from a local or Git marketplace."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from managed_policy import install as install_managed_policy


PLUGIN_NAME = "codex-repo-sync"
MARKETPLACE_NAME = "ctx9"
DEFAULT_GIT_SOURCE = "MDerman/codex-repo-sync"


class InstallError(RuntimeError):
    pass


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def json_command(*args: str) -> dict[str, Any]:
    result = run(*args)
    if result.returncode != 0:
        raise InstallError(result.stderr.strip() or result.stdout.strip() or "command failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InstallError(f"invalid JSON from {' '.join(args)}: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"expected JSON object from {' '.join(args)}")
    return value


def plugin_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "plugins" / PLUGIN_NAME / ".codex-plugin" / "plugin.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid plugin manifest: {exc}") from exc
    if not isinstance(value, dict) or value.get("name") != PLUGIN_NAME or not value.get("version"):
        raise InstallError("plugin manifest has no accepted name/version")
    return value


def normalize_source(value: str) -> str:
    normalized = value.removesuffix(".git").removeprefix("git@github.com:")
    normalized = normalized.removeprefix("https://github.com/")
    return normalized.casefold().rstrip("/")


def marketplace_entries() -> list[dict[str, Any]]:
    value = json_command("codex", "plugin", "marketplace", "list", "--json")
    entries = value.get("marketplaces")
    if not isinstance(entries, list):
        raise InstallError("Codex marketplace list has no marketplaces")
    return [entry for entry in entries if isinstance(entry, dict)]


def ensure_marketplace(repo_root: Path, source: str | None, ref: str | None) -> None:
    desired_source = source or str(repo_root)
    matches = [entry for entry in marketplace_entries() if entry.get("name") == MARKETPLACE_NAME]
    if matches:
        current = matches[0].get("marketplaceSource")
        current_source = current.get("source") if isinstance(current, dict) else matches[0].get("root")
        if not isinstance(current_source, str) or normalize_source(current_source) != normalize_source(desired_source):
            raise InstallError(
                f"marketplace {MARKETPLACE_NAME!r} already points to a different source: {current_source}"
            )
        if isinstance(current, dict) and current.get("sourceType") == "git":
            result = run("codex", "plugin", "marketplace", "upgrade", MARKETPLACE_NAME, "--json")
            if result.returncode != 0:
                raise InstallError(result.stderr.strip() or result.stdout.strip())
        return

    command = ["codex", "plugin", "marketplace", "add", desired_source]
    if ref:
        command.extend(["--ref", ref])
    command.append("--json")
    result = run(*command)
    if result.returncode != 0:
        raise InstallError(result.stderr.strip() or result.stdout.strip())


def installed_plugin() -> dict[str, Any] | None:
    value = json_command("codex", "plugin", "list", "--json")
    installed = value.get("installed")
    if not isinstance(installed, list):
        raise InstallError("Codex plugin list has no installed plugins")
    return next(
        (
            item
            for item in installed
            if isinstance(item, dict) and item.get("pluginId") == f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
        ),
        None,
    )


def verify(repo_root: Path, policy_path: Path, managed_dir: Path) -> dict[str, Any]:
    expected_hook = repo_root / "plugins" / PLUGIN_NAME / "scripts" / "session_start.py"
    installed_hook = managed_dir / PLUGIN_NAME / "session_start.py"
    manifest = plugin_manifest(repo_root)
    errors: list[str] = []
    if not expected_hook.is_file() or not installed_hook.is_file():
        errors.append("managed hook is missing")
    elif hashlib.sha256(expected_hook.read_bytes()).digest() != hashlib.sha256(installed_hook.read_bytes()).digest():
        errors.append("managed hook does not match this release")
    try:
        policy = policy_path.read_text(encoding="utf-8")
    except OSError:
        policy = ""
    if "# codex-repo-sync:managed:start" not in policy or str(managed_dir) not in policy:
        errors.append("managed Codex policy is missing or points elsewhere")
    plugin = installed_plugin()
    if plugin is None:
        errors.append(f"{PLUGIN_NAME}@{MARKETPLACE_NAME} is not installed")
    else:
        if plugin.get("version") != manifest["version"]:
            errors.append(f"installed plugin version is {plugin.get('version')}, expected {manifest['version']}")
        if plugin.get("enabled") is not True:
            errors.append("installed plugin is disabled")
    return {
        "schema_version": 1,
        "component": PLUGIN_NAME,
        "version": manifest["version"],
        "ready": not errors,
        "managed_hook": str(installed_hook),
        "policy": str(policy_path),
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="verify the installed plugin and managed hook")
    mode.add_argument("--version", action="store_true", help="print the component version")
    parser.add_argument(
        "--marketplace-source",
        help=f"Git marketplace source, for example {DEFAULT_GIT_SOURCE}; local checkout by default",
    )
    parser.add_argument("--ref", help="exact Git ref for a Git marketplace source")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable result")
    parser.add_argument("--policy-path", type=Path, default=Path("/etc/codex/requirements.toml"), help=argparse.SUPPRESS)
    parser.add_argument("--managed-dir", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    manifest = plugin_manifest(repo_root)
    managed_dir = (args.managed_dir or Path.home() / ".local/share/codex/managed-hooks").expanduser().resolve()
    policy_path = args.policy_path.expanduser().resolve()
    if args.version:
        print(manifest["version"])
        return 0
    try:
        if args.verify:
            report = verify(repo_root, policy_path, managed_dir)
        else:
            ensure_marketplace(repo_root, args.marketplace_source, args.ref)
            hook_path, policy_changed = install_managed_policy(repo_root, policy_path, managed_dir)
            result = run("codex", "plugin", "add", f"{PLUGIN_NAME}@{MARKETPLACE_NAME}", "--json")
            if result.returncode != 0:
                raise InstallError(result.stderr.strip() or result.stdout.strip())
            report = verify(repo_root, policy_path, managed_dir)
            report["policy_changed"] = policy_changed
            report["managed_hook"] = str(hook_path)
    except (InstallError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Codex Repo Sync installation failed: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{PLUGIN_NAME} {report['version']}")
        print(f"Managed hook: {report['managed_hook']}")
        print(f"System policy: {report['policy']}")
        print("Status: ready" if report["ready"] else "Status: " + "; ".join(report["errors"]))
        if not args.verify:
            print("No /hooks review is required. Start a new Codex thread to load the managed hook.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
