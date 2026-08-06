# Agent Instructions

This repository owns the `codex-repo-sync` Codex plugin.

Before task edits, fetch the configured upstream and compare it with `HEAD`. Fast-forward only when the checkout is clean and strictly behind. Never stash, reset, clean, rebase, force-update, or discard unrelated work.

Keep the hook standard-library-only and compatible with current macOS and Linux Python 3. Run these checks after changes:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check.py
```

The plugin manifest must remain at `plugins/codex-repo-sync/.codex-plugin/plugin.json`. Lifecycle hooks use the default `plugins/codex-repo-sync/hooks/hooks.json` discovery path; do not add the currently unsupported `hooks` manifest field.
