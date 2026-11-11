"""Verify each module's own files before registering it with the gateway."""
import hashlib
import json
import logging
import math
import os
from pathlib import Path

from server.gateway.protocol import ProtocolError
from server.modules.asr import Asr
from server.modules.semantic import Semantic
from server.modules.vad import Vad
from server.modules.match import Matcher

LOG = logging.getLogger(__name__)
MODULES = ("M1", "M2", "M3", "M4")


def load_registry(root=None):
    """Load one manifest snapshot and register only independently valid modules."""
    root = Path(root or os.environ.get("SA_MODEL_ROOT", "models")).resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text("utf-8"))
        config, artifacts = manifest["config"], manifest["artifacts"]
        if not isinstance(artifacts, dict) or not all(
            isinstance(manifest[k], str) and manifest[k] for k in ("model_version", "config_version")
        ):
            raise ValueError("Invalid manifest")
        if (type(config["dimension"]) is not int or config["dimension"] != 384
                or type(config["max_length"]) is not int or not 3 <= config["max_length"] <= 128
                or config["pooling"] != "mean" or config["normalize"] != "L2"):
            raise ValueError("Unsupported encoding configuration")
        for key, low in (("vad_threshold", 0), ("match_threshold", 0)):
            value = config[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= 1:
                raise ValueError("Invalid threshold")
    except (OSError, ValueError, KeyError, TypeError):
        return None, {}, {module: "INVALID_OR_MISSING_MANIFEST" for module in MODULES}

    def location(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Path outside model directory")
        return path

    def verify(key):
        descriptor = artifacts[key]
        path = location(descriptor["path"])
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != descriptor["sha256"]:
            raise ValueError("Model file hash mismatch")
        return path

    def load_asr():
        directory = location(manifest["vosk_directory"])
        files = {location(item["path"]): key for key, item in artifacts.items()
                 if Path(item["path"]).is_relative_to(Path(manifest["vosk_directory"]))}
        if not files or any(path not in files for path in directory.rglob("*") if path.is_file()):
            raise ValueError("Unverified Vosk file")
        for key in files.values():
            verify(key)
        if directory / "am/final.mdl" not in files:
            raise ValueError("Missing Vosk acoustic model")
        return Asr(directory)

    builders = {
        "M1": lambda: Vad(verify("vad"), config["vad_threshold"]),
        "M2": load_asr,
        "M3": lambda: Semantic(verify("semantic"), verify("tokenizer"),
                               config["dimension"], config["max_length"]),
        "M4": lambda: Matcher(config["dimension"], config["match_threshold"]),
    }
    handlers, errors = {}, {}
    for module, build in builders.items():
        try:
            handlers[module] = build()
        except Exception as error:
            errors[module] = type(error).__name__
            LOG.warning("%s unavailable (%s)", module, type(error).__name__)
    return manifest, handlers, errors


def create_handlers(*, strict=False):
    _, handlers, errors = load_registry()
    if strict and errors:
        raise ProtocolError("MODEL_UNAVAILABLE", "Unavailable modules: " + ",".join(errors))
    return handlers
