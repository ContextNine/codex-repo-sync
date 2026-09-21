# Release and installation

Codex Repo Sync is an independently versioned CTX9 component. The GitHub repository is the source marketplace and release authority. A release tag must exactly equal `v<plugin version>`.

`scripts/build_release.py` creates a deterministic source archive and SHA-256 file from the tagged commit. The release workflow runs tests and structural checks before attaching both files to a GitHub Release.

The installer accepts either its current checkout or an explicit Git marketplace source and ref. It installs the managed hook, owns only its marker block in `/etc/codex/requirements.toml`, installs `codex-repo-sync@ctx9`, and verifies the exact plugin version, hook digest, policy path, and enabled state.

When the `ctx9` marketplace already points at a local checkout, the installer migrates it only if that checkout's Git origin exactly matches `ContextNine/codex-repo-sync`. A different source is a hard collision. Git-backed upgrades replace an older pinned release with the requested exact ref; an already matching release is a no-op.

The public `ctx9` launcher downloads the release archive, verifies its manifest checksum, and invokes:

```bash
python3 scripts/install.py \
  --marketplace-source ContextNine/codex-repo-sync \
  --ref v<VERSION>
```

`python3 scripts/install.py --verify --json` is the component doctor contract. Repeating install or verification must be safe and current.
