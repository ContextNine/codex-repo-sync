from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / "plugins" / "codex-repo-sync" / "scripts" / "session_start.py"
SPEC = importlib.util.spec_from_file_location("codex_repo_sync_session_start", HOOK_PATH)
assert SPEC and SPEC.loader
HOOK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOK
SPEC.loader.exec_module(HOOK)


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def configure_identity(repo: Path) -> None:
    git(repo, "config", "user.name", "Codex Repo Sync Tests")
    git(repo, "config", "user.email", "codex-repo-sync@example.invalid")


class RepositoryFixture:
    def __init__(self, base: Path) -> None:
        self.remote = base / "remote.git"
        self.seed = base / "seed"
        self.worker = base / "worker"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=master", str(self.remote)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "clone", str(self.remote), str(self.seed)],
            check=True,
            capture_output=True,
            text=True,
        )
        configure_identity(self.seed)
        (self.seed / "README.md").write_text("initial\n", encoding="utf-8")
        git(self.seed, "add", "README.md")
        git(self.seed, "commit", "-m", "initial")
        git(self.seed, "push", "-u", "origin", "master")
        subprocess.run(
            ["git", "clone", str(self.remote), str(self.worker)],
            check=True,
            capture_output=True,
            text=True,
        )
        configure_identity(self.worker)

    def push_remote_commit(self, name: str = "remote.txt") -> str:
        path = self.seed / name
        path.write_text(f"{name}\n", encoding="utf-8")
        git(self.seed, "add", name)
        git(self.seed, "commit", "-m", f"add {name}")
        git(self.seed, "push")
        return git(self.seed, "rev-parse", "HEAD")


class SessionStartTests(unittest.TestCase):
    def test_outside_repository_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = HOOK.inspect_and_sync(Path(directory), "startup")
        self.assertIsNone(report)

    def test_clean_behind_branch_fast_forwards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = RepositoryFixture(Path(directory))
            expected_head = fixture.push_remote_commit()
            report = HOOK.inspect_and_sync(fixture.worker, "startup")
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(git(fixture.worker, "rev-parse", "HEAD"), expected_head)
            self.assertIn("fast-forwarded master", report["action"])
            self.assertEqual(report["upstream_relation"], "ahead=0, behind=0")

    def test_dirty_behind_branch_is_preserved_for_codex(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = RepositoryFixture(Path(directory))
            old_head = git(fixture.worker, "rev-parse", "HEAD")
            fixture.push_remote_commit()
            (fixture.worker / "local.txt").write_text("local\n", encoding="utf-8")
            report = HOOK.inspect_and_sync(fixture.worker, "startup")
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(git(fixture.worker, "rev-parse", "HEAD"), old_head)
            self.assertEqual(report["action"], "none")
            self.assertGreater(report["dirty_count"], 0)
            self.assertEqual(report["upstream_relation"], "ahead=0, behind=1")

    def test_feature_branch_reports_missing_default_branch_commits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = RepositoryFixture(Path(directory))
            git(fixture.worker, "switch", "-c", "feature")
            (fixture.worker / "feature.txt").write_text("feature\n", encoding="utf-8")
            git(fixture.worker, "add", "feature.txt")
            git(fixture.worker, "commit", "-m", "feature")
            git(fixture.worker, "push", "-u", "origin", "feature")
            fixture.push_remote_commit("master-new.txt")
            report = HOOK.inspect_and_sync(fixture.worker, "startup")
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["branch"], "feature")
            self.assertEqual(report["default_ref"], "origin/master")
            self.assertEqual(report["default_relation"], "ahead=1, behind=1")
            context = HOOK.render_context(report)
            self.assertIn("merge the fetched remote default branch", context)

    def test_divergent_upstream_is_not_merged_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = RepositoryFixture(Path(directory))
            (fixture.worker / "local.txt").write_text("local\n", encoding="utf-8")
            git(fixture.worker, "add", "local.txt")
            git(fixture.worker, "commit", "-m", "local")
            fixture.push_remote_commit()
            report = HOOK.inspect_and_sync(fixture.worker, "startup")
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["action"], "none")
            self.assertEqual(report["upstream_relation"], "ahead=1, behind=1")

    def test_cli_returns_developer_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = RepositoryFixture(Path(directory))
            payload = json.dumps({"cwd": str(fixture.worker), "source": "startup"})
            completed = subprocess.run(
                ["python3", str(HOOK_PATH)],
                input=payload,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "CODEX_REPO_SYNC_TIMEOUT_SECONDS": "10"},
            )
            output = json.loads(completed.stdout)
            hook_output = output["hookSpecificOutput"]
            self.assertEqual(hook_output["hookEventName"], "SessionStart")
            self.assertIn("Mandatory repository freshness preflight", hook_output["additionalContext"])


if __name__ == "__main__":
    unittest.main()
