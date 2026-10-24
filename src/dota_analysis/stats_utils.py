from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    if lo < 1e-12:
        lo = 0.0
    if hi > 1 - 1e-12:
        hi = 1.0
    return (lo, hi)


def fpc_halfwidth(lo: float, hi: float, n: int, population: int | None) -> float:
    """Finite population correction applied to a CI half-width."""
    half = (hi - lo) / 2
    if not population or population <= n or n <= 0:
        return half
    return half * math.sqrt(max(0.0, (population - n) / (population - 1)))


def wilson_ci_fpc(k: int, n: int, population: int | None, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n if n else 0.0
    lo, hi = wilson_ci(k, n, z)
    half = fpc_halfwidth(lo, hi, n, population)
    return (max(0.0, p - half), min(1.0, p + half))


@dataclass
class DesignEffect:
    icc: float
    mean_cluster: float
    deff: float
    clusters: int
    effective_n: float


def design_effect(values: list[int], clusters: list[str]) -> DesignEffect:
    """One-way ANOVA estimate of the intra-cluster correlation (ICC) for a
    binary outcome, and the resulting design effect for clustered data."""
    df = {}
    for v, c in zip(values, clusters):
        df.setdefault(c, []).append(float(v))
    groups = [g for g in df.values() if g]
    n = sum(len(g) for g in groups)
    k = len(groups)
    if n == 0 or k < 2:
        return DesignEffect(0.0, 1.0, 1.0, k, float(n))
    grand = sum(sum(g) for g in groups) / n
    ssb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups)
    msb = ssb / (k - 1)
    msw = ssw / (n - k) if n > k else 0.0
    mbar = n / k
    denom = msb + (mbar - 1) * msw
    rho = (msb - msw) / denom if denom > 0 else 0.0
    rho = max(0.0, min(1.0, rho))
    deff = 1 + (mbar - 1) * rho
    return DesignEffect(round(rho, 4), round(mbar, 2), round(deff, 3), k,
                        round(n / deff, 1) if deff else float(n))


def wilson_ci_clustered(k: int, n: int, deff: float, z: float = 1.959963984540054) -> tuple[float, float]:
    n_eff = max(1.0, n / max(deff, 1e-9))
    return wilson_ci(k, int(round(n_eff)), z)


def cohen_kappa(a: list, b: list) -> float:
    if not a or len(a) != len(b):
        return float("nan")
    labels = sorted(set(a) | set(b))
    idx = {l: i for i, l in enumerate(labels)}
    m = np.zeros((len(labels), len(labels)))
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    n = m.sum()
    po = np.trace(m) / n
    pe = float(sum(m[i, :].sum() * m[:, i].sum() for i in range(len(labels))) / (n * n))
    if pe == 1:
        return 1.0
    return float((po - pe) / (1 - pe))


def kappa_ci(a: list, b: list, n_boot: int = 2000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(a)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        vals.append(cohen_kappa([a[i] for i in idx], [b[i] for i in idx]))
    vals = [v for v in vals if not math.isnan(v)]
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def sens_spec(y_true: list[int], y_pred: list[int]) -> dict:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    n_pos = tp + fn
    n_neg = tn + fp
    sens = tp / n_pos if n_pos else float("nan")
    spec = tn / n_neg if n_neg else float("nan")
    ppv = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")
    out = {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "n": len(y_true), "n_pos": n_pos, "n_neg": n_neg,
        "sensitivity": sens, "specificity": spec, "ppv": ppv, "npv": npv,
        "accuracy": (tp + tn) / len(y_true) if y_true else float("nan"),
        "f1": (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else float("nan"),
    }
    out["sens_ci"] = wilson_ci(tp, n_pos) if n_pos else (float("nan"), float("nan"))
    out["spec_ci"] = wilson_ci(tn, n_neg) if n_neg else (float("nan"), float("nan"))
    out["ppv_ci"] = wilson_ci(tp, tp + fp) if (tp + fp) else (float("nan"), float("nan"))
    return out


def weighted_validation_metrics(y_true: list[int], y_pred: list[int],
                                strata: list[str], population_sizes: dict[str, int],
                                n_boot: int = 2000, seed: int = 43) -> dict:
    """Metrics and bootstrap CIs weighted to the target population's strata.

    Each sampled record in stratum h receives weight N_h / n_h. Bootstrap
    resampling occurs independently within strata, preserving the validation
    design while reflecting current source proportions.
    """
    if not (len(y_true) == len(y_pred) == len(strata)) or not y_true:
        return {}
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(strata):
        groups.setdefault(s, []).append(i)
    weights = np.zeros(len(y_true), dtype=float)
    for s, indices in groups.items():
        pop = int(population_sizes.get(s, len(indices)))
        weights[indices] = pop / max(1, len(indices))

    def calculate(idx: np.ndarray, w: np.ndarray) -> dict:
        yt = np.asarray(y_true, dtype=int)[idx]
        yp = np.asarray(y_pred, dtype=int)[idx]
        ww = w
        tp = float(ww[(yt == 1) & (yp == 1)].sum())
        tn = float(ww[(yt == 0) & (yp == 0)].sum())
        fp = float(ww[(yt == 0) & (yp == 1)].sum())
        fn = float(ww[(yt == 1) & (yp == 0)].sum())
        sens = tp / (tp + fn) if tp + fn else float("nan")
        spec = tn / (tn + fp) if tn + fp else float("nan")
        ppv = tp / (tp + fp) if tp + fp else float("nan")
        npv = tn / (tn + fn) if tn + fn else float("nan")
        accuracy = (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else float("nan")
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else float("nan")
        total = ww.sum()
        po = float(ww[yt == yp].sum() / total) if total else float("nan")
        py1 = float(ww[yt == 1].sum() / total) if total else 0.0
        py0 = 1 - py1
        pp1 = float(ww[yp == 1].sum() / total) if total else 0.0
        pp0 = 1 - pp1
        pe = py1 * pp1 + py0 * pp0
        kappa = (po - pe) / (1 - pe) if 1 - pe > 0 else float("nan")
        return {"sensitivity": sens, "specificity": spec, "ppv": ppv,
                "npv": npv, "accuracy": accuracy, "f1": f1, "kappa": kappa}

    base = calculate(np.arange(len(y_true)), weights)
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in base}
    for _ in range(n_boot):
        sampled = []
        for indices in groups.values():
            sampled.extend(rng.choice(indices, size=len(indices), replace=True).tolist())
        idx = np.asarray(sampled, dtype=int)
        vals = calculate(idx, weights[idx])
        for k, v in vals.items():
            if not math.isnan(v):
                draws[k].append(v)
    out = {k: float(v) for k, v in base.items()}
    for k, values in draws.items():
        ci = (float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))) if values else (float("nan"), float("nan"))
        out[f"{k}_ci"] = ci
    return out


