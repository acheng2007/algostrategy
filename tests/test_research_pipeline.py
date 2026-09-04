import unittest
import os

import numpy as np

from src.research_pipeline import build_research_panel, hypothesis_tables, run_backtests


@unittest.skipUnless(os.environ.get("RUN_PRIVATE_DATA_TESTS") == "1",
                     "Set RUN_PRIVATE_DATA_TESTS=1 after acquiring private inputs")
class ResearchPipelineTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.panel = build_research_panel()
        cls.tables = hypothesis_tables(cls.panel)
        cls.backtests = run_backtests(cls.panel)

    def test_eia_release_timing_never_looks_ahead(self):
        available = self.panel["available_date"].dropna()
        dates = self.panel.loc[available.index, "date"]
        self.assertTrue((available <= dates).all())

    def test_negative_wti_contract_is_not_held(self):
        row = self.panel.loc[self.panel["date"] == "2020-04-20"].iloc[0]
        self.assertEqual(row["contract_alias_cl"], "CL19M20")
        self.assertGreater(row["close_cl"], 0)

    def test_primary_window_has_one_campaign_per_year(self):
        trades = self.backtests["primary"].trades
        self.assertEqual(len(trades), 16)
        self.assertTrue((trades["direction"] == 1).all())

    def test_primary_results_are_finite(self):
        metrics = self.backtests["metrics"]
        primary = metrics[metrics["strategy"] == "July-October seasonal"]
        self.assertTrue(np.isfinite(primary["sharpe"]).all())
        self.assertTrue((primary["trade_count"] > 0).all())

    def test_trade_pnl_reconciles_with_daily_pnl(self):
        for name in ("primary", "original"):
            result = self.backtests[name]
            self.assertAlmostEqual(
                result.trades["net_pnl"].sum(),
                result.daily["net_pnl_strategy"].sum(),
                places=6,
                msg=f"{name} trade P&L must account for every modelled cost",
            )
            self.assertAlmostEqual(
                result.trades["costs"].sum(),
                result.daily["cost"].sum(),
                places=6,
            )

    def test_cost_sensitivity_is_monotonic(self):
        costs = self.backtests["costs"].sort_values(
            ["slippage_ticks_per_contract_side", "fee_per_contract_side"]
        )
        cheapest = costs.iloc[0]
        most_expensive = costs.iloc[-1]
        self.assertGreater(cheapest["annualized_return"], most_expensive["annualized_return"])
        self.assertLess(cheapest["total_costs"], most_expensive["total_costs"])


if __name__ == "__main__":
    unittest.main()
