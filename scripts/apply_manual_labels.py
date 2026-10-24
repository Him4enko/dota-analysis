"""Apply the completed manual coding to sample_to_label.csv.

This script is intentionally explicit so the labels can be independently
reviewed against the sample and docs/CODEBOOK.md.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_analysis import config


LABELS = [
    0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0,
    1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1,
    0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1,
    1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0,
    0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1,
    1, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1,
]
EXPECTED_SAMPLE_SHA256 = "3810e28c0df831fa1541fb210e2934f762b20cd8740e7f141675b83342d33d53"


def main() -> None:
    sample = pd.read_csv(config.VAL_DIR / "sample_to_label.csv")
    if len(sample) != len(LABELS):
        raise SystemExit(f"Expected {len(LABELS)} sample rows; found {len(sample)}")
    sample_hash = hashlib.sha256("\n".join(sample["id"].astype(str)).encode("utf-8")).hexdigest()
    if sample_hash != EXPECTED_SAMPLE_SHA256:
        raise SystemExit("The validation sample has changed; refusing to attach labels to different documents")
    out = sample[["id", "source", "lang", "title", "body_short"]].copy()
    out["label"] = LABELS
    out["notes"] = ""
    path = config.VAL_DIR / "labels.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(out)} manual labels ({sum(LABELS)} complaints) to {path}")


if __name__ == "__main__":
    main()
