"""Aggregate observed task events without counting retries as extra tasks."""
import argparse
import csv
import json
import math
import unicodedata
from collections import defaultdict
from pathlib import Path


def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * p
    left = int(index)
    return ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (index - left)


def normalize(text):
    return "".join(x for x in text if not x.isspace() and not unicodedata.category(x).startswith("P"))


def edits(reference, actual):
    previous = list(range(len(actual) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, observed in enumerate(actual, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (expected != observed)))
        previous = current
    return previous[-1]


def aggregate(rows):
    terminals, visible = {}, {}
    for row in rows:
        key = tuple(row[k] for k in ("run_id", "device_id", "task_id"))
        if row["event"] in ("TASK_TERMINAL", "FEEDBACK_VISIBLE"):
            mapping = terminals if row["event"] == "TASK_TERMINAL" else visible
            if key in mapping and mapping[key] != row:
                raise ValueError(f"Conflicting terminal or visible event: {key}")
            mapping[key] = row
    groups = defaultdict(list)
    for key, row in terminals.items():
        groups[tuple(row[k] for k in ("run_id", "device_id", "mode", "input_source"))].append((key, row))
    result = []
    for group, tasks in sorted(groups.items()):
        valid = [(key, row) for key, row in tasks if row.get("effective_input") is True]
        success = [(key, row) for key, row in valid if row["status"] == "SUCCEEDED"]
        delays = [visible[key]["elapsed_ms"] for key, _ in success if key in visible and visible[key]["elapsed_ms"] is not None]
        rtf = [row["elapsed_ms"] / (row["audio_samples"] / 16000 * 1000) for _, row in success
               if row.get("audio_samples") and row.get("elapsed_ms") is not None]
        p50, p90, p99 = [percentile(delays, p) for p in (0.5, 0.9, 0.99)]
        result.append(dict(zip(("run_id", "device_id", "mode", "input_source"), group)) | {
            "observed_tasks": len(tasks), "effective_tasks": len(valid), "successful_tasks": len(success),
            "unknown_effective_input": sum(row.get("effective_input") is None for _, row in tasks),
            "completion_rate": len(success) / len(valid) if valid else None,
            "latency_n": len(delays), "p50_ms": p50, "p90_ms": p90, "p99_ms": p99,
            "jitter_ms": p90 - p50 if p90 is not None else None,
            "rtf_p90": percentile(rtf, 0.9),
            "failed": sum(row["status"] == "FAILED" for _, row in valid),
            "cancelled": sum(row["status"] == "CANCELLED" for _, row in valid),
            "interrupted": sum(row["status"] == "INTERRUPTED" for _, row in valid),
        })
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("events", nargs="+", type=Path)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--plot", action="store_true")
    args = cli.parse_args()
    rows = [json.loads(line) for path in args.events for line in path.read_text("utf-8").splitlines() if line.strip()]
    records = aggregate(rows)
    if not records:
        raise SystemExit("No terminal events")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        valid = [row for row in records if row["p90_ms"] is not None]
        if valid:
            plt.bar(range(len(valid)), [row["p90_ms"] for row in valid])
            plt.xticks(range(len(valid)), [f'{row["device_id"]}/{row["mode"]}' for row in valid], rotation=30)
            plt.ylabel("Complete feedback P90 (ms)")
            plt.tight_layout()
            plt.savefig(args.output.with_suffix(".png"), dpi=160)
            plt.close()


if __name__ == "__main__":
    main()
