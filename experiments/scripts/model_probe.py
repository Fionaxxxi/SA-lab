"""Measure model startup and record real tokenizer/tensor invariants."""
import argparse
import gc
import json
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from server.modules.semantic import Semantic

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("--models", type=Path, default=Path("models"))
cli.add_argument("--output", type=Path, required=True)
args = cli.parse_args()
manifest = json.loads((args.models / "manifest.json").read_text("utf-8"))
artifact = lambda key: args.models / manifest["artifacts"][key]["path"]
config = manifest["config"]
texts = ["先调查居民需求", "面向老年居民讲解诈骗案例", "活动后回访评估宣传效果"]
observations = []
for cold in range(5):
    started = perf_counter_ns()
    encoder = Semantic(artifact("semantic"), artifact("tokenizer"), config["dimension"], config["max_length"])
    load_ms = (perf_counter_ns() - started) / 1e6
    runs = 5 if cold == 0 else 1
    for index in range(runs):
        started = perf_counter_ns()
        vectors = [encoder.vector(text) for text in texts]
        elapsed = (perf_counter_ns() - started) / 1e6
        for vector in vectors:
            assert len(vector) == config["dimension"]
            assert abs(np.linalg.norm(vector) - 1) <= 1e-5
        observations.append({"model_instance_index": cold, "iteration": index, "load_ms": load_ms,
                             "inference_ms": elapsed, "token_ids": [encoder.tokens(text) for text in texts],
                             "vectors_first8": [vector[:8] for vector in vectors],
                             "norms": [float(np.linalg.norm(vector)) for vector in vectors],
                             "cosine": np.asarray(vectors).dot(np.asarray(vectors).T).tolist()})
    del encoder
    gc.collect()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({"model_version": manifest["model_version"],
                                   "config_version": manifest["config_version"],
                                   "texts": texts, "observations": observations}, ensure_ascii=False, indent=2) + "\n", "utf-8")
