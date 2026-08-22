from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "install.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("codex_repo_sync_install", MODULE_PATH)
assert SPEC and SPEC.loader
INSTALL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INSTALL
SPEC.loader.exec_module(INSTALL)


class InstallTests(unittest.TestCase):
    def test_git_marketplace_add_uses_exact_ref(self) -> None:
        success = subprocess.CompletedProcess(["codex"], 0, "{}", "")
        with (
            patch.object(INSTALL, "marketplace_entries", return_value=[]),
            patch.object(INSTALL, "run", return_value=success) as run,
        ):
            INSTALL.ensure_marketplace(ROOT, "MDerman/codex-repo-sync", "v0.1.0")
        run.assert_called_once_with(
            "codex",
            "plugin",
            "marketplace",
            "add",
            "MDerman/codex-repo-sync",
            "--ref",
            "v0.1.0",
            "--json",
        )

    def test_existing_marketplace_with_different_source_is_refused(self) -> None:
        entries = [
            {
                "name": "ctx9",
                "marketplaceSource": {"sourceType": "git", "source": "other/repository"},
            }
        ]
        with (
            patch.object(INSTALL, "marketplace_entries", return_value=entries),
            self.assertRaisesRegex(INSTALL.InstallError, "different source"),
        ):
            INSTALL.ensure_marketplace(ROOT, "MDerman/codex-repo-sync", "v0.1.0")

    def test_verify_accepts_matching_hook_policy_and_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            plugin = root / "plugins/codex-repo-sync"
            hook = plugin / "scripts/session_start.py"
            hook.parent.mkdir(parents=True)
            hook.write_text("hook\n", encoding="utf-8")
            manifest = plugin / ".codex-plugin/plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps({"name": "codex-repo-sync", "version": "0.1.0"}),
                encoding="utf-8",
            )
            managed = Path(temporary) / "managed"
            installed = managed / "codex-repo-sync/session_start.py"
            installed.parent.mkdir(parents=True)
            installed.write_text("hook\n", encoding="utf-8")
            policy = Path(temporary) / "requirements.toml"
            policy.write_text(
                f'managed_dir = "{managed}"\n# codex-repo-sync:managed:start\n',
                encoding="utf-8",
            )
            with patch.object(
                INSTALL,
                "installed_plugin",
                return_value={"version": "0.1.0", "enabled": True},
            ):
                report = INSTALL.verify(root, policy, managed)
            self.assertTrue(report["ready"])
            self.assertEqual(report["errors"], [])
