# Landing Page A/B Test Analysis

**Should we replace the current landing page with the redesign?**

A company tested a redesigned landing page against its current one by splitting
visitors at random. This project reads that test the way a growth team should
before rolling anything out: check the data can be trusted, measure the
difference, decide whether the difference is big enough to matter, and make a call.

**Recommendation: {verdict}.** The new page converted at {rate_t} against {rate_c}
for the old page. That is {abs_lift_mag} points lower, and the gap is within
normal random noise. The test was large enough to spot a lift worth paying for,
and it did not find one.

## At a glance

| | Old page (control) | New page (treatment) |
|---|---|---|
| Visitors | {n_c} | {n_t} |
| Conversions | {k_c} | {k_t} |
| Conversion rate | {rate_c} | {rate_t} |
| 95% range for the rate | {ci_c_lo} to {ci_c_hi} | {ci_t_lo} to {ci_t_hi} |

| Result | Value |
|---|---|
| Change in conversion rate (new minus old) | {abs_lift} percentage points |
| Change relative to the old page | {rel_lift} |
| 95% confidence range for the change | {abs_lo} to {abs_hi} points ({rel_lo} to {rel_hi}) |
| Chance of a gap this size if the pages were truly equal (p value) | {p} |
| Smallest lift worth shipping (business input) | {mde_abs} points ({mde_rel} relative) |
| Chance this test would have caught that lift | {power_mde} |

![Conversion by page](reports/figures/conversion_by_group.png)

## The data

`ab_data.csv` from the public [30lm32/ml-ab-testing](https://github.com/30lm32/ml-ab-testing)
repository: one row per page view with `user_id`, `timestamp`, `group`
(control or treatment), `landing_page` (old_page or new_page) and `converted`
(1 if the visitor converted). It holds {raw_rows} rows from {raw_users} unique
visitors between {start} and {end}.

That repository has no country file, so the planned country breakdown is skipped.

## Step 1: cleaning

Each group should only ever see its own page. Some rows broke that rule, which
means the tracking or the page routing misfired for those visits. We cannot
say which page actually influenced those visitors, so the rows are removed.

| What was removed | Rows | Why |
|---|---|---|
| Control visitors shown the new page | {mm_control_new} | wrong page for the group |
| Treatment visitors shown the old page | {mm_treat_old} | wrong page for the group |
| Repeat visits by the same user | {dup_rows} | keeps one row per person (their first visit) so nobody is counted twice |
| **Total removed** | **{removed_total}** | |

{raw_rows} rows in, {final_rows} rows out. Before cleaning, {raw_repeat_rows} rows
were repeat appearances of a user already in the data. Almost all of them were
the mismatched rows: those visitors had one correct visit and one wrong one.
After dropping the mismatches only {dup_users} user still appeared twice. The
number of unique visitors lost in cleaning is {users_lost}, so every person in
the test is still counted once.

## Step 2: can the split be trusted?

- **Group sizes.** A 50/50 split should give nearly equal groups. We got
  {share_c} old and {share_t} new. A chi square check on those counts gives
  p = {srm_p}, so there is no sign the randomizer was broken (a p value below
  0.01 here would be a red flag).
- **Test length.** {days} days, which covers three full weekly cycles, so
  weekday and weekend visitors are both well represented.
- **Daily split.** On every full day the new page got between {min_share} and
  {max_share} of traffic. No day was lopsided.

## Step 3: the result

The new page converted {abs_lift} points differently from the old one ({rel_lift}).
The 95% confidence range for the true change runs from {abs_lo} to {abs_hi}
points. That range includes zero, and the p value is {p} (a two proportion z
test gives z = {z}), so the data does not show a real difference in either
direction. A bootstrap check gives almost the same range ({boot_lo} to {boot_hi}
points).

## Step 4: is it worth acting on?

A statistically real lift can still be too small to justify the cost of
switching. We set the **smallest lift worth shipping**
at {mde_abs} percentage points, about {mde_rel} on top of the old page. That is
the business input in `src/run_analysis.py`; change it and the whole report
updates.

- With this many visitors, the test had a {power_mde} chance of detecting a
  {mde_abs} point lift if it existed. It would detect anything from
  {det_abs} points ({det_rel} relative) upward with 80% power.
- To detect a {mde_abs} point lift with 80% power you only need {n_needed}
  visitors per page, so this test was well above the size it needed.
- Even the most optimistic end of the confidence range ({abs_hi} points) is far
  below the {mde_abs} point bar.

So this is not a case of "too little data to tell". The test was strong enough,
and the best case for the new page is still not worth rolling out.

![Power curve](reports/figures/power_curve.png)

## Step 5: does the effect change over time?

New designs sometimes win early just because they are new (a novelty effect),
then fade. Over the {days_trend} full days:

- The new page beat the old one on {days_ahead} of {days_trend} days.
- Average daily gap: {first_half} points in the first half of the test and
  {second_half} points in the second half.
- The daily gap has no meaningful trend ({slope} points per day, p = {slope_p}).

There is no early spike that fades, and no late surge that would justify waiting.

![Daily conversion trend](reports/figures/daily_conversion_trend.png)

## Recommendation: {verdict}

1. The new page did not convert better: {rate_t} against {rate_c}, a gap well
   inside normal noise (p = {p}).
2. The test was big enough to catch a {mde_abs} point lift {power_mde} of the time,
   so the lack of a win is a real answer, not a sample size problem.
3. The best plausible outcome ({abs_hi} points) is still below the lift needed to
   justify switching, and the daily trend shows no hidden upside.
4. Keep the old page, and put design effort into a bolder variant rather than
   running this one longer.

## Reuse it on the next test

All of the statistics live in `src/ab_test.py`. For any one row per user
conversion table:

```python
from src.ab_test import analyze_ab_test

result = analyze_ab_test(
    df, group_col="group", conversion_col="converted",
    control="control", treatment="treatment",
    time_col="timestamp", mde_abs=0.005,
)
result["test"]        # rates, lift, confidence range, z test
result["srm"]         # group size check
result["power"]       # power and minimum detectable lift
result["decision"]    # ship / keep old page / keep testing, with the reason
```

The cleaning helpers (`remove_assignment_mismatches`, `deduplicate_users`) are
separate so they can be reused or skipped.

## How to run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.run_analysis
```

This downloads the data if it is missing, writes `reports/results.json`, the
three charts in `reports/figures/`, and regenerates this README from
`reports/README_template.md`. The notebook `notebooks/ab_test_analysis.ipynb`
walks through the same steps with outputs shown. The random seed is fixed at 42
(used by the bootstrap check), so every run gives identical numbers.

## Project structure

```
data/                          raw and cleaned data
notebooks/ab_test_analysis.ipynb   step by step walkthrough
src/ab_test.py                 reusable analysis functions
src/run_analysis.py            end to end pipeline and charts
src/render_readme.py           fills the README from results.json
reports/results.json           every number in this README
reports/figures/               charts
```
