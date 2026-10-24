from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config, db, stats_utils
from .classify import classify
from .text import MinHash, content_hash, detect_lang, is_probable_spam

CONDUCT_PATCH = (
    r"behavio|behaviour|conduct|communicat|commend|overwatch|low priority|"
    r"report(?:ing|s)? (?:system|and)|system of report|toxic|mute[ds]?|ban wave|banned accounts|поведен|"
    r"порядочн|вежливост|репорт|приоритет|токсич|мьют|мут"
)


def _month(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m")


def _quarter(ts: int) -> str:
    d = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def build_corpus(con) -> tuple[pd.DataFrame, dict]:
    docs = db.load_documents(con)
    if not docs.empty:
        docs = docs.sort_values(["id"]).reset_index(drop=True)
    meta: dict = {"raw_documents": int(len(docs))}
    if docs.empty:
        return docs, meta

    docs = docs[docs["created_utc"] > 0].copy()
    docs["date"] = pd.to_datetime(docs["created_utc"], unit="s", utc=True)
    docs["month"] = docs["date"].dt.strftime("%Y-%m")
    docs["quarter"] = (docs["date"].dt.year.astype(str) + "-Q" +
                        ((docs["date"].dt.month - 1) // 3 + 1).astype(str))
    docs["text"] = (docs["title"].fillna("") + ". " + docs["body"].fillna("")).str.strip()
    docs["lang"] = docs["text"].apply(detect_lang)
    docs = docs[docs["text"].str.len() >= 20]
    meta["after_length_filter"] = int(len(docs))

    docs = docs[docs["date"] >= pd.Timestamp(config.DATE_FROM, tz="UTC")]
    meta["after_date_filter"] = int(len(docs))

    spam = docs["text"].apply(is_probable_spam)
    meta["spam_removed"] = int(spam.sum())
    docs = docs[~spam].copy()

    # exact duplicates
    docs["chash"] = docs["text"].apply(content_hash)
    before = len(docs)
    docs = docs.drop_duplicates(subset=["chash"]).copy()
    meta["exact_duplicates_removed"] = int(before - len(docs))

    # near duplicates (same source, >=0.9 estimated Jaccard)
    mh = MinHash(perms=64, bands=16)
    keep = np.ones(len(docs), dtype=bool)
    sigs: dict[int, tuple] = {}
    docs = docs.reset_index(drop=True)
    for i, (_, row) in enumerate(docs.iterrows()):
        if len(row["text"]) < 80:
            continue
        sig = mh.signature(row["text"])
        candidates = mh.add(i, sig)
        for j in sorted(candidates):
            if not keep[j] or j not in sigs:
                continue
            if docs.at[j, "source"] != row["source"]:
                continue
            if MinHash.jaccard(sigs[j], sig) >= 0.9:
                keep[i] = False
                break
        if keep[i]:
            sigs[i] = sig
    meta["near_duplicates_removed"] = int((~keep).sum())
    docs = docs[keep].reset_index(drop=True)

    rows = []
    for _, r in docs.iterrows():
        c = classify(r["title"], (r["body"] or "")[:420], r["source_type"])
        rows.append(c.as_dict())
    cls = pd.DataFrame(rows, index=docs.index)
    docs = docs.drop(columns=["lang"])
    docs = pd.concat([docs, cls], axis=1)
    docs["is_complaint"] = (docs["stance"] == "complaint").astype(int)

    meta["final_documents"] = int(len(docs))
    meta["relevant_docs"] = int(docs["relevant"].sum())
    meta["date_min"] = docs["date"].min().strftime("%Y-%m-%d") if len(docs) else None
    meta["date_max"] = docs["date"].max().strftime("%Y-%m-%d") if len(docs) else None
    meta["languages"] = docs["lang"].value_counts().to_dict()
    meta["sources"] = docs["source"].value_counts().to_dict()
    meta["source_types"] = docs["source_type"].value_counts().to_dict()
    return docs, meta


def _agg_monthly(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("month")
    out = pd.DataFrame({
        "n": g.size(),
        "complaints": g["is_complaint"].sum(),
        "relevant": g["relevant"].sum(),
    })
    out["share"] = out["complaints"] / out["n"].replace(0, np.nan)
    out = out.reset_index().sort_values("month")
    return out


def analyse(docs: pd.DataFrame, players: pd.DataFrame, events: pd.DataFrame,
            serp: pd.DataFrame, meta: dict) -> dict:
    rel = docs[docs["relevant"]].copy()
    result: dict = {"meta": meta}
    if rel.empty:
        result["error"] = "no relevant documents"
        return result

    result["corpus"] = {
        "relevant": int(len(rel)),
        "complaints": int(rel["is_complaint"].sum()),
        "complaint_share": float(rel["is_complaint"].mean()),
        "wilson": stats_utils.wilson_ci(int(rel["is_complaint"].sum()), len(rel)),
        "by_source": {},
        "by_lang": {},
        "by_stance": rel["stance"].value_counts().to_dict(),
        "by_theme": rel["theme"].value_counts().to_dict(),
    }
    for src, g in rel.groupby("source"):
        k = int(g["is_complaint"].sum())
        lo, hi = stats_utils.wilson_ci(k, len(g))
        result["corpus"]["by_source"][src] = {
            "n": int(len(g)), "complaints": k, "share": float(k / len(g)),
            "ci": (float(lo), float(hi)),
        }
    for lang, g in rel.groupby("lang"):
        k = int(g["is_complaint"].sum())
        lo, hi = stats_utils.wilson_ci(k, len(g))
        result["corpus"]["by_lang"][lang] = {
            "n": int(len(g)), "complaints": k,
            "share": float(k / len(g)) if len(g) else 0.0,
            "ci": (float(lo), float(hi)),
        }

    # clustered CI (comments by the same author are not independent)
    de = stats_utils.design_effect(
        rel["is_complaint"].tolist(),
        (rel["source"] + "|" + rel["author"].fillna("")).tolist(),
    )
    result["design"] = de.__dict__
    lo, hi = stats_utils.wilson_ci_clustered(int(rel["is_complaint"].sum()), len(rel), de.deff)
    result["corpus"]["wilson_clustered"] = (float(lo), float(hi))
    result["corpus"]["deff"] = de.deff

    # monthly / quarterly series
    monthly = _agg_monthly(rel)
    quarterly = rel.groupby("quarter").agg(n=("is_complaint", "size"),
                                           complaints=("is_complaint", "sum")).reset_index()
    quarterly["share"] = quarterly["complaints"] / quarterly["n"]
    # source-standardised quarterly series (removes shifts in platform mix)
    qs = rel.groupby(["quarter", "source"]).agg(n=("is_complaint", "size"),
                                                  k=("is_complaint", "sum")).reset_index()
    w_src = rel["source"].value_counts(normalize=True).to_dict()
    std_rows = []
    for qtr, g in qs.groupby("quarter"):
        present = {r["source"]: r for _, r in g.iterrows()}
        wsum = sum(w_src.get(s, 0) for s in present)
        if wsum <= 0:
            continue
        p_std = 0.0
        var = 0.0
        for src, r in present.items():
            w = w_src.get(src, 0) / wsum
            p_s = r["k"] / r["n"] if r["n"] else 0.0
            p_std += w * p_s
            if r["n"] > 1:
                var += (w ** 2) * p_s * (1 - p_s) / r["n"]
        std_rows.append({"quarter": qtr, "share_std": p_std,
                         "se": math.sqrt(max(var, 0.0)),
                         "sources": len(present), "n": int(g["n"].sum())})
    std = pd.DataFrame(std_rows).sort_values("quarter") if std_rows else pd.DataFrame()
    if not std.empty:
        xs2 = list(range(len(std)))
        result["trend_std"] = {
            "mann_kendall": stats_utils.mann_kendall(std["share_std"].tolist()),
            "ols": stats_utils.ols_slope(xs2, std["share_std"].tolist()),
            "bootstrap": stats_utils.bootstrap_slope_ci(xs2, std["share_std"].tolist()),
            "first": float(std["share_std"].iloc[0]),
            "last": float(std["share_std"].iloc[-1]),
        }
    result["series"] = {
        "monthly": monthly.to_dict(orient="records"),
        "quarterly": quarterly.to_dict(orient="records"),
        "quarterly_std": std.to_dict(orient="records") if not std.empty else [],
    }

    # players join (monthly average concurrent)
    if not players.empty:
        pl = players.copy()
        pl["month"] = pl["month"]
        merged = monthly.merge(pl[["month", "avg_players"]], on="month", how="left")
        merged["per_100k"] = merged["complaints"] / merged["avg_players"] * 100000
        result["series"]["monthly_players"] = merged.to_dict(orient="records")
        valid = merged.dropna(subset=["avg_players"])
        if len(valid) >= 6:
            rho, p = stats_utils.stats.spearmanr(valid["share"], valid["avg_players"])
            result["players_corr"] = {"rho": round(float(rho), 3), "p": float(p), "n": int(len(valid))}
            # Calculate month-over-month changes on the full SteamCharts series
            # before restricting to months that have enough discussion data.
            pl_changes = pl.sort_values("month").copy()
            pl_changes["chg"] = pl_changes["avg_players"].pct_change()
            v = valid[valid["n"] >= 20].merge(
                pl_changes[["month", "chg"]], on="month", how="left")
            dipped = v[v["chg"] <= -0.05]
            other = v[v["chg"] > -0.05]
            if len(dipped) >= 3 and len(other) >= 3:
                k1, n1 = int(dipped["complaints"].sum()), int(dipped["n"].sum())
                k0, n0 = int(other["complaints"].sum()), int(other["n"].sum())
                result["online_dips"] = {
                    "months": [{"month": r["month"], "change_pct": round(r["chg"] * 100, 1),
                                "n": int(r["n"]), "share": round(r["share"], 4)}
                               for _, r in dipped.iterrows()],
                    "dip_share": k1 / n1 if n1 else None,
                    "other_share": k0 / n0 if n0 else None,
                    "test": stats_utils.proportion_test(k1, n1, k0, n0),
                }

    # trend tests on quarterly complaint share
    q = quarterly.sort_values("quarter")
    mk = stats_utils.mann_kendall(q["share"].tolist())
    xs = list(range(len(q)))
    slope = stats_utils.ols_slope(xs, q["share"].tolist())
    boot = stats_utils.bootstrap_slope_ci(xs, q["share"].tolist())
    result["trend"] = {
        "mann_kendall": mk,
        "ols_per_quarter": slope,
        "bootstrap_ci": boot,
        "first_share": float(q["share"].iloc[0]) if len(q) else None,
        "last_share": float(q["share"].iloc[-1]) if len(q) else None,
        "delta_pp": float((q["share"].iloc[-1] - q["share"].iloc[0]) * 100) if len(q) else None,
    }

    # trend on platforms with continuous coverage (GitHub + Steam)
    core = rel[rel["source"].isin(["GitHub (Dota 2 tracker)", "Steam Community"])]
    core_q = core.groupby("quarter").agg(n=("is_complaint", "size"),
                                           k=("is_complaint", "sum")).reset_index().sort_values("quarter")
    if len(core_q) >= 8:
        core_q["share"] = core_q["k"] / core_q["n"]
        xs3 = list(range(len(core_q)))
        result["trend_core"] = {
            "sources": sorted(core["source"].unique().tolist()),
            "quarters": int(len(core_q)),
            "n": int(len(core)),
            "mann_kendall": stats_utils.mann_kendall(core_q["share"].tolist()),
            "ols": stats_utils.ols_slope(xs3, core_q["share"].tolist()),
            "bootstrap": stats_utils.bootstrap_slope_ci(xs3, core_q["share"].tolist()),
            "first": float(core_q["share"].iloc[0]),
            "last": float(core_q["share"].iloc[-1]),
        }

    # year comparison
    rel["year"] = rel["date"].dt.year
    years = {}
    for y, g in rel.groupby("year"):
        k = int(g["is_complaint"].sum())
        lo, hi = stats_utils.wilson_ci(k, len(g))
        years[str(y)] = {"n": int(len(g)), "complaints": k, "share": float(k / len(g)),
                         "ci": (float(lo), float(hi))}
    result["years"] = years
    year_list = sorted(years)
    if len(year_list) >= 2:
        a, b = year_list[0], year_list[-1]
        result["first_vs_last_year"] = stats_utils.proportion_test(
            years[b]["complaints"], years[b]["n"], years[a]["complaints"], years[a]["n"])

    # source comparison (chi-square)
    if rel["source"].nunique() >= 2:
        table = pd.crosstab(rel["source"], rel["is_complaint"])
        if table.shape[1] == 2 and table.shape[0] >= 2:
            from scipy import stats as st
            chi2, p, dof, _ = st.chi2_contingency(table.values, correction=False)
            result["source_test"] = {"chi2": round(float(chi2), 3), "dof": int(dof),
                                     "p": float(p),
                                     "cramers_v": round(float(math.sqrt(chi2 / (table.values.sum() * (min(table.shape) - 1)))), 3)}

    # themes
    theme_stats = {}
    for t, g in rel.groupby("theme"):
        theme_stats[t] = {"n": int(len(g)), "share_of_corpus": round(len(g) / len(rel), 4),
                          "complaint_share": round(float(g["is_complaint"].mean()), 4)}
    result["themes"] = theme_stats

    # event study around conduct patches
    result["patch_events"] = _event_study(rel, events)

    # validation
    result["validation"] = _validation(rel)

    # sensitivity
    result["sensitivity"] = _sensitivity(rel)

    # coverage table
    result["coverage"] = _coverage(docs, rel, serp)

    # reproducibility hashes
    result["hashes"] = {
        "corpus_sha256": _df_hash(rel),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return result


def _event_study(rel: pd.DataFrame, events: pd.DataFrame) -> dict:
    if events.empty:
        return {"events": [], "note": "no events"}
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date_utc"], unit="s", utc=True)
    ev = ev[ev["title"].str.contains(CONDUCT_PATCH, case=False, na=False)]
    ev = ev.sort_values("date")
    out = []
    used: list[pd.Timestamp] = []
    for _, e in ev.iterrows():
        if any(abs((e["date"] - u).days) < 14 for u in used):
            continue
        used.append(e["date"])
        win = rel[(rel["date"] >= e["date"] - pd.Timedelta(days=14)) &
                  (rel["date"] <= e["date"] + pd.Timedelta(days=14))]
        base = rel[~rel.index.isin(win.index)]
        if len(win) < 10 or len(base) < 10:
            continue
        k1, n1 = int(win["is_complaint"].sum()), len(win)
        k0, n0 = int(base["is_complaint"].sum()), len(base)
        test = stats_utils.proportion_test(k1, n1, k0, n0)
        out.append({
            "date": e["date"].strftime("%Y-%m-%d"),
            "title": e["title"][:160],
            "window_n": n1, "window_share": round(k1 / n1, 4),
            "baseline_share": round(k0 / n0, 4),
            "diff_pp": round((k1 / n1 - k0 / n0) * 100, 2),
            "p": test["p"],
        })
    return {"events": out, "n_events": len(out)}


def _validation(rel: pd.DataFrame) -> dict:
    path = config.VAL_DIR / "labels.csv"
    if not path.exists():
        return {"status": "no labels", "n": 0}
    lab = pd.read_csv(path)
    if "label" not in lab or lab.empty:
        return {"status": "no labels", "n": 0}
    lab = lab.dropna(subset=["label"]).drop(columns=["stance", "source"], errors="ignore")
    merged = lab.merge(rel[["id", "is_complaint", "source"]], on="id", how="inner")
    if len(merged) < 20:
        return {"status": "too few labelled documents", "n": int(len(merged))}
    y_true = merged["label"].astype(int).tolist()
    y_pred = merged["is_complaint"].astype(int).tolist()
    raw_metrics = stats_utils.sens_spec(y_true, y_pred)
    source_population = rel["source"].value_counts().to_dict()
    weighted = stats_utils.weighted_validation_metrics(
        y_true, y_pred, merged["source"].astype(str).tolist(), source_population)
    m = dict(raw_metrics)
    for key in ("sensitivity", "specificity", "ppv", "npv", "accuracy", "f1"):
        if key in weighted:
            m[key] = weighted[key]
    if "sensitivity_ci" in weighted:
        m["sens_ci"] = weighted["sensitivity_ci"]
        m["spec_ci"] = weighted["specificity_ci"]
        m["ppv_ci"] = weighted["ppv_ci"]
    kappa = weighted.get("kappa", stats_utils.cohen_kappa(y_true, y_pred))
    klo, khi = weighted.get("kappa_ci", stats_utils.kappa_ci(y_true, y_pred))
    p_obs = float(rel["is_complaint"].mean())
    corrected = stats_utils.rogan_gladen(p_obs, m["sensitivity"], m["specificity"])

    # Design-based prevalence from the proportionate source-stratified sample.
    # This estimate does not depend on classifier accuracy on the corpus.
    N = len(rel)
    n_by = rel["source"].value_counts().to_dict()
    p_str = 0.0
    var = 0.0
    strata = []
    for source, g in merged.groupby("source"):
        n_h = len(g)
        N_h = int(n_by.get(source, 0))
        if n_h == 0 or N_h == 0:
            continue
        p_h = float(g["label"].mean())
        w = N_h / N
        f = n_h / N_h
        p_str += w * p_h
        if n_h > 1:
            var += (w ** 2) * (1 - f) * p_h * (1 - p_h) / (n_h - 1)
        strata.append({"source": source, "N_h": N_h, "n_h": n_h, "p_h": round(p_h, 4),
                       "weight": round(w, 4)})
    se = math.sqrt(max(var, 0.0))
    leave_one_source_out = []
    for omitted in strata:
        remaining = [x for x in strata if x["source"] != omitted["source"]]
        remaining_n = sum(x["N_h"] for x in remaining)
        if remaining_n:
            p_loo = sum(x["N_h"] * x["p_h"] for x in remaining) / remaining_n
            leave_one_source_out.append({"omitted": omitted["source"],
                                         "prevalence": p_loo,
                                         "delta_pp": (p_loo - p_str) * 100})
    max_loo_delta_pp = max((abs(x["delta_pp"]) for x in leave_one_source_out), default=0.0)
    strat = {"prevalence": p_str, "se": se,
             "ci": (max(0.0, p_str - 1.96 * se), min(1.0, p_str + 1.96 * se)),
             "strata": strata,
             "leave_one_source_out": leave_one_source_out,
             "max_loo_delta_pp": max_loo_delta_pp}

    return {
        "status": "ok", "n": m["n"], "metrics": m, "raw_metrics": raw_metrics,
        "weighting": "source post-stratification to current corpus counts",
        "kappa": kappa,
        "kappa_ci": (klo, khi), "observed_prevalence": p_obs,
        "corrected_prevalence": corrected,
        "correction_delta_pp": (corrected - p_obs) * 100,
        "design_based": strat,
    }


def _sensitivity(rel: pd.DataFrame) -> dict:
    out = {}
    base = float(rel["is_complaint"].mean())
    out["base_share"] = base
    for src in rel["source"].unique():
        sub = rel[rel["source"] != src]
        k, n = int(sub["is_complaint"].sum()), len(sub)
        out[f"without_{src}"] = {"n": n, "share": k / n if n else float("nan"),
                                 "delta_pp": (k / n - base) * 100 if n else float("nan")}
    ru = rel[rel["lang"] == "ru"]
    en = rel[rel["lang"] == "en"]
    if len(ru) and len(en):
        out["ru_vs_en"] = stats_utils.proportion_test(int(ru["is_complaint"].sum()), len(ru),
                                                      int(en["is_complaint"].sum()), len(en))
    posts = rel[rel["source_type"].isin(["post", "issue", "thread_op"])]
    comments = rel[~rel["source_type"].isin(["post", "issue", "thread_op"])]
    if len(posts) and len(comments):
        out["posts_vs_comments"] = stats_utils.proportion_test(
            int(posts["is_complaint"].sum()), len(posts),
            int(comments["is_complaint"].sum()), len(comments))
    return out


def _coverage(docs: pd.DataFrame, rel: pd.DataFrame, serp: pd.DataFrame) -> dict:
    out: dict = {"by_source": {}, "serp": {}, "months": {}}
    for src, g in docs.groupby("source"):
        months = g["month"].nunique()
        out["by_source"][src] = {
            "docs": int(len(g)),
            "relevant": int(g["relevant"].sum()) if "relevant" in g else 0,
            "first": g["date"].min().strftime("%Y-%m-%d"),
            "last": g["date"].max().strftime("%Y-%m-%d"),
            "months_with_data": int(months),
        }
    if not serp.empty:
        for prov, g in serp.groupby("provider"):
            blocked = int(g["blocked"].sum())
            out["serp"][prov] = {
                "queries": int(g["query"].nunique()),
                "blocked_queries": blocked,
                "results": int((g["blocked"] == 0).sum()),
                "status": "blocked" if blocked else "ok",
            }
    total_months = max(1, docs["month"].nunique())
    for src, g in docs.groupby("source"):
        out["months"][src] = round(g["month"].nunique() / total_months, 3)
    return out


def _df_hash(df: pd.DataFrame) -> str:
    import hashlib
    cols = ["id", "created_utc", "raw" if "raw" in df.columns else "text"]
    payload = df[cols].sort_values("id").to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _csv_export_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Trim trailing horizontal whitespace in derived CSV text fields only.

    The raw JSONL exports keep the original source text. This makes Git diffs
    and spreadsheet exports cleaner without changing analysis inputs.
    """
    out = df.copy()
    for col in out.select_dtypes(include=["object"]).columns:
        out[col] = out[col].map(
            lambda value: "\n".join(line.rstrip(" \t") for line in value.split("\n"))
            if isinstance(value, str) else value
        )
    return out


def main() -> None:
    con = db.connect()
    docs, meta = build_corpus(con)
    players = pd.read_sql_query("SELECT * FROM players", con)
    events = pd.read_sql_query("SELECT * FROM events", con)
    serp = pd.read_sql_query("SELECT * FROM serp", con)
    result = analyse(docs, players, events, serp, meta)
    out = config.PROC_DIR / "analysis.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    if not docs.empty:
        _csv_export_frame(docs).to_csv(
            config.PROC_DIR / "documents_classified.csv", index=False, encoding="utf-8")
        _csv_export_frame(docs[docs["relevant"]]).to_csv(
            config.PROC_DIR / "corpus.csv", index=False, encoding="utf-8")
    print(json.dumps({"documents": len(docs), "relevant": int(docs["relevant"].sum()) if not docs.empty else 0,
                      "analysis": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
