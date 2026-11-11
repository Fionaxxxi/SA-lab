"""Compute CER and evidence-linked classification scores from reviewed records."""
import argparse
import json
from pathlib import Path
from experiments.scripts.compute_metrics import edits, normalize

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("labels", type=Path, help="JSON records with reference_text, actual_text and matches")
args = cli.parse_args()
rows = json.loads(args.labels.read_text("utf-8"))
errors = characters = tp = fp = fn = correct = evidence_n = 0
for row in rows:
    reference, actual = normalize(row["reference_text"]), normalize(row["actual_text"])
    if not reference:
        raise ValueError("Empty reference transcript")
    characters += len(reference)
    errors += edits(reference, actual)
    for match in row["matches"]:
        expected, actual = match["expected_covered"], match["actual_covered"]
        tp += expected and actual
        fp += not expected and actual
        fn += expected and not actual
        if actual:
            evidence_n += 1
            correct += match["actual_evidence_sentence_id"] in match["accepted_evidence_sentence_ids"]
precision = tp / (tp + fp) if tp + fp else None
recall = tp / (tp + fn) if tp + fn else None
print(json.dumps({"recordings": len(rows), "reference_characters": characters,
                  "cer": errors / characters if characters else None, "precision": precision, "recall": recall,
                  "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                  "evidence_accuracy": correct / evidence_n if evidence_n else None}, indent=2))
