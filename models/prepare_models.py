"""Download pinned artifacts, measure SHA256, extract Vosk and publish an importable model ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--semantic-revision", required=True, help="Hugging Face commit SHA reviewed by the group")
parser.add_argument("--silero-revision", required=True, help="snakers4/silero-vad commit SHA reviewed by the group")
parser.add_argument("--output", type=Path, default=Path("models"))
parser.add_argument("--vosk-archive", type=Path, help="Existing cn-0.22 ZIP, verified before use")
parser.add_argument("--vosk-source", default="https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip")
parser.add_argument("--vosk-sha256", help="Expected archive SHA256, mandatory for a custom source")
args = parser.parse_args()
if args.vosk_source != "https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip" and not args.vosk_sha256:
    parser.error("A custom Vosk source requires its expected SHA256")
import re
for value in (args.semantic_revision, args.silero_revision):
    if not re.fullmatch("[0-9a-f]{40}", value):
        parser.error("Use full immutable commit hashes")
root = args.output
root.mkdir(parents=True, exist_ok=True)
base = f"https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/resolve/{args.semantic_revision}"
urls = {
    "semantic": (f"{base}/onnx/model.onnx", "weights/semantic.onnx", "Apache-2.0"),
    "tokenizer": (f"{base}/sentencepiece.bpe.model", "weights/sentencepiece.bpe.model", "Apache-2.0"),
    "vad": (f"https://raw.githubusercontent.com/snakers4/silero-vad/{args.silero_revision}/src/silero_vad/data/silero_vad.onnx",
            "weights/silero_vad.onnx", "MIT"),
    "vosk_archive": ("https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip", "weights/vosk-model-cn-0.22.zip", "Apache-2.0"),
}
artifacts = {}
for name, (url, relative, license) in urls.items():
    path = args.vosk_archive if name == "vosk_archive" and args.vosk_archive else root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as source, temporary.open("wb") as target:
            import shutil
            shutil.copyfileobj(source, target)
        temporary.replace(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    expected = {"semantic": "10f7a088420252b26caf819236ca2c9d2987afd0fc06fec7553b542a5655a05a",
                "vad": "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
                "vosk_archive": args.vosk_sha256}.get(name)
    if expected and digest.hexdigest() != expected:
        raise ValueError(f"SHA256 mismatch for {name}")
    artifacts[name] = {"path": relative, "url": args.vosk_source if name == "vosk_archive" else url,
                       "sha256": digest.hexdigest(), "license": license}
vosk_directory = "weights/vosk-model-cn-0.22"
with ZipFile(args.vosk_archive or root / artifacts["vosk_archive"]["path"]) as archive:
    if archive.testzip() is not None:
        raise ValueError("Corrupt Vosk archive")
    import shutil
    roots = {item.filename.split("/")[0] for item in archive.infolist()}
    if len(roots) != 1:
        raise ValueError("Expected one Vosk archive root")
    for item in archive.infolist():
        relative = Path(*item.filename.split("/")[1:])
        target = (root / vosk_directory / relative).resolve()
        if not target.is_relative_to((root / vosk_directory).resolve()):
            raise ValueError("Unsafe archive path")
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
source_archive = artifacts.pop("vosk_archive")
for index, path in enumerate(sorted((root / vosk_directory).rglob("*"))):
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        artifacts[f"vosk_file_{index:03d}"] = {"path": path.relative_to(root).as_posix(),
            "sha256": digest.hexdigest(), "license": "Apache-2.0"}
if len(artifacts) <= 3:
    raise ValueError("Archive does not contain the expected vosk-model-cn-0.22 directory")
manifest = {
    "model_version": "modelset-" + args.semantic_revision[:12] + "-" + args.silero_revision[:12] + "-" + source_archive["sha256"][:12],
    "config_version": "rules-v1", "source_archives": [source_archive], "artifacts": artifacts, "vosk_directory": vosk_directory,
    "config": {"dimension": 384, "max_length": 128, "pooling": "mean", "normalize": "L2",
               "match_threshold": 0.8, "vad_threshold": 0.5, "tokenizer": "XLM-R SentencePiece offset=1",
               "long_text": "126-token chunks weighted by content-token count"},
}
(root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
# Bundle only verified runtime files; never include partial downloads, chunks or source archives.
with ZipFile(root / "android-models.zip", "w", ZIP_DEFLATED, compresslevel=1) as bundle:
    bundle.write(root / "manifest.json", "manifest.json")
    for artifact in artifacts.values():
        bundle.write(root / artifact["path"], artifact["path"])
print(root / "android-models.zip")
