"""Independent check: recompute the headline numbers from the processed corpus
and compare them with analysis.json and REPORT.md.

Exit code 0 = everything matches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dota_analysis import config, stats_utils  # noqa: E402


def main() -> None:
    corpus = pd.read_csv(config.PROC_DIR / "corpus.csv")
    result = json.loads((config.PROC_DIR / "analysis.json").read_text(encoding="utf-8"))
    report_text = (config.REPORT_DIR / "REPORT.md").read_text(encoding="utf-8")

    checks: list[tuple[str, bool, str]] = []

    n = len(corpus)
    k = int(corpus["is_complaint"].sum())
    share = k / n
    lo, hi = stats_utils.wilson_ci(k, n)

    checks.append(("corpus size", n == result["corpus"]["relevant"], f"{n}"))
    checks.append(("complaint count", k == result["corpus"]["complaints"], f"{k}"))
    checks.append(("complaint share",
                   abs(share - result["corpus"]["complaint_share"]) < 1e-12,
                   f"{share:.6f}"))
    checks.append(("wilson CI",
                   abs(lo - result["corpus"]["wilson"][0]) < 1e-6 and
                   abs(hi - result["corpus"]["wilson"][1]) < 1e-6,
                   f"{lo:.4f}–{hi:.4f}"))
    checks.append(("share rendered in report",
                   f"{share*100:.1f}%" in report_text,
                   f"{share*100:.1f}%"))

    by_src = corpus.groupby("source")["is_complaint"].agg(["size", "sum"])
    for src, row in by_src.iterrows():
        ref = result["corpus"]["by_source"].get(src)
        ok = ref is not None and int(row["sum"]) == ref["complaints"] and int(row["size"]) == ref["n"]
        checks.append((f"source: {src}", ok, f"n={int(row['size'])}, complaints={int(row['sum'])}"))

    missing_figs = []
    for name in result.get("figures", []) or []:
        p = config.FIG_DIR / name
        if not p.exists() or p.stat().st_size < 2000:
            missing_figs.append(name)
    if not result.get("figures"):
        for p in sorted(config.FIG_DIR.glob("*.png")):
            if p.stat().st_size < 2000:
                missing_figs.append(p.name)
    checks.append(("figures present", not missing_figs, ", ".join(missing_figs) or "ok"))

    checks.append(("report exists", len(report_text) > 5000, f"{len(report_text)} chars"))
    checks.append(("no NaN share", share == share, f"{share}"))

    width = max(len(c[0]) for c in checks)
    failed = 0
    for name, ok, detail in checks:
        status = "OK  " if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {name:<{width}}  {detail}")

    print()
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
