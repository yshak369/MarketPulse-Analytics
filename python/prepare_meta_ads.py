"""Clean a Meta Ads Manager campaigns export for the database.

Input:  a DAILY campaigns export from Ads Manager, including the
        "Campaign ID" column. One row per campaign per day.
Output: two files for sql/04_load_meta_ads.sql:
          meta_ad_campaigns.csv    one row per campaign
          meta_ad_performance.csv  one row per campaign per day with activity

Design: docs/schema_design.md, sections 4.6 and 4.7.

How to run on the fake export (from the project folder):
    python python/prepare_meta_ads.py --input data/synthetic/synthetic_meta_campaigns_export.csv --output data/processed/meta_test_output

The real export is confidential business data. Keep it, and the output,
outside this project or under data/processed/ (ignored by Git).
What is printed on screen shows counts only.

Rules:
  * Calculated columns (CPM, CPC, CTR, frequency, cost per result) are
    dropped. SQL can work them out from the raw numbers.
  * A row is skipped only when it is completely empty. A day with zero
    impressions but a result is kept, because Meta can count a
    conversation days after the ad was seen.
  * Nothing is guessed. If a campaign's details differ between days, or
    a row has results without saying what kind, the script stops.
"""

import argparse
from pathlib import Path

import pandas as pd

from parse_whatsapp_orders import check_output_folder

# Headings in the export, and the names used in the database.
CAMPAIGN_COLUMNS = {
    "Campaign ID": "campaign_id",
    "Campaign name": "campaign_name",
    "Campaign delivery": "delivery_status",
    "Attribution setting": "attribution_setting",
    "Ad set budget": "budget_amount",
    "Ad set budget type": "budget_type",
    "Ends": "end_date",
}
PERFORMANCE_COLUMNS = {
    "Amount spent (INR)": "amount_spent_inr",
    "Impressions": "impressions",
    "Reach": "reach",
    "Link clicks": "link_clicks",
    "Clicks (all)": "clicks_all",
    "Landing page views": "landing_page_views",
    "Results": "results",
    "Result indicator": "result_indicator",
}
DATE_COLUMNS = ["Reporting starts", "Reporting ends"]
REQUIRED_COLUMNS = DATE_COLUMNS + list(CAMPAIGN_COLUMNS) + list(PERFORMANCE_COLUMNS)

# Numbers that decide whether a row has any activity at all.
ACTIVITY_COLUMNS = ["impressions", "amount_spent_inr", "reach", "link_clicks",
                    "clicks_all", "landing_page_views", "results"]
WHOLE_NUMBER_COLUMNS = ["impressions", "reach", "link_clicks", "clicks_all",
                        "landing_page_views", "results"]

# Special words Meta writes in place of a value.
USING_AD_SET_BUDGET = "using ad set budget"
ONGOING = "ongoing"
NO_SETTING = "-"


class ExportProblem(Exception):
    """The export cannot be cleaned without guessing. A person must look."""


def read_export(path):
    """Read the export as text, so nothing is changed silently."""
    export = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    export.columns = [column.strip() for column in export.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in export.columns]
    if missing:
        raise ExportProblem("The export is missing these columns: " + ", ".join(missing)
                            + ". Add them in Ads Manager under Columns > Customise columns.")

    export = export.apply(lambda column: column.str.strip())
    if (export["Reporting starts"] != export["Reporting ends"]).any():
        raise ExportProblem("This is not a daily export: some rows cover more than one day. "
                            "In Ads Manager choose Breakdown > By time > Day, then export again.")
    return export


def to_number(column):
    """Text to number. Blank stays blank; anything else unreadable stops the script."""
    numbers = pd.to_numeric(column.replace("", None), errors="coerce")
    unreadable = column.ne("") & numbers.isna()
    if unreadable.any():
        raise ExportProblem(f"Unreadable numbers in the export: {sorted(column[unreadable].unique())[:5]}")
    return numbers


def clean_campaign_details(export):
    """Turn Meta's special words into clean values, one column at a time."""
    details = export[list(CAMPAIGN_COLUMNS)].rename(columns=CAMPAIGN_COLUMNS).copy()

    using_ad_set = details["budget_amount"].str.lower() == USING_AD_SET_BUDGET
    details.loc[using_ad_set, "budget_amount"] = ""
    details["budget_type"] = details["budget_type"].str.lower()
    details.loc[using_ad_set, "budget_type"] = "ad_set_level"   # Meta writes 0 here
    details["budget_amount"] = to_number(details["budget_amount"])

    details.loc[details["end_date"].str.lower() == ONGOING, "end_date"] = ""
    details.loc[details["attribution_setting"] == NO_SETTING, "attribution_setting"] = ""
    return details


