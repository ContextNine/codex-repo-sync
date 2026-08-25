# Agent Instructions

This repository owns the `codex-repo-sync` Codex plugin.

Before task edits, fetch the configured upstream and compare it with `HEAD`. Fast-forward only when the checkout is clean and strictly behind. Never stash, reset, clean, rebase, force-update, or discard unrelated work.

Keep the hook and managed-policy installer standard-library-only and compatible with current macOS and Linux Python 3. The supported install path is `python3 scripts/install.py`; agents must complete it without asking the user to review the hook in `/hooks`. A first-time operating-system administrator prompt for `/etc/codex/requirements.toml` is distinct from Codex hook trust.

Run these checks after changes:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check.py
```

Repository-specific documentation lives in `docs/`. Update it with behavior, installation, release, policy, or verification changes and keep `docs/README.md` current. Release and fresh-install behavior is documented in `docs/release-and-installation.md`; a release tag must match the stable plugin version and include the deterministic archive plus its SHA-256 file.

The plugin manifest must remain at `plugins/codex-repo-sync/.codex-plugin/plugin.json`. Do not create `plugins/codex-repo-sync/hooks/hooks.json`: ordinary plugin hook discovery would reintroduce Codex's per-definition trust review. `scripts/install.py` owns managed `SessionStart` registration through `/etc/codex/requirements.toml`.
