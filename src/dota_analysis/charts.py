from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
})

C_MAIN = "#c0392b"
C_ALT = "#2c3e50"
C_ACC = "#2980b9"
C_GREY = "#7f8c8d"
PALETTE = ["#c0392b", "#2980b9", "#27ae60", "#8e44ad", "#d35400", "#16a085", "#7f8c8d"]


def _months_axis(ax, labels: list[str], step: int = 6) -> None:
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step], rotation=45, ha="right")


def fig_monthly(corpus: pd.DataFrame, out: Path) -> None:
    rel = corpus[corpus["relevant"]].copy()
    if rel.empty:
        return
    pivot = rel.pivot_table(index="month", columns="source", values="id",
                            aggfunc="count", fill_value=0).sort_index()
    share = rel.groupby("month")["is_complaint"].mean().reindex(pivot.index)
    counts = rel.groupby("month").size().reindex(pivot.index)
    share = share.where(counts >= 20)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    bottom = np.zeros(len(pivot))
    for i, col in enumerate(pivot.columns):
        ax.bar(range(len(pivot)), pivot[col].values, bottom=bottom, label=col,
               color=PALETTE[i % len(PALETTE)], width=0.85)
        bottom += pivot[col].values
    ax.set_ylabel("Документов в выборке (шт.)")
    ax2 = ax.twinx()
    ax2.plot(range(len(share)), share.values * 100, color="black", lw=1.8, marker="o", ms=2.5,
             label="Доля жалоб, %")
    ax2.set_ylabel("Доля жалоб, %")
    ax2.set_ylim(0, 100)
    ax2.grid(False)
    _months_axis(ax, list(pivot.index))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, ncol=4, fontsize=8, loc="upper left")
    ax.set_title("Объём выборки по источникам и доля жалоб по месяцам")
    fig.savefig(out)
    plt.close(fig)


