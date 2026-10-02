from pathlib import Path
import csv
from collections import defaultdict
root = Path(__file__).resolve().parent
with (root / "coding-table.csv").open() as f:
    codes = list(csv.DictReader(f))
extra = defaultdict(set)
with (root / "additional-applications.csv").open() as f:
    for row in csv.DictReader(f):
        extra[row["code"]].update(row["participant_labels"].split(";"))
with (root / "code-summary.csv").open("w") as f:
    w = csv.writer(f)
    w.writerow(["code", "label", "initial_participant_label", "additional_participant_labels", "status"])
    for row in codes:
        w.writerow([row["id"], row["label"], row["participant"], ";".join(sorted(extra[row["id"]])), row["status"]])
print("Summarized", len(codes), "retained codes")
