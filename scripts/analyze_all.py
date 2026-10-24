"""Run the whole analysis: classify -> statistics -> figures -> REPORT.md."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dota_analysis import analyze, charts, db, report  # noqa: E402


def main() -> None:
    analyze.main()

    # figures read analysis.json and the classified corpus
    made = charts.build_all()
    print(f"figures: {len(made)} -> {', '.join(made)}")

    report.main()

    con = db.connect()
    print("db counts:", db.table_counts(con))


if __name__ == "__main__":
    main()
