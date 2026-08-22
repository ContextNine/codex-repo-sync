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
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
