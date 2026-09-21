from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "managed_policy.py"
SPEC = importlib.util.spec_from_file_location("codex_repo_sync_managed_policy", MODULE_PATH)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


class ManagedPolicyTests(unittest.TestCase):
    def test_new_policy_enables_managed_session_start_hook(self) -> None:
        managed_dir = Path("/Users/test/.local/share/codex/managed-hooks")
        result = POLICY.render_requirements("", managed_dir)
        self.assertIn("[features]\nhooks = true", result)
        self.assertIn(f'managed_dir = "{managed_dir}"', result)
        self.assertIn("[[hooks.SessionStart]]", result)
        self.assertIn("codex-repo-sync/session_start.py", result)

    def test_existing_requirements_are_preserved(self) -> None:
        existing = 'allowed_approval_policies = ["never"]\n\n[features]\nplugins = true\n'
        result = POLICY.render_requirements(existing, Path("/managed"))
        self.assertIn("plugins = true", result)
        self.assertIn('allowed_approval_policies = ["never"]', result)
        self.assertIn("hooks = true", result)

    def test_owned_hook_block_is_replaced_idempotently(self) -> None:
        first = POLICY.render_requirements("", Path("/managed"))
        second = POLICY.render_requirements(first, Path("/managed"))
        self.assertEqual(first, second)
        self.assertEqual(second.count(POLICY.MARKER_START), 1)

    def test_install_supports_unprivileged_test_policy_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "requirements.toml"
            managed_dir = Path(directory) / "managed-hooks"
            hook_path, changed = POLICY.install(ROOT, policy_path, managed_dir)
            self.assertTrue(changed)
            self.assertTrue(hook_path.is_file())
            self.assertIn("codex-repo-sync", policy_path.read_text(encoding="utf-8"))

    def test_uninstall_removes_owned_hook_and_policy_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy_path = root / "requirements.toml"
            managed_dir = root / "managed-hooks"
            hook_path, _changed = POLICY.install(ROOT, policy_path, managed_dir)
            policy_path.write_text(
                'allowed_approval_policies = ["never"]\n\n'
                + policy_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            hook_changed, policy_changed = POLICY.uninstall(policy_path, managed_dir)
            self.assertTrue(hook_changed)
            self.assertTrue(policy_changed)
            self.assertFalse(hook_path.exists())
            result = policy_path.read_text(encoding="utf-8")
            self.assertIn('allowed_approval_policies = ["never"]', result)
            self.assertNotIn(POLICY.MARKER_START, result)


if __name__ == "__main__":
    unittest.main()
