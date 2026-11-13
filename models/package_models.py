"""Verify existing runtime weights and package the current manifest for Android."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def package(root, output, verify_only=False):
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = []
    for key, artifact in manifest["artifacts"].items():
        relative = Path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe artifact path: {relative}")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(f"Missing runtime weight: {relative}")
        if digest(path).lower() != artifact["sha256"].lower():
            raise ValueError(f"Weight SHA256 mismatch: {relative}")
        entries.append((path, relative.as_posix()))
    if verify_only:
        print(f"Verified {len(entries)} runtime weights for {manifest['config_version']}")
        return
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=1) as bundle:
        bundle.write(manifest_path, "manifest.json")
        for path, relative in entries:
            bundle.write(path, relative)
    print(f"Packaged {len(entries)} verified weights: {output}")
    print(f"ZIP SHA256: {digest(output)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="models")
    parser.add_argument("--output", default="models/android-models.zip")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    package(args.models, args.output, args.verify_only)


if __name__ == "__main__":
    main()
