#!/usr/bin/env python3
"""Build a deterministic Codex Repo Sync source release and checksum."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def version(root: Path) -> str:
    manifest = root / "plugins/codex-repo-sync/.codex-plugin/plugin.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    return str(value["version"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if len(source_commit) != 40:
        raise SystemExit("source commit must be a full SHA")
    release_version = version(root)
    if args.tag != f"v{release_version}":
        raise SystemExit(f"tag {args.tag!r} does not match plugin version {release_version!r}")
    archive_name = f"codex-repo-sync-{release_version}.tar.gz"
    archive = args.output / archive_name
    args.output.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            f"--prefix=codex-repo-sync-{release_version}/",
            "HEAD",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(tar)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = args.output / f"{archive_name}.sha256"
    checksum.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
    release = args.output / f"{archive_name}.release.json"
    release.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "component": "codex-repo-sync",
                "version": release_version,
                "tag": args.tag,
                "source_commit": source_commit,
                "artifact": {"name": archive_name, "sha256": digest},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(archive)
    print(checksum)
    print(release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
