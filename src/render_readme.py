"""Fill README_template.md with numbers from a results dict.

Every figure in the README is a placeholder here, so nothing is typed by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def pct(x: float, d: int = 2) -> str:
    return f"{x * 100:.{d}f}%"


def pts(x: float, d: int = 2) -> str:
    return f"{x * 100:+.{d}f}"


def values(res: dict) -> dict:
    t, p, c, s = res["test"], res["power"], res["cleaning"], res["srm"]
    tr, du = res["trend"], res["duration"]
    br = {(r["group"], r["landing_page"]): r["rows"] for r in c["mismatch_breakdown"]}
    return {
        "raw_rows": f"{c['raw_rows']:,}",
        "raw_users": f"{c['raw_unique_users']:,}",
        "raw_repeat_rows": f"{c['raw_repeated_user_rows']:,}",
        "mismatched": f"{c['mismatched_rows']:,}",
        "mm_control_new": f"{br.get(('control', 'new_page'), 0):,}",
        "mm_treat_old": f"{br.get(('treatment', 'old_page'), 0):,}",
        "dup_rows": f"{c['duplicate_rows_removed']:,}",
        "dup_users": f"{c['duplicate_user_ids']:,}",
        "removed_total": f"{c['rows_removed_total']:,}",
        "final_rows": f"{c['final_rows']:,}",
        "users_lost": f"{c['users_lost']:,}",
        "n_c": f"{res['n_control']:,}", "n_t": f"{res['n_treatment']:,}",
        "k_c": f"{res['conversions_control']:,}", "k_t": f"{res['conversions_treatment']:,}",
        "share_c": pct(s["observed_share"]["control"]), "share_t": pct(s["observed_share"]["treatment"]),
        "srm_chi2": f"{s['chi2']:.4f}", "srm_p": f"{s['p_value']:.2f}",
        "start": du["start"][:10], "end": du["end"][:10], "days": f"{du['days']:.0f}",
        "min_share": pct(tr["min_daily_share"], 1), "max_share": pct(tr["max_daily_share"], 1),
        "rate_c": pct(t["rate_control"]), "rate_t": pct(t["rate_treatment"]),
        "ci_c_lo": pct(t["ci_control"][0]), "ci_c_hi": pct(t["ci_control"][1]),
        "ci_t_lo": pct(t["ci_treatment"][0]), "ci_t_hi": pct(t["ci_treatment"][1]),
        "abs_lift": pts(t["abs_lift"]), "rel_lift": f"{t['rel_lift'] * 100:+.1f}%",
        "abs_lo": pts(t["abs_ci"][0]), "abs_hi": pts(t["abs_ci"][1]),
        "rel_lo": f"{t['rel_ci'][0] * 100:+.1f}%", "rel_hi": f"{t['rel_ci'][1] * 100:+.1f}%",
        "boot_lo": pts(t["bootstrap_abs_ci"][0]), "boot_hi": pts(t["bootstrap_abs_ci"][1]),
        "z": f"{t['z']:.2f}", "p": f"{t['p_value']:.2f}",
        "abs_lift_mag": f"{abs(t['abs_lift']) * 100:.2f}",
        "mde_abs": f"{p['mde_abs_business'] * 100:.1f}", "mde_rel": f"{p['mde_rel_business'] * 100:.1f}%",
        "power_mde": pct(p["power_at_business_mde"], 0),
        "det_abs": f"{p['detectable_abs_at_target_power'] * 100:.2f}",
        "det_rel": f"{p['detectable_rel_at_target_power'] * 100:.1f}%",
        "n_needed": f"{p['n_per_group_for_business_mde']:,}",
        "days_trend": f"{tr['days_used']}", "days_ahead": f"{tr['days_treatment_ahead']}",
        "first_half": pts(tr["first_half_mean_diff"]), "second_half": pts(tr["second_half_mean_diff"]),
        "slope": f"{tr['slope_per_day'] * 100:+.3f}", "slope_p": f"{tr['slope_p_value']:.2f}",
        "verdict": res["decision"]["verdict"].upper(),
    }


def render(res: dict, root: Path) -> None:
    template = (root / "reports" / "README_template.md").read_text()
    out = template.format_map(values(res))
    if "—" in out:
        raise ValueError("README contains an em dash")
    (root / "README.md").write_text(out)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    render(json.loads((root / "reports" / "results.json").read_text()), root)
    sys.exit(0)
