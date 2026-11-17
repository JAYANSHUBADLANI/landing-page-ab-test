"""Run the landing page test end to end: clean, analyze, chart, write results.

    python -m src.run_analysis

Writes reports/results.json and reports/figures/*.png, then renders README.md
from reports/README_template.md so every number in the README comes from this run.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ab_test import (SEED, analyze_ab_test, deduplicate_users,
                         power_two_proportions, remove_assignment_mismatches)
from src.render_readme import render

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ab_data.csv"
FIG = ROOT / "reports" / "figures"
DATA_URL = "https://raw.githubusercontent.com/30lm32/ml-ab-testing/master/ab_data.csv"

# Business input: the smallest lift in conversion rate worth rolling out a new page for.
# Half a percentage point (about a 4% relative lift on a 12% base) covers the design,
# engineering and QA cost of switching. Change it here and everything downstream follows.
MDE_ABS = 0.005
ALPHA = 0.05
POWER = 0.80

CONTROL_COLOR = "#2a78d6"
TREATMENT_COLOR = "#eb6834"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"


def load() -> pd.DataFrame:
    if not DATA.exists():
        DATA.parent.mkdir(parents=True, exist_ok=True)
        pd.read_csv(DATA_URL).to_csv(DATA, index=False)
    return pd.read_csv(DATA)


def style_axes(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_conversion(res: dict, path: Path):
    t = res["test"]
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    labels = ["Old page\n(control)", "New page\n(treatment)"]
    rates = [t["rate_control"], t["rate_treatment"]]
    cis = [t["ci_control"], t["ci_treatment"]]
    colors = [CONTROL_COLOR, TREATMENT_COLOR]
    for i, (r, ci, c) in enumerate(zip(rates, cis, colors)):
        ax.bar(i, r * 100, width=0.55, color=c, zorder=2)
        ax.errorbar(i, r * 100, yerr=[[(r - ci[0]) * 100], [(ci[1] - r) * 100]],
                    color=INK, capsize=6, linewidth=1.5, zorder=3)
        ax.text(i, ci[1] * 100 + 0.25, f"{r:.2%}", ha="center", color=INK, fontsize=11)
    ax.set_xticks([0, 1], labels, color=INK)
    ax.set_ylim(0, 14)
    ax.set_ylabel("Conversion rate (%)", color=INK_2)
    ax.set_title(f"New page converts {abs(t['abs_lift']) * 100:.2f} points lower, not significant "
                 f"(p = {t['p_value']:.2f})", color=INK, fontsize=10, loc="left")
    style_axes(ax)
    fig.text(0.01, 0.01, "Bars: conversion rate. Whiskers: 95% confidence interval.",
             color=INK_2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def fig_daily(daily: pd.DataFrame, res: dict, path: Path):
    d = daily.iloc[1:-1]  # first and last calendar days are partial
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(8, 5.6), dpi=150, sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1]})
    ax.plot(d.index, d.rate_control * 100, color=CONTROL_COLOR, lw=2, marker="o", ms=4, label="Old page")
    ax.plot(d.index, d.rate_treatment * 100, color=TREATMENT_COLOR, lw=2, marker="o", ms=4, label="New page")
    ax.set_ylabel("Daily conversion (%)", color=INK_2)
    ax.set_ylim(top=ax.get_ylim()[1] + 0.35)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    ax.set_title("Daily conversion by page: no early spike that fades", color=INK, fontsize=10, loc="left")
    style_axes(ax)
    ax2.axhline(0, color=INK_2, lw=1)
    ax2.plot(d.index, d.abs_diff * 100, color=INK, lw=2, marker="o", ms=4)
    ax2.set_ylabel("New minus old\n(points)", color=INK_2)
    style_axes(ax2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_power(res: dict, path: Path):
    t, pw = res["test"], res["power"]
    p_base = t["rate_control"]
    lifts = np.linspace(0, 0.01, 400)
    power = power_two_proportions(p_base, lifts, res["n_control"], res["n_treatment"], ALPHA)
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    ax.plot(lifts * 100, power, color=CONTROL_COLOR, lw=2)
    ax.axhline(POWER, color=INK_2, lw=1, ls="--")
    ax.axvline(pw["detectable_abs_at_target_power"] * 100, color=INK_2, lw=1, ls=":")
    ax.axvline(MDE_ABS * 100, color=TREATMENT_COLOR, lw=1.5)
    ax.text(pw["detectable_abs_at_target_power"] * 100 + 0.02, 0.08,
            f"80% power at {pw['detectable_abs_at_target_power'] * 100:.2f} pts",
            color=INK_2, fontsize=8, rotation=90, va="bottom")
    ax.text(MDE_ABS * 100 + 0.02, 0.08, f"worthwhile lift {MDE_ABS * 100:.1f} pts: "
            f"{pw['power_at_business_mde']:.0%} power", color=INK, fontsize=8, rotation=90, va="bottom")
    ax.set_xlabel("True lift in conversion rate (percentage points)", color=INK_2)
    ax.set_ylabel("Chance the test detects it", color=INK_2)
    ax.set_ylim(0, 1.02)
    ax.set_title("This test was big enough to catch any lift worth shipping", color=INK, fontsize=10, loc="left")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> dict:
    random.seed(SEED)
    np.random.seed(SEED)
    FIG.mkdir(parents=True, exist_ok=True)

    raw = load()
    cleaning = {"raw_rows": int(len(raw)), "raw_unique_users": int(raw.user_id.nunique()),
                "raw_repeated_user_rows": int(raw.user_id.duplicated().sum())}
    matched, mm = remove_assignment_mismatches(
        raw, "group", "landing_page", {"control": "old_page", "treatment": "new_page"})
    clean, dd = deduplicate_users(matched, "user_id", "timestamp")
    cleaning.update(mm)
    cleaning.update(dd)
    cleaning["final_rows"] = int(len(clean))
    cleaning["rows_removed_total"] = cleaning["raw_rows"] - cleaning["final_rows"]
    cleaning["users_lost"] = cleaning["raw_unique_users"] - int(clean.user_id.nunique())
    cleaning["segment_breakdown"] = "skipped: the source repository has no countries.csv"
    clean.to_csv(ROOT / "data" / "ab_data_clean.csv", index=False)

    res = analyze_ab_test(clean, "group", "converted", time_col="timestamp",
                          alpha=ALPHA, mde_abs=MDE_ABS, power=POWER)
    daily = res.pop("_daily")
    daily.to_csv(ROOT / "reports" / "daily_summary.csv")
    res["cleaning"] = cleaning

    fig_conversion(res, FIG / "conversion_by_group.png")
    fig_daily(daily, res, FIG / "daily_conversion_trend.png")
    fig_power(res, FIG / "power_curve.png")

    (ROOT / "reports" / "results.json").write_text(json.dumps(res, indent=2, default=str))
    render(res, ROOT)
    return res


def print_summary(res: dict):
    t, p, c = res["test"], res["power"], res["cleaning"]
    print("KEY NUMBERS")
    print(f"  rows in / out           {c['raw_rows']:,} / {c['final_rows']:,} "
          f"({c['mismatched_rows']:,} mismatched, {c['duplicate_rows_removed']} duplicate)")
    print(f"  users per group         {res['n_control']:,} old / {res['n_treatment']:,} new "
          f"(SRM p = {res['srm']['p_value']:.3f})")
    print(f"  test length             {res['duration']['days']:.0f} days")
    print(f"  conversion              {t['rate_control']:.2%} old vs {t['rate_treatment']:.2%} new")
    print(f"  lift                    {t['abs_lift'] * 100:+.2f} pts ({t['rel_lift']:+.1%} relative)")
    print(f"  95% CI (points)         [{t['abs_ci'][0] * 100:+.2f}, {t['abs_ci'][1] * 100:+.2f}]")
    print(f"  z / p                   {t['z']:.2f} / {t['p_value']:.3f}")
    print(f"  worthwhile lift         {p['mde_abs_business'] * 100:.1f} pts, power {p['power_at_business_mde']:.1%}")
    print(f"  detectable at 80%       {p['detectable_abs_at_target_power'] * 100:.2f} pts")
    print(f"  decision                {res['decision']['verdict']}")


if __name__ == "__main__":
    print_summary(main())
