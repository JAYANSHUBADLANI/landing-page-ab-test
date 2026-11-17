"""Reusable analysis for a two group conversion test.

The entry point is ``analyze_ab_test``. It works on any table with one row per
user, a group column and a 0/1 conversion column, so the same code can read the
next landing page, checkout or email test.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats

SEED = 42


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def remove_assignment_mismatches(df: pd.DataFrame, group_col: str, variant_col: str,
                                 expected: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Drop rows where the variant a user saw does not match their assigned group.

    ``expected`` maps each group label to the variant it should have seen,
    e.g. {"control": "old_page", "treatment": "new_page"}.
    """
    should_see = df[group_col].map(expected)
    ok = df[variant_col] == should_see
    breakdown = (df.loc[~ok].groupby([group_col, variant_col]).size()
                 .rename("rows").reset_index().to_dict("records"))
    report = {"rows_in": int(len(df)), "mismatched_rows": int((~ok).sum()),
              "mismatch_breakdown": breakdown}
    return df.loc[ok].copy(), report


def deduplicate_users(df: pd.DataFrame, user_col: str, time_col: str | None = None
                      ) -> tuple[pd.DataFrame, dict]:
    """Keep one row per user: the first exposure if a timestamp is given."""
    if time_col is not None:
        df = df.sort_values([user_col, time_col], kind="mergesort")
    dup_mask = df.duplicated(user_col, keep="first")
    report = {"duplicate_user_ids": int(df.loc[dup_mask, user_col].nunique()),
              "duplicate_rows_removed": int(dup_mask.sum()),
              "duplicate_examples": df.loc[df[user_col].isin(df.loc[dup_mask, user_col])]
              .astype(str).to_dict("records")[:6]}
    return df.loc[~dup_mask].copy(), report


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def srm_check(counts: dict[str, int], expected_share: dict[str, float] | None = None) -> dict:
    """Chi square goodness of fit on group sizes (sample ratio mismatch)."""
    labels = list(counts)
    observed = np.array([counts[k] for k in labels], dtype=float)
    if expected_share is None:
        expected_share = {k: 1 / len(labels) for k in labels}
    expected = np.array([expected_share[k] for k in labels]) * observed.sum()
    chi2, p = stats.chisquare(observed, expected)
    return {"counts": {k: int(counts[k]) for k in labels},
            "observed_share": {k: float(counts[k] / observed.sum()) for k in labels},
            "chi2": float(chi2), "p_value": float(p)}


def two_proportion_test(conv_c: int, n_c: int, conv_t: int, n_t: int, alpha: float = 0.05) -> dict:
    """Two sided pooled z test plus an unpooled (Wald) CI for the difference."""
    p_c, p_t = conv_c / n_c, conv_t / n_t
    p_pool = (conv_c + conv_t) / (n_c + n_t)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = (p_t - p_c) / se_pool
    p_value = 2 * stats.norm.sf(abs(z))
    se_diff = np.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    zcrit = stats.norm.ppf(1 - alpha / 2)
    diff = p_t - p_c
    lo, hi = diff - zcrit * se_diff, diff + zcrit * se_diff
    return {"rate_control": p_c, "rate_treatment": p_t,
            "ci_control": _wald_ci(p_c, n_c, zcrit), "ci_treatment": _wald_ci(p_t, n_t, zcrit),
            "abs_lift": diff, "rel_lift": diff / p_c,
            "abs_ci": [lo, hi], "rel_ci": [lo / p_c, hi / p_c],
            "z": float(z), "p_value": float(p_value), "alpha": alpha,
            "significant": bool(p_value < alpha)}


def _wald_ci(p: float, n: int, zcrit: float) -> list[float]:
    half = zcrit * np.sqrt(p * (1 - p) / n)
    return [p - half, p + half]


def bootstrap_diff_ci(y_c: np.ndarray, y_t: np.ndarray, n_boot: int = 2000,
                      alpha: float = 0.05, seed: int = SEED) -> list[float]:
    """Percentile bootstrap CI for the difference in rates (cross check on the z CI)."""
    rng = np.random.default_rng(seed)
    n_c, n_t = len(y_c), len(y_t)
    k_c, k_t = int(y_c.sum()), int(y_t.sum())
    # Resampling 0/1 outcomes is equivalent to a binomial draw on the observed rate.
    diffs = rng.binomial(n_t, k_t / n_t, n_boot) / n_t - rng.binomial(n_c, k_c / n_c, n_boot) / n_c
    return [float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))]


def power_two_proportions(p_base: float, abs_lift: float | np.ndarray, n_c: int, n_t: int,
                          alpha: float = 0.05) -> np.ndarray:
    """Power of a two sided two proportion z test for a given true absolute lift."""
    abs_lift = np.asarray(abs_lift, dtype=float)
    p_t = p_base + abs_lift
    se = np.sqrt(p_base * (1 - p_base) / n_c + p_t * (1 - p_t) / n_t)
    zcrit = stats.norm.ppf(1 - alpha / 2)
    return stats.norm.cdf(abs_lift / se - zcrit) + stats.norm.cdf(-abs_lift / se - zcrit)


