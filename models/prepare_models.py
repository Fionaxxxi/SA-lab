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
args = parser.parse_args()
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
    path = root / relative
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
    artifacts[name] = {"path": relative, "url": url, "sha256": digest.hexdigest(), "license": license}
vosk_directory = "weights/vosk-model-cn-0.22"
with ZipFile(root / artifacts["vosk_archive"]["path"]) as archive:
    for item in archive.infolist():
        target = (root / "weights" / item.filename).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Unsafe archive path")
    archive.extractall(root / "weights")
manifest = {
    "model_version": "modelset-" + args.semantic_revision[:12] + "-" + args.silero_revision[:12],
    "config_version": "rules-v1", "artifacts": artifacts, "vosk_directory": vosk_directory,
    "config": {"dimension": 384, "max_length": 128, "pooling": "mean", "normalize": "L2",
               "match_threshold": 0.8, "vad_threshold": 0.5, "tokenizer": "XLM-R SentencePiece offset=1",
               "long_text": "126-token chunks weighted by content-token count"},
}
(root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
# Keep downloaded archive in the bundle because manifest verification covers its hash.
with ZipFile(root / "android-models.zip", "w", ZIP_DEFLATED) as bundle:
    bundle.write(root / "manifest.json", "manifest.json")
    for path in (root / "weights").rglob("*"):
        if path.is_file():
            bundle.write(path, path.relative_to(root).as_posix())
print(root / "android-models.zip")