def build_campaigns(export):
    """One row per Campaign ID. Stops if a campaign's details change between days."""
    details = clean_campaign_details(export).fillna("").astype(str)

    changing = details.groupby("campaign_id").nunique()
    changing = changing[(changing > 1).any(axis=1)]
    if not changing.empty:
        first_id = changing.index[0]
        columns = [c for c in changing.columns if changing.loc[first_id, c] > 1]
        raise ExportProblem(
            f"{len(changing)} campaign(s) have details that differ between days, for example "
            f"campaign ID {first_id} in: {', '.join(columns)}. The script does not choose one. "
            "Check the export, or tell the developer this happens in your data."
        )

    campaigns = details.drop_duplicates("campaign_id").sort_values("campaign_id")
    campaigns["budget_amount"] = to_number(campaigns["budget_amount"])
    return campaigns.reset_index(drop=True)


def build_performance(export):
    """One row per campaign per day with any activity. Returns (rows, skipped count)."""
    performance = export[["Campaign ID", "Reporting starts"] + list(PERFORMANCE_COLUMNS)]
    performance = performance.rename(columns={"Campaign ID": "campaign_id", "Reporting starts": "report_date",
                                              **PERFORMANCE_COLUMNS}).copy()

    for column in ACTIVITY_COLUMNS:
        performance[column] = to_number(performance[column])

    # Meta leaves spend and impressions blank when nothing happened.
    performance["amount_spent_inr"] = performance["amount_spent_inr"].fillna(0)
    performance["impressions"] = performance["impressions"].fillna(0)

    has_activity = (performance[ACTIVITY_COLUMNS].fillna(0) != 0).any(axis=1)
    skipped = int((~has_activity).sum())
    performance = performance[has_activity].copy()

    results_without_kind = performance["results"].fillna(0).ne(0) & performance["result_indicator"].eq("")
    if results_without_kind.any():
        raise ExportProblem(f"{int(results_without_kind.sum())} row(s) have results but no result indicator, "
                            "so it is unknown what was counted.")

    if performance.duplicated(["campaign_id", "report_date"]).any():
        raise ExportProblem("Some campaigns appear twice on the same day. Export with Breakdown > By time > Day only.")

    for column in WHOLE_NUMBER_COLUMNS:
        performance[column] = performance[column].astype("Int64")   # keeps blanks blank
    performance = performance.sort_values(["report_date", "campaign_id"]).reset_index(drop=True)
    return performance, skipped


def write_outputs(campaigns, performance, folder):
    folder = check_output_folder(folder)
    folder.mkdir(parents=True, exist_ok=True)
    campaigns.to_csv(folder / "meta_ad_campaigns.csv", index=False, lineterminator="\n")
    performance.to_csv(folder / "meta_ad_performance.csv", index=False, lineterminator="\n")
    return folder


def main():
    arguments = argparse.ArgumentParser(description="Clean a Meta Ads campaigns export.")
    arguments.add_argument("--input", required=True, help="the daily campaigns export (CSV)")
    arguments.add_argument("--output", required=True, help="folder for the two clean files")
    options = arguments.parse_args()

    check_output_folder(options.output)   # fail early, before any work is done
    try:
        export = read_export(options.input)
        campaigns = build_campaigns(export)
        performance, skipped = build_performance(export)
    except ExportProblem as problem:
        raise SystemExit(f"Stopped: {problem}")

    print(f"export rows read:           {len(export):>7}")
    print(f"campaigns:                  {len(campaigns):>7}")
    print(f"  with no activity at all:  {int((~campaigns['campaign_id'].isin(performance['campaign_id'])).sum()):>7}")
    print(f"daily rows with activity:   {len(performance):>7}")
    print(f"  with zero impressions:    {int((performance['impressions'] == 0).sum()):>7}  (kept: they have other activity)")
    print(f"empty rows skipped:         {skipped:>7}")
    for indicator, total in performance.groupby("result_indicator")["results"].sum().items():
        if indicator:
            print(f"results [{indicator}]: {int(total)}")

    folder = write_outputs(campaigns, performance, options.output)
    print(f"two files written to {Path(folder)}")


if __name__ == "__main__":
    main()