def mde_at_power(p_base: float, n_c: int, n_t: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest absolute lift this sample detects with the requested power."""
    grid = np.linspace(1e-5, 0.1, 200_000)
    pw = power_two_proportions(p_base, grid, n_c, n_t, alpha)
    return float(grid[np.argmax(pw >= power)])


def sample_size_per_group(p_base: float, abs_lift: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Users needed in each group to detect ``abs_lift`` with the requested power."""
    p_t = p_base + abs_lift
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    var = p_base * (1 - p_base) + p_t * (1 - p_t)
    return int(np.ceil((za + zb) ** 2 * var / abs_lift ** 2))


# ---------------------------------------------------------------------------
# Time checks
# ---------------------------------------------------------------------------

def daily_summary(df: pd.DataFrame, group_col: str, conversion_col: str, time_col: str,
                  control: str, treatment: str) -> pd.DataFrame:
    d = df.assign(date=pd.to_datetime(df[time_col]).dt.normalize())
    g = d.groupby(["date", group_col])[conversion_col].agg(["sum", "count"]).unstack(group_col)
    out = pd.DataFrame({
        "users_control": g[("count", control)], "users_treatment": g[("count", treatment)],
        "rate_control": g[("sum", control)] / g[("count", control)],
        "rate_treatment": g[("sum", treatment)] / g[("count", treatment)],
    })
    out["treatment_share"] = out.users_treatment / (out.users_control + out.users_treatment)
    out["abs_diff"] = out.rate_treatment - out.rate_control
    return out


def trend_check(daily: pd.DataFrame, trim_edges: bool = True) -> dict:
    """Does the daily gap between groups drift over time? (novelty or learning effect)"""
    d = daily.copy()
    if trim_edges:  # first and last calendar days are partial
        d = d.iloc[1:-1]
    x = np.arange(len(d))
    fit = stats.linregress(x, d.abs_diff.values)
    half = len(d) // 2
    return {"days_used": int(len(d)),
            "slope_per_day": float(fit.slope), "slope_p_value": float(fit.pvalue),
            "first_half_mean_diff": float(d.abs_diff.iloc[:half].mean()),
            "second_half_mean_diff": float(d.abs_diff.iloc[half:].mean()),
            "days_treatment_ahead": int((d.abs_diff > 0).sum()),
            "min_daily_share": float(d.treatment_share.min()),
            "max_daily_share": float(d.treatment_share.max())}


# ---------------------------------------------------------------------------
# One call analysis
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    verdict: str
    reason: str


def decide(test: dict, mde_abs: float) -> Decision:
    """Turn the numbers into ship / keep / keep testing."""
    lo, hi = test["abs_ci"]
    if test["significant"] and lo > 0 and lo >= mde_abs:
        return Decision("ship", "lift is significant and even the low end clears the minimum worthwhile lift")
    if test["significant"] and test["abs_lift"] < 0:
        return Decision("keep old page", "the new page converts significantly worse")
    if hi < mde_abs:
        return Decision("keep old page", "even the most optimistic plausible lift is below the minimum worthwhile lift")
    return Decision("keep testing", "the plausible range still includes a lift worth having")


def analyze_ab_test(df: pd.DataFrame, group_col: str, conversion_col: str,
                    control: str = "control", treatment: str = "treatment",
                    time_col: str | None = None, alpha: float = 0.05,
                    mde_abs: float = 0.005, power: float = 0.8,
                    expected_share: dict[str, float] | None = None) -> dict:
    """Full read of a clean, one row per user conversion test.

    ``mde_abs`` is the smallest absolute lift in conversion rate that would be
    worth acting on. It is a business input, not a statistical one.
    """
    sub = df[df[group_col].isin([control, treatment])]
    y_c = sub.loc[sub[group_col] == control, conversion_col].to_numpy()
    y_t = sub.loc[sub[group_col] == treatment, conversion_col].to_numpy()
    n_c, n_t = len(y_c), len(y_t)

    result = {"n_control": n_c, "n_treatment": n_t,
              "conversions_control": int(y_c.sum()), "conversions_treatment": int(y_t.sum())}
    result["srm"] = srm_check({control: n_c, treatment: n_t}, expected_share)
    result["test"] = two_proportion_test(int(y_c.sum()), n_c, int(y_t.sum()), n_t, alpha)
    result["test"]["bootstrap_abs_ci"] = bootstrap_diff_ci(y_c, y_t, alpha=alpha)

    p_base = result["test"]["rate_control"]
    result["power"] = {
        "mde_abs_business": mde_abs, "mde_rel_business": mde_abs / p_base,
        "power_at_business_mde": float(power_two_proportions(p_base, mde_abs, n_c, n_t, alpha)),
        "detectable_abs_at_target_power": mde_at_power(p_base, n_c, n_t, alpha, power),
        "target_power": power,
        "n_per_group_for_business_mde": sample_size_per_group(p_base, mde_abs, alpha, power),
    }
    result["power"]["detectable_rel_at_target_power"] = (
        result["power"]["detectable_abs_at_target_power"] / p_base)

    if time_col is not None:
        ts = pd.to_datetime(sub[time_col])
        daily = daily_summary(sub, group_col, conversion_col, time_col, control, treatment)
        result["duration"] = {"start": str(ts.min()), "end": str(ts.max()),
                              "days": float((ts.max() - ts.min()).total_seconds() / 86400),
                              "calendar_days": int(daily.shape[0])}
        result["trend"] = trend_check(daily)
        result["_daily"] = daily

    result["decision"] = asdict(decide(result["test"], mde_abs))
    return result
