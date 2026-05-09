#!/usr/bin/env python3
"""Reassemble split raw export chunks and verify SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base_dir = args.manifest.parent
    output = args.output or (base_dir / manifest["original_name"])

    with output.open("wb") as out:
        for part in manifest["parts"]:
            part_path = base_dir / part["name"]
            if sha256_file(part_path) != part["sha256"]:
                raise SystemExit(f"SHA-256 mismatch: {part_path}")
            with part_path.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    out.write(block)

    final_hash = sha256_file(output)
    if final_hash != manifest["sha256"]:
        raise SystemExit(
            f"Output SHA-256 mismatch: expected {manifest['sha256']}, got {final_hash}"
        )

    print(f"OK {output} {final_hash}")


if __name__ == "__main__":
    main()