def rogan_gladen(p_obs: float, sens: float, spec: float) -> float:
    denom = sens + spec - 1
    if denom <= 0:
        return p_obs
    return max(0.0, min(1.0, (p_obs + spec - 1) / denom))


def mann_kendall(x: list[float]) -> dict:
    x = [v for v in x if not (isinstance(v, float) and math.isnan(v))]
    n = len(x)
    if n < 4:
        return {"n": n, "s": 0, "tau": 0.0, "z": 0.0, "p": 1.0, "trend": "n/a"}
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += int(np.sign(x[j] - x[i]))
    _, counts = np.unique(x, return_counts=True)
    tie = sum(c * (c - 1) * (2 * c + 5) for c in counts)
    var = (n * (n - 1) * (2 * n + 5) - tie) / 18
    if var <= 0:
        return {"n": n, "s": s, "tau": 0.0, "z": 0.0, "p": 1.0, "trend": "n/a"}
    if s > 0:
        z = (s - 1) / math.sqrt(var)
    elif s < 0:
        z = (s + 1) / math.sqrt(var)
    else:
        z = 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    trend = "increasing" if (z > 0 and p < 0.05) else ("decreasing" if (z < 0 and p < 0.05) else "no significant trend")
    return {"n": n, "s": int(s), "tau": round(float(tau), 4), "z": round(float(z), 3),
            "p": float(p), "trend": trend}


def ols_slope(x: list[float], y: list[float], hac_lags: int | None = None) -> dict:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 4:
        return {"n": n, "slope": float("nan"), "se": float("nan"), "ci": (float("nan"), float("nan")), "p": float("nan")}
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    lags = hac_lags if hac_lags is not None else int(round(4 * (n / 100) ** (2 / 9)))
    # Newey-West HAC covariance
    XtX_inv = np.linalg.inv(X.T @ X)
    S = np.zeros((2, 2))
    for t in range(n):
        u = resid[t] * X[t]
        S += np.outer(u, u)
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        for t in range(l, n):
            u = resid[t] * X[t]
            v = resid[t - l] * X[t - l]
            S += w * (np.outer(u, v) + np.outer(v, u))
    cov = XtX_inv @ S @ XtX_inv
    se = float(math.sqrt(max(cov[1, 1], 0)))
    slope = float(beta[1])
    tstat = slope / se if se > 0 else float("nan")
    p = 2 * (1 - stats.t.cdf(abs(tstat), df=n - 2)) if se > 0 else float("nan")
    ci = (slope - 1.96 * se, slope + 1.96 * se)
    return {"n": n, "slope": round(slope, 6), "se": round(se, 6),
            "ci": (round(ci[0], 6), round(ci[1], 6)), "p": float(p),
            "intercept": round(float(beta[0]), 4), "hac_lags": lags}


def bootstrap_slope_ci(x: list[float], y: list[float], n_boot: int = 2000, seed: int = 11) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(x)
    if n < 4:
        return (float("nan"), float("nan"))
    out = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        xi, yi = x[idx], y[idx]
        if np.ptp(xi) == 0:
            continue
        b = np.polyfit(xi, yi, 1)[0]
        out.append(b)
    if not out:
        return (float("nan"), float("nan"))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def rate_ratio(k1: int, n1: int, k0: int, n0: int) -> dict:
    if min(n1, n0) == 0:
        return {"rr": float("nan"), "p": float("nan"), "ci": (float("nan"), float("nan"))}
    p1, p0 = k1 / n1, k0 / n0
    rr = p1 / p0 if p0 else float("inf")
    tbl = [[k1, n1 - k1], [k0, n0 - k0]]
    chi2, p, _, _ = stats.chi2_contingency(tbl, correction=False)
    se = math.sqrt(1 / k1 - 1 / n1 + 1 / k0 - 1 / n0) if min(k1, k0) > 0 else float("nan")
    if math.isnan(se):
        ci = (float("nan"), float("nan"))
    else:
        ci = (math.exp(math.log(rr) - 1.96 * se), math.exp(math.log(rr) + 1.96 * se))
    return {"rr": round(float(rr), 3), "p": float(p),
            "ci": (round(ci[0], 3), round(ci[1], 3))}


def proportion_test(k1: int, n1: int, k2: int, n2: int) -> dict:
    if min(n1, n2) == 0:
        return {"p": float("nan"), "diff": float("nan")}
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se > 0 else 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return {"p": float(p), "z": round(float(z), 3), "diff": round(p1 - p2, 4),
            "ci": tuple(round(v, 4) for v in (
                (p1 - p2) - 1.96 * math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2),
                (p1 - p2) + 1.96 * math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2),
            ))}
