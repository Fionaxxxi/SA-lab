import hashlib
import json
import os
from pathlib import Path
from server.modules.asr import Asr
from server.modules.semantic import Semantic
from server.modules.vad import Vad
from server.modules.match import Matcher


def create_handlers():
    root = Path(os.environ.get("SA_MODEL_ROOT", "models")).resolve()
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    for artifact in manifest["artifacts"].values():
        path = (root / artifact["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid model path")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != artifact["sha256"]:
            raise ValueError(f"Hash mismatch: {path.name}")
    artifact = lambda key: root / manifest["artifacts"][key]["path"]
    config = manifest["config"]
    return {"M1": Vad(artifact("vad"), config["vad_threshold"]),
            "M2": Asr(root / manifest["vosk_directory"]),
            "M3": Semantic(artifact("semantic"), artifact("tokenizer"), config["dimension"], config["max_length"]),
            "M4": Matcher(config["dimension"], config["match_threshold"])}
