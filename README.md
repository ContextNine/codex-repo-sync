# Codex Repo Sync

`codex-repo-sync` is a Codex lifecycle plugin that fetches the current Git repository whenever a Codex session starts or resumes. It safely fast-forwards a clean branch that is strictly behind its own upstream, then gives the active Codex task a structured repository report and mandatory integration instructions.

The hook deliberately uses the already-running Codex task as the judgment layer. It does not start a nested Codex process.

## Behavior

| Repository state | Hook behavior |
| --- | --- |
| Outside Git | Exit without output |
| Clean and strictly behind current upstream | Fetch and fast-forward with `git merge --ff-only` |
| Current feature branch is missing commits from the remote default branch | Ask the active Codex task to inspect and merge the default branch before task edits |
| Dirty, ahead, divergent, detached, or missing upstream | Preserve the checkout and ask the active Codex task to reconcile it |
| Fetch or fast-forward failure | Continue the session with a warning and require Codex to diagnose before editing |

The plugin never stashes, resets, cleans, rebases, switches branches, creates merge commits, force-updates, or discards work. A non-fast-forward integration is always performed by the active Codex task under the repository's own instructions.

## Install locally

```bash
python3 scripts/install.py
```

Then start Codex, open `/hooks`, review the `codex-repo-sync` `SessionStart` hook, and trust it. Codex records trust against the hook definition, so changed definitions require review again.

Start a new task in a Git repository after installation. The hook runs for `startup` and `resume`, but not for `compact`, so it does not change repository state during mid-turn context compaction.

## Fleet distribution

The repository lives at `~/Code/ctx9/codex-repo-sync`. The existing CTX9 recursive code-workspace catalog discovers it automatically, so the fleet workspace reconciler can clone the same path on another registered machine. Run `python3 scripts/install.py` in that target checkout, then review and trust the hook on that machine.

Private GitHub access must work noninteractively before the workspace reconciler can clone this private repository. Do not copy credentials or weaken Git authentication to bypass that gate; use the target machine's reviewed GitHub authentication flow.

## Validate

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check.py
```

Set `CODEX_REPO_SYNC_SKIP=1` for a one-process bypass. Set `CODEX_REPO_SYNC_TIMEOUT_SECONDS` to change the Git command timeout from its default of 45 seconds.
