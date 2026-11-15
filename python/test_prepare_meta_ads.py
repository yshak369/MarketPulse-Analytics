"""Tests for prepare_meta_ads.py, using the fake Meta export only.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

import prepare_meta_ads as meta

FAKE_EXPORT = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "synthetic_meta_campaigns_export.csv"
MESSAGING = "actions:onsite_conversion.messaging_conversation_started_7d"


class FakeExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = meta.read_export(FAKE_EXPORT)
        cls.campaigns = meta.build_campaigns(cls.export).set_index("campaign_id")
        cls.performance, cls.skipped = meta.build_performance(cls.export)

    def row(self, campaign_suffix, day):
        rows = self.performance[(self.performance["campaign_id"] == "1200000000000001" + campaign_suffix)
                                & (self.performance["report_date"] == day)]
        self.assertEqual(len(rows), 1)
        return rows.iloc[0]

    def test_counts(self):
        self.assertEqual(len(self.export), 35)
        self.assertEqual(len(self.campaigns), 5)
        self.assertEqual(len(self.performance), 17)
        self.assertEqual(self.skipped, 18)

    def test_rows_per_campaign(self):
        counts = self.performance["campaign_id"].str[-3:].value_counts().to_dict()
        self.assertEqual(counts, {"101": 7, "102": 5, "103": 3, "104": 2})

    def test_conversation_on_zero_impression_day_is_kept(self):
        row = self.row("02", "2025-10-06")
        self.assertEqual((row["impressions"], row["amount_spent_inr"], row["results"]), (0, 0, 1))
        self.assertEqual(row["result_indicator"], MESSAGING)

    def test_impressions_without_spend_are_kept(self):
        row = self.row("01", "2025-10-07")
        self.assertEqual((row["impressions"], row["amount_spent_inr"]), (14, 0))

    def test_campaign_without_activity_is_kept_without_rows(self):
        self.assertIn("120000000000000105", self.campaigns.index)
        self.assertNotIn("120000000000000105", set(self.performance["campaign_id"]))

    def test_name_with_comma_and_emoji(self):
        self.assertEqual(self.campaigns.loc["120000000000000103", "campaign_name"],
                         "Synthetic Post Boost: Glow ✨ offer, Kerala")

    def test_two_campaigns_can_share_a_name(self):
        self.assertEqual(self.campaigns.loc["120000000000000101", "campaign_name"],
                         self.campaigns.loc["120000000000000102", "campaign_name"])

    def test_cleaning_rules(self):
        c = self.campaigns
        self.assertEqual((c.loc["120000000000000101", "budget_amount"], c.loc["120000000000000101", "budget_type"]),
                         (500, "daily"))
        self.assertTrue(pd.isna(c.loc["120000000000000102", "budget_amount"]))
        self.assertEqual(c.loc["120000000000000102", "budget_type"], "ad_set_level")
        self.assertEqual(c.loc["120000000000000103", "budget_type"], "lifetime")
        self.assertEqual(c.loc["120000000000000101", "end_date"], "")             # Ongoing
        self.assertEqual(c.loc["120000000000000102", "end_date"], "2025-10-04")
        self.assertEqual(c.loc["120000000000000103", "attribution_setting"], "")  # "-"
        self.assertEqual(c.loc["120000000000000101", "attribution_setting"], "7-day click or 1-day view")

    def test_calculated_and_empty_columns_are_dropped(self):
        for column in ("CPM (cost per 1,000 impressions) (INR)", "Frequency", "shop_clicks", "Results (initial)"):
            self.assertNotIn(column, self.performance.columns)
        self.assertEqual(list(self.performance.columns),
                         ["campaign_id", "report_date", "amount_spent_inr", "impressions", "reach", "link_clicks",
                          "clicks_all", "landing_page_views", "results", "result_indicator"])

    def test_totals_match_the_export(self):
        export_spend = pd.to_numeric(self.export["Amount spent (INR)"]).sum()
        self.assertAlmostEqual(self.performance["amount_spent_inr"].sum(), export_spend, places=2)

        export_results = (self.export.assign(r=pd.to_numeric(self.export["Results"].replace("", None)))
                          .groupby("Result indicator")["r"].sum())
        loaded_results = self.performance.groupby("result_indicator")["results"].sum()
        for indicator in ("actions:link_click", "actions:post_engagement", MESSAGING):
            self.assertEqual(loaded_results[indicator], export_results[indicator])
        self.assertEqual(loaded_results[MESSAGING], 21)


class ProblemExportTest(unittest.TestCase):
    def changed_copy(self, change):
        """Write a changed copy of the fake export and return its path."""
        export = pd.read_csv(FAKE_EXPORT, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        change(export)
        path = Path(self.folder.name) / "changed.csv"
        export.to_csv(path, index=False)
        return path

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.folder.cleanup()

    def test_campaign_details_that_change_stop_the_script(self):
        def rename_one_day(export):
            export.loc[0, "Campaign name"] = "Synthetic Renamed Campaign"
        export = meta.read_export(self.changed_copy(rename_one_day))
        with self.assertRaisesRegex(meta.ExportProblem, "120000000000000101"):
            meta.build_campaigns(export)

    def test_missing_column_stops_the_script(self):
        path = self.changed_copy(lambda export: export.drop(columns=["Campaign ID"], inplace=True))
        with self.assertRaisesRegex(meta.ExportProblem, "Campaign ID"):
            meta.read_export(path)

    def test_non_daily_export_stops_the_script(self):
        def stretch(export):
            export.loc[0, "Reporting ends"] = "2025-10-08"
        with self.assertRaisesRegex(meta.ExportProblem, "not a daily export"):
            meta.read_export(self.changed_copy(stretch))

    def test_results_without_indicator_stop_the_script(self):
        def drop_indicator(export):
            export.loc[export["Results"] != "", "Result indicator"] = ""
        export = meta.read_export(self.changed_copy(drop_indicator))
        with self.assertRaisesRegex(meta.ExportProblem, "no result indicator"):
            meta.build_performance(export)

    def test_output_guard_refuses_a_tracked_folder(self):
        export = meta.read_export(FAKE_EXPORT)
        performance, _ = meta.build_performance(export)
        with self.assertRaises(SystemExit):
            meta.write_outputs(meta.build_campaigns(export), performance, FAKE_EXPORT.parent)


if __name__ == "__main__":
    unittest.main()
