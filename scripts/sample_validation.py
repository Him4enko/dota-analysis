"""Draw a proportionate, source-stratified random validation sample.

Creates data/validation/sample_to_label.csv. Fill the `label` column with
1 = complaint, 0 = not a complaint, then save as data/validation/labels.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dota_analysis import config  # noqa: E402


def _proportionate_allocation(counts: pd.Series, sample_size: int) -> dict[str, int]:
    exact = counts / counts.sum() * sample_size
    allocation = exact.apply(int).to_dict()
    remainder = sample_size - sum(allocation.values())
    order = (exact - exact.apply(int)).sort_values(ascending=False).index
    for source in order[:remainder]:
        allocation[source] += 1
    return allocation


def main(sample_size: int = 120, seed: int = 20261024) -> None:
    src = config.PROC_DIR / "corpus.csv"
    if not src.exists():
        raise SystemExit("run scripts/analyze_all.py first")
    df = pd.read_csv(src)
    if len(df) < sample_size:
        sample_size = len(df)

    counts = df["source"].value_counts()
    allocation = _proportionate_allocation(counts, sample_size)
    parts = []
    for i, (source, n) in enumerate(sorted(allocation.items())):
        part = df[df["source"] == source].sample(n=n, random_state=seed + i)
        parts.append(part)
    sample = pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)
    sample["body_short"] = sample["body"].fillna("").str.slice(0, 420).map(
        lambda text: "\n".join(line.rstrip(" \t") for line in text.split("\n")))
    out = sample[["id", "source", "lang", "title", "body_short"]].copy()
    out["label"] = ""
    out["notes"] = ""
    path = config.VAL_DIR / "sample_to_label.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"sample: {len(out)} rows -> {path}")
    print(f"source allocation: {allocation}")


if __name__ == "__main__":
    main()
