#!/usr/bin/env python3
"""Build and install the Codex managed-hook policy for codex-repo-sync."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


POLICY_PATH = Path("/etc/codex/requirements.toml")
MARKER_START = "# codex-repo-sync:managed:start"
MARKER_END = "# codex-repo-sync:managed:end"
MANAGED_HOOK_RELATIVE = Path("codex-repo-sync/session_start.py")


def _table_span(text: str, table: str) -> tuple[int, int] | None:
    header = re.compile(rf"(?m)^\s*\[{re.escape(table)}\]\s*(?:#.*)?$")
    match = header.search(text)
    if match is None:
        return None
    next_header = re.search(r"(?m)^\s*\[", text[match.end() :])
    end = match.end() + next_header.start() if next_header else len(text)
    return match.start(), end


def _set_table_key(text: str, table: str, key: str, value: str) -> str:
    span = _table_span(text, table)
    if span is None:
        suffix = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return f"{text}{suffix}[{table}]\n{key} = {value}\n"

    start, end = span
    section = text[start:end]
    key_pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")
    if key_pattern.search(section):
        section = key_pattern.sub(f"{key} = {value}", section, count=1)
    else:
        header_end = section.find("\n")
        if header_end == -1:
            section = f"{section}\n{key} = {value}\n"
        else:
            section = f"{section[: header_end + 1]}{key} = {value}\n{section[header_end + 1 :]}"
    return f"{text[:start]}{section}{text[end:]}"


def _remove_owned_block(text: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\s*{re.escape(MARKER_START)}\n.*?^\s*{re.escape(MARKER_END)}\s*\n?"
    )
    return pattern.sub("", text)


def render_requirements(existing: str, managed_dir: Path) -> str:
    """Preserve unrelated requirements while replacing this tool's owned policy."""
    text = _remove_owned_block(existing).rstrip() + "\n" if existing.strip() else ""
    text = _set_table_key(text, "features", "hooks", "true")
    text = _set_table_key(text, "hooks", "managed_dir", json.dumps(str(managed_dir)))

    hook_path = managed_dir / MANAGED_HOOK_RELATIVE
    command = shlex.quote(str(hook_path))
    block = "\n".join(
        [
            MARKER_START,
            "[[hooks.SessionStart]]",
            'matcher = "^(startup|resume)$"',
            "",
            "[[hooks.SessionStart.hooks]]",
            'type = "command"',
            f"command = {json.dumps(command)}",
            "timeout = 60",
            'statusMessage = "Fetching repository updates"',
            "additionalContextLimit = 4000",
            MARKER_END,
            "",
        ]
    )
    separator = "" if text.endswith("\n\n") else "\n"
    return f"{text}{separator}{block}"


def _apple_script_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _install_root_file(source: Path, destination: Path) -> bool:
    """Install a root-owned file, using one macOS admin dialog when required."""
    command = ["/usr/bin/install", "-m", "0644", str(source), str(destination)]

    if destination.parent.is_dir() and os.access(destination.parent, os.W_OK) and (
        not destination.exists() or os.access(destination, os.W_OK)
    ):
        subprocess.run(command, check=True)
        return True

    if os.geteuid() == 0:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(command, check=True)
        return True

    mkdir = ["sudo", "-n", "/bin/mkdir", "-p", str(destination.parent)]
    install = ["sudo", "-n", *command]
    if subprocess.run(mkdir, check=False, capture_output=True).returncode == 0:
        subprocess.run(install, check=True)
        return True

    if sys.platform == "darwin":
        shell_command = " && ".join(
            [
                f"/bin/mkdir -p {shlex.quote(str(destination.parent))}",
                " ".join(shlex.quote(part) for part in command),
            ]
        )
        script = f"do shell script {_apple_script_string(shell_command)} with administrator privileges"
        subprocess.run(["/usr/bin/osascript", "-e", script], check=True)
        return True

    if sys.stdin.isatty():
        subprocess.run(["sudo", "/bin/mkdir", "-p", str(destination.parent)], check=True)
        subprocess.run(["sudo", *command], check=True)
        return True

    raise RuntimeError(
        f"Administrator access is required once to install {destination}. "
        "Run this installer from an interactive terminal."
    )


def install(
    repo_root: Path,
    policy_path: Path = POLICY_PATH,
    managed_dir: Path | None = None,
) -> tuple[Path, bool]:
    source_hook = repo_root / "plugins" / "codex-repo-sync" / "scripts" / "session_start.py"
    if not source_hook.is_file():
        raise FileNotFoundError(f"Missing hook script: {source_hook}")

    managed_dir = managed_dir or Path.home() / ".local" / "share" / "codex" / "managed-hooks"
    installed_hook = managed_dir / MANAGED_HOOK_RELATIVE
    installed_hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_hook, installed_hook)
    installed_hook.chmod(0o755)

    existing = policy_path.read_text(encoding="utf-8") if policy_path.is_file() else ""
    desired = render_requirements(existing, managed_dir)
    if existing == desired:
        return installed_hook, False

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="codex-requirements-", suffix=".toml", delete=False
    ) as handle:
        handle.write(desired)
        temporary = Path(handle.name)
    try:
        _install_root_file(temporary, policy_path)
    finally:
        temporary.unlink(missing_ok=True)
    return installed_hook, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-path",
        type=Path,
        default=POLICY_PATH,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        hook_path, policy_changed = install(repo_root, args.policy_path)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Managed-hook installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Managed hook installed: {hook_path}")
    print(f"System policy: {args.policy_path} ({'updated' if policy_changed else 'already current'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