def fig_quarterly_ci(result: dict, out: Path) -> None:
    q = pd.DataFrame(result["series"]["quarterly"]).sort_values("quarter")
    if q.empty:
        return
    p = q["share"].values
    n = q["n"].values
    z = 1.96
    lo = (p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
    hi = (p + z * z / (2 * n) + z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
    fig, ax = plt.subplots(figsize=(11, 4.4))
    x = np.arange(len(q))
    ax.errorbar(x, p * 100, yerr=[(p - lo) * 100, (hi - p) * 100], fmt="o-", color=C_MAIN,
                ecolor=C_GREY, elinewidth=1, capsize=3, ms=4, lw=1.8,
                label="Доля жалоб, 95% ДИ Уилсона")
    if len(x) > 2:
        k = np.polyfit(x, p, 1)
        ax.plot(x, np.polyval(k, x) * 100, "--", color=C_ACC, lw=1.5,
                label=f"Линейный тренд: {k[0] * 100:+.2f} п.п./квартал")
    std = result["series"].get("quarterly_std") or []
    if std:
        smap = {r["quarter"]: r["share_std"] for r in std}
        ys = [smap.get(qq) for qq in q["quarter"]]
        if any(v is not None for v in ys):
            ax.plot(x, [v * 100 if v is not None else np.nan for v in ys], "s--",
                    color=C_ACC, ms=3, lw=1.3, label="Стандартизовано по источникам")
    ax.set_xticks(x)
    ax.set_xticklabels(q["quarter"], rotation=45, ha="right")
    ax.set_ylabel("Доля жалоб, %")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8)
    ax.set_title("Доля жалоб среди релевантных обсуждений по кварталам")
    for i, (yy, nn) in enumerate(zip(p * 100, n)):
        if i % 2 == 0:
            ax.annotate(f"n={nn}", (i, yy), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=6, color=C_GREY)
    fig.savefig(out)
    plt.close(fig)


def fig_players(result: dict, out: Path) -> None:
    rows = result["series"].get("monthly_players", [])
    if not rows:
        return
    df = pd.DataFrame(rows).dropna(subset=["avg_players"]).sort_values("month")
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.fill_between(range(len(df)), df["avg_players"] / 1000, color=C_ALT, alpha=0.18,
                    label="Средний онлайн, тыс.")
    ax.plot(range(len(df)), df["avg_players"] / 1000, color=C_ALT, lw=1.4)
    ax.set_ylabel("Средний онлайн за месяц, тыс. игроков")
    ax2 = ax.twinx()
    per = df["per_100k"].where(df["complaints"] >= 10)
    ax2.plot(range(len(df)), per, color=C_MAIN, lw=1.8, marker="o", ms=2.5,
             label="Жалоб на 100 тыс. среднего онлайна (n≥10)")
    ax2.set_ylabel("Жалоб на 100 тыс. среднего онлайна")
    ax2.grid(False)
    _months_axis(ax, list(df["month"]))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax.set_title("Онлайн Dota 2 (SteamCharts) и интенсивность жалоб")
    fig.savefig(out)
    plt.close(fig)


def fig_sources(result: dict, out: Path) -> None:
    src = result["corpus"]["by_source"]
    if not src:
        return
    names = list(src)
    shares = [src[s]["share"] * 100 for s in names]
    ns = [src[s]["n"] for s in names]
    err = [[(src[s]["share"] - src[s]["ci"][0]) * 100 for s in names],
           [(src[s]["ci"][1] - src[s]["share"]) * 100 for s in names]]
    order = np.argsort(shares)
    fig, ax = plt.subplots(figsize=(9, max(3, 0.6 * len(names) + 1.6)))
    ax.barh([names[i] for i in order], [shares[i] for i in order],
            xerr=[[err[0][i] for i in order], [err[1][i] for i in order]],
            color=C_ACC, alpha=0.85, capsize=3)
    for j, i in enumerate(order):
        ax.text(shares[i] + 1.5, j, f"{shares[i]:.1f}% (n={ns[i]})", va="center", fontsize=8)
    ax.set_xlabel("Доля жалоб, % (95% ДИ)")
    ax.set_xlim(0, 100)
    ax.set_title("Доля жалоб по источникам")
    fig.savefig(out)
    plt.close(fig)


def fig_themes(result: dict, out: Path) -> None:
    themes = result.get("themes", {})
    if not themes:
        return
    items = sorted(themes.items(), key=lambda kv: kv[1]["n"], reverse=True)[:8]
    names = [k for k, _ in items]
    ns = [v["n"] for _, v in items]
    shares = [v["complaint_share"] * 100 for _, v in items]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(names))
    ax.bar(x, ns, color=C_GREY, alpha=0.55, label="Документов")
    ax.set_ylabel("Документов")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20, ha="right")
    ax2 = ax.twinx()
    ax2.plot(x, shares, "o-", color=C_MAIN, label="Доля жалоб внутри темы, %")
    ax2.set_ylabel("Доля жалоб, %")
    ax2.set_ylim(0, 100)
    ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    ax.set_title("Тематика обсуждений и доля жалоб")
    fig.savefig(out)
    plt.close(fig)


def fig_years(result: dict, out: Path) -> None:
    years = result.get("years", {})
    if not years:
        return
    keys = sorted(years)
    fig, ax = plt.subplots(figsize=(8, 4))
    vals = [years[k]["share"] * 100 for k in keys]
    err = [[(years[k]["share"] - years[k]["ci"][0]) * 100 for k in keys],
           [(years[k]["ci"][1] - years[k]["share"]) * 100 for k in keys]]
    ax.bar(keys, vals, color=C_MAIN, alpha=0.85, capsize=3, yerr=err, error_kw={"ecolor": C_GREY})
    for i, k in enumerate(keys):
        ax.text(i, vals[i] + 3, f"{vals[i]:.1f}%\nn={years[k]['n']}", ha="center", fontsize=8)
    ax.set_ylabel("Доля жалоб, % (95% ДИ)")
    ax.set_ylim(0, 100)
    ax.set_title("Доля жалоб по годам")
    fig.savefig(out)
    plt.close(fig)


def fig_patches(result: dict, out: Path) -> None:
    ev = result.get("patch_events", {}).get("events", [])
    if not ev:
        return
    df = pd.DataFrame(ev).sort_values("date")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    colors = [C_MAIN if d > 0 else C_ACC for d in df["diff_pp"]]
    ax.barh(range(len(df)), df["diff_pp"], color=colors)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels([f"{r['date']}  {r['title'][:48]}" for _, r in df.iterrows()], fontsize=7)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Разница доли жалоб в окне ±14 дней vs. фон, п.п.")
    for i, (_, r) in enumerate(df.iterrows()):
        ax.text(r["diff_pp"] + (0.5 if r["diff_pp"] >= 0 else -0.5), i,
                f"p={r['p']:.3f}", va="center", ha="left" if r["diff_pp"] >= 0 else "right", fontsize=7)
    ax.set_title("Реакция на обновления, затрагивающие систему поведения")
    fig.savefig(out)
    plt.close(fig)


