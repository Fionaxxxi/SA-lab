"""Run a labeled manifest through local real modules and export traceable events."""
import argparse
import base64
import json
from pathlib import Path
from time import perf_counter_ns
import uuid
import wave
from server.modules.integration import create_handlers

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("samples", type=Path)
cli.add_argument("--run-id", required=True)
cli.add_argument("--device-id", required=True)
cli.add_argument("--output", type=Path, required=True)
cli.add_argument("--repeats", type=int, default=1)
args = cli.parse_args()
if args.repeats < 1:
    cli.error("repeats must be positive")
handlers = create_handlers(strict=True)
manifest = json.loads(Path("models/manifest.json").read_text("utf-8"))
samples = json.loads(args.samples.read_text("utf-8"))
args.output.parent.mkdir(parents=True, exist_ok=True)
# Exclusive creation preserves original measurements when the command is retried.
with args.output.open("x", encoding="utf-8") as log:
    for repeat in range(args.repeats):
        for sample in samples:
            task_id = str(uuid.uuid4())
            common = {"event_schema_version": 1, "task_id": task_id, "attempt": 1, "run_id": args.run_id,
                      "device_id": args.device_id, "sample_id": sample["sample_id"], "mode": "LOCAL",
                      "plan_version": "python-local-v1", "model_version": manifest["model_version"],
                      "config_version": manifest["config_version"], "input_source": "IMPORT",
                      "effective_input": sample["effective_input"], "module_id": None, "executor": None,
                      "bytes_up": 0, "bytes_down": 0, "error_code": None, "audio_samples": None}
            def emit(event, status, elapsed_ms, **values):
                log.write(json.dumps(common | {"event": event, "status": status, "elapsed_ms": elapsed_ms} | values,
                                     ensure_ascii=False, allow_nan=False) + "\n")
                log.flush()
            started = perf_counter_ns()
            elapsed = lambda begin: (perf_counter_ns() - begin) // 1_000_000
            emit("TASK_SUBMITTED", "CREATED", 0)
            try:
                with wave.open(str(args.samples.parent / sample["wav_path"]), "rb") as audio:
                    if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                        raise ValueError("Unsupported WAV")
                    count = audio.getnframes()
                    if not 0 < count <= 960000:
                        raise ValueError("Invalid duration")
                    raw = audio.readframes(count)
                common["audio_samples"] = count
                emit("MODULE_END", "OK", elapsed(started), module_id="M0", executor="LOCAL")
                payload = {"audio": {"sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le",
                                     "sample_count": count, "pcm_b64": base64.b64encode(raw).decode()}}
                transcript = None
                for module in ("M1", "M2", "M3", "M4"):
                    node_start = perf_counter_ns()
                    try:
                        output = handlers[module](payload)
                    except Exception as error:
                        emit("MODULE_END", "ERROR", elapsed(node_start), module_id=module, executor="LOCAL",
                             error_code=getattr(error, "code", "INTERNAL_ERROR"))
                        raise
                    emit("MODULE_END", "OK", elapsed(node_start), module_id=module, executor="LOCAL")
                    payload = output
                    if module == "M2":
                        transcript = output["transcript"]
                        payload = output | {"keypoints": sample["keypoints"]}
                emit("MODULE_END", "OK", 0, module_id="M5", executor="LOCAL")
                emit("TASK_TERMINAL", "SUCCEEDED", elapsed(started))
                # This desktop runner has no phone UI. It deliberately has no FEEDBACK_VISIBLE event.
            except Exception as error:
                emit("TASK_TERMINAL", "FAILED", elapsed(started), error_code=getattr(error, "code", "INVALID_PAYLOAD"))
