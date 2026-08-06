#!/usr/bin/env python3
"""Fetch the active repository and give the current Codex task a safe sync brief."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported fleet is macOS/Linux.
    fcntl = None


DEFAULT_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def command_timeout() -> int:
    raw = os.environ.get("CODEX_REPO_SYNC_TIMEOUT_SECONDS", "")
    try:
        value = int(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(5, min(value, 300))


def run_git(cwd: Path, *args: str) -> CommandResult:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=command_timeout(),
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CommandResult(124, "", str(error))
    return CommandResult(
        completed.returncode,
        completed.stdout.strip(),
        completed.stderr.strip(),
    )


def successful_output(cwd: Path, *args: str) -> str | None:
    result = run_git(cwd, *args)
    return result.stdout if result.returncode == 0 and result.stdout else None


def repository_root(cwd: Path) -> Path | None:
    root = successful_output(cwd, "rev-parse", "--show-toplevel")
    return Path(root).resolve() if root else None


def git_common_dir(root: Path) -> Path:
    common_dir = successful_output(root, "rev-parse", "--git-common-dir")
    if not common_dir:
        return root / ".git"
    candidate = Path(common_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


class RepositoryLock:
    def __init__(self, root: Path) -> None:
        self.path = git_common_dir(root) / "codex-repo-sync.lock"
        self.handle: Any = None

    def __enter__(self) -> "RepositoryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is not None:
            if fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def current_branch(root: Path) -> str | None:
    return successful_output(root, "symbolic-ref", "--quiet", "--short", "HEAD")


def upstream_ref(root: Path) -> str | None:
    return successful_output(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )


def remotes(root: Path) -> list[str]:
    output = successful_output(root, "remote")
    return sorted(line for line in (output or "").splitlines() if line)


def fetch_remote(root: Path, branch: str | None) -> str | None:
    configured = None
    if branch:
        configured = successful_output(root, "config", "--get", f"branch.{branch}.remote")
    available = remotes(root)
    if configured and configured != "." and configured in available:
        return configured
    if "origin" in available:
        return "origin"
    if len(available) == 1:
        return available[0]
    return None


def dirty_paths(root: Path) -> list[str]:
    result = run_git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    if result.returncode != 0:
        return ["<git status failed>"]
    return [line for line in result.stdout.splitlines() if line]


def ahead_behind(root: Path, target: str | None) -> tuple[int, int] | None:
    if not target:
        return None
    result = run_git(root, "rev-list", "--left-right", "--count", f"HEAD...{target}")
    if result.returncode != 0:
        return None
    values = result.stdout.replace("\t", " ").split()
    if len(values) != 2:
        return None
    try:
        return int(values[0]), int(values[1])
    except ValueError:
        return None


def ref_exists(root: Path, ref: str) -> bool:
    return run_git(root, "show-ref", "--verify", "--quiet", ref).returncode == 0


def default_remote_ref(root: Path, remote: str | None) -> str | None:
    if not remote:
        return None
    symbolic = successful_output(
        root,
        "symbolic-ref",
        "--quiet",
        "--short",
        f"refs/remotes/{remote}/HEAD",
    )
    if symbolic:
        return symbolic
    for branch_name in ("master", "main"):
        full_ref = f"refs/remotes/{remote}/{branch_name}"
        if ref_exists(root, full_ref):
            return f"{remote}/{branch_name}"
    return None


def short_error(result: CommandResult) -> str:
    message = result.stderr or result.stdout or f"exit {result.returncode}"
    return " ".join(message.split())[:500]


def render_context(report: dict[str, Any]) -> str:
    lines = [
        "[codex-repo-sync] Mandatory repository freshness preflight",
        f"Repository: {report['root']}",
        f"Session source: {report['source']}",
        f"Branch: {report['branch'] or 'DETACHED'}",
        f"Fetch remote: {report['remote'] or 'none'} ({report['fetch']})",
        f"Upstream: {report['upstream'] or 'none'}",
        f"Working tree: {'dirty' if report['dirty_count'] else 'clean'}",
        f"Current-vs-upstream: {report['upstream_relation']}",
        f"Remote default: {report['default_ref'] or 'unknown'}",
        f"Current-vs-default: {report['default_relation']}",
        f"Automatic action: {report['action']}",
    ]

    if report.get("error"):
        lines.append(f"Preflight warning: {report['error']}")

    lines.extend(
        [
            "",
            "Before doing the user's task, use this report and inspect the repository's AGENTS.md/README rules. "
            "If the checkout is not safely current, reconcile fetched changes first. On the default branch, "
            "bring its upstream current. On another branch, bring its upstream current and merge the fetched "
            "remote default branch when it contains commits missing from the current branch. Prefer an explicit "
            "merge over rebase unless repository instructions require otherwise.",
            "Preserve all local work. Never reset, clean, force-update, discard, or silently overwrite changes. "
            "Do not stash unless the user explicitly authorizes it. Resolve conflicts only when the intended "
            "result is clear; otherwise stop and report the exact blocker. Continue the requested task only after "
            "repository freshness is established or the blocker is made explicit.",
        ]
    )
    return "\n".join(lines)


def relation_text(values: tuple[int, int] | None) -> str:
    if values is None:
        return "unknown"
    ahead, behind = values
    return f"ahead={ahead}, behind={behind}"


def inspect_and_sync(cwd: Path, source: str) -> dict[str, Any] | None:
    root = repository_root(cwd)
    if root is None:
        return None

    with RepositoryLock(root):
        branch = current_branch(root)
        remote = fetch_remote(root, branch)
        fetch_summary = "not attempted"
        error = None
        if remote:
            fetch_result = run_git(
                root,
                "fetch",
                "--prune",
                "--no-recurse-submodules",
                remote,
            )
            if fetch_result.returncode == 0:
                fetch_summary = "succeeded"
            else:
                fetch_summary = "failed"
                error = f"git fetch failed: {short_error(fetch_result)}"
        else:
            fetch_summary = "skipped: no unambiguous remote"

        upstream = upstream_ref(root)
        dirty = dirty_paths(root)
        upstream_relation = ahead_behind(root, upstream)
        default_ref = default_remote_ref(root, remote)
        default_relation = ahead_behind(root, default_ref)
        action = "none"

        if (
            fetch_summary == "succeeded"
            and branch
            and upstream
            and not dirty
            and upstream_relation is not None
            and upstream_relation[0] == 0
            and upstream_relation[1] > 0
        ):
            merge_result = run_git(root, "merge", "--ff-only", upstream)
            if merge_result.returncode == 0:
                action = f"fast-forwarded {branch} to {upstream}"
                upstream_relation = ahead_behind(root, upstream)
                default_relation = ahead_behind(root, default_ref)
            else:
                action = "fast-forward attempted but failed"
                error = f"git merge --ff-only failed: {short_error(merge_result)}"

        return {
            "root": str(root),
            "source": source,
            "branch": branch,
            "remote": remote,
            "fetch": fetch_summary,
            "upstream": upstream,
            "dirty_count": len(dirty),
            "upstream_relation": relation_text(upstream_relation),
            "default_ref": default_ref,
            "default_relation": relation_text(default_relation),
            "action": action,
            "error": error,
        }


def read_payload() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    if os.environ.get("CODEX_REPO_SYNC_SKIP") == "1":
        return 0

    payload = read_payload()
    cwd_value = payload.get("cwd")
    cwd = Path(cwd_value).expanduser() if isinstance(cwd_value, str) else Path.cwd()
    source = payload.get("source") if isinstance(payload.get("source"), str) else "unknown"

    report = inspect_and_sync(cwd, source)
    if report is None:
        return 0

    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": render_context(report),
        }
    }
    if report.get("error"):
        output["systemMessage"] = "Repository freshness preflight needs Codex attention before editing."
    json.dump(output, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