def fig_validation(result: dict, out: Path) -> None:
    v = result.get("validation", {})
    if v.get("status") != "ok":
        return
    m = v["metrics"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw={"width_ratios": [1, 1.2]})
    cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
    ax1.imshow(cm, cmap="Blues")
    labels = ["не жалоба", "жалоба"]
    ax1.set_xticks([0, 1], labels)
    ax1.set_yticks([0, 1], labels)
    ax1.set_xlabel("Классификатор")
    ax1.set_ylabel("Ручная разметка")
    for i in range(2):
        for j in range(2):
            ax1.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax1.grid(False)
    ax1.set_title(f"Матрица ошибок (n={m['n']})")
    ax2.axis("off")
    lines = [
        f"Чувствительность: {m['sensitivity']:.3f} [{m['sens_ci'][0]:.3f}; {m['sens_ci'][1]:.3f}]",
        f"Специфичность:   {m['specificity']:.3f} [{m['spec_ci'][0]:.3f}; {m['spec_ci'][1]:.3f}]",
        f"Точность (PPV):  {m['ppv']:.3f} [{m['ppv_ci'][0]:.3f}; {m['ppv_ci'][1]:.3f}]",
        f"F1:              {m['f1']:.3f}",
        f"Каппа Коэна:     {v['kappa']:.3f} [{v['kappa_ci'][0]:.3f}; {v['kappa_ci'][1]:.3f}]",
        "",
        f"Наблюдаемая доля:  {v['observed_prevalence'] * 100:.2f}%",
        f"Скорректированная: {v['corrected_prevalence'] * 100:.2f}%",
        f"Сдвиг: {v['correction_delta_pp']:+.2f} п.п.",
    ]
    ax2.text(0, 0.95, "\n".join(lines), va="top", fontsize=9, family="DejaVu Sans Mono")
    fig.suptitle("Валидация классификатора жалоб", fontsize=11)
    fig.savefig(out)
    plt.close(fig)


def fig_heatmap(corpus: pd.DataFrame, out: Path) -> None:
    if corpus.empty:
        return
    pivot = corpus.pivot_table(index="source", columns="month", values="id", aggfunc="count", fill_value=0)
    if pivot.shape[1] < 4:
        return
    fig, ax = plt.subplots(figsize=(12, 0.5 * len(pivot) + 1.4))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    step = max(1, pivot.shape[1] // 12)
    ax.set_xticks(range(0, pivot.shape[1], step))
    ax.set_xticklabels(pivot.columns[::step], rotation=45, ha="right", fontsize=7)
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="Документов")
    ax.set_title("Покрытие по источникам и месяцам")
    fig.savefig(out)
    plt.close(fig)


def build_all() -> list[str]:
    result = json.loads((config.PROC_DIR / "analysis.json").read_text(encoding="utf-8"))
    corpus_path = config.PROC_DIR / "documents_classified.csv"
    corpus = pd.read_csv(corpus_path) if corpus_path.exists() else pd.DataFrame()
    made = []
    figs = [
        ("fig_monthly.png", lambda p: fig_monthly(corpus, p)),
        ("fig_quarterly_ci.png", lambda p: fig_quarterly_ci(result, p)),
        ("fig_players.png", lambda p: fig_players(result, p)),
        ("fig_sources.png", lambda p: fig_sources(result, p)),
        ("fig_themes.png", lambda p: fig_themes(result, p)),
        ("fig_years.png", lambda p: fig_years(result, p)),
        ("fig_patches.png", lambda p: fig_patches(result, p)),
        ("fig_validation.png", lambda p: fig_validation(result, p)),
        ("fig_coverage.png", lambda p: fig_heatmap(corpus, p)),
    ]
    for name, fn in figs:
        path = config.FIG_DIR / name
        try:
            fn(path)
            if path.exists():
                made.append(name)
        except Exception as exc:  # pragma: no cover
            print(f"figure {name} failed: {exc}")
    return made


if __name__ == "__main__":
    print(build_all())
