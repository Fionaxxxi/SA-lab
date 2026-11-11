"""Compare observed local/remote module outputs with a fixed tolerance."""
import argparse
import json
from pathlib import Path

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("local", type=Path)
cli.add_argument("remote", type=Path)
cli.add_argument("--tolerance", type=float, default=0.01)
args = cli.parse_args()
if args.tolerance < 0:
    cli.error("tolerance must be nonnegative")
left, right = [json.loads(path.read_text("utf-8")) for path in (args.local, args.remote)]
differences = []


def compare(a, b, path="$"):
    if isinstance(a, bool) or isinstance(b, bool):
        if a != b:
            differences.append({"path": path, "local": a, "remote": b})
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        import math
        if not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > args.tolerance:
            differences.append({"path": path, "local": a, "remote": b})
    elif isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            differences.append({"path": path, "reason": "Different fields"})
        for key in a.keys() & b.keys():
            compare(a[key], b[key], path + "." + key)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            differences.append({"path": path, "reason": "Different lengths"})
        for index, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}[{index}]")
    elif a != b:
        differences.append({"path": path, "local": a, "remote": b})


compare(left, right)
print(json.dumps({"tolerance": args.tolerance, "differences": differences}, ensure_ascii=False, indent=2))
raise SystemExit(bool(differences))
