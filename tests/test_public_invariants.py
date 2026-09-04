"""Data-free tests use invented P&L, never private market observations."""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from src.research_pipeline import backtest_signal, seasonal_signal, BASE_PAIR_COST

class PublicInvariantTests(unittest.TestCase):
    def setUp(self):
        self.panel = pd.DataFrame({
            "date": pd.bdate_range("2023-01-02", periods=130),
            "gross_pnl": np.tile([-100., 150.], 65),
            "is_roll": False,
        })
        self.signal = pd.Series(0., index=self.panel.index)
        self.signal.loc[65:95] = 1.
        self.panel.loc[80, "is_roll"] = True
        self.result = backtest_signal(self.panel, self.signal,
                                      pd.Series(True, index=self.panel.index))

    def test_close_signal_only_affects_next_interval(self):
        d = self.result.daily
        self.assertEqual(d.loc[65, "held_units"], 0)
        self.assertGreater(d.loc[66, "held_units"], 0)
        self.assertEqual(d.loc[65, "gross_pnl_strategy"], 0)
        self.assertGreater(d.loc[65, "signal_trade_cost"], 0)

    def test_campaign_and_daily_pnl_reconcile_including_entry(self):
        d, t = self.result.daily, self.result.trades
        self.assertEqual(len(t), 1)
        self.assertGreater(d.loc[65, "cost"], 0)
        self.assertAlmostEqual(t.net_pnl.sum(), d.net_pnl_strategy.sum(), places=8)
        self.assertAlmostEqual(t.costs.sum(), d.cost.sum(), places=8)
        self.assertAlmostEqual(t.gross_pnl.sum(), d.gross_pnl_strategy.sum(), places=8)

    def test_roll_pays_close_and_reopen_on_both_legs(self):
        d = self.result.daily
        self.assertAlmostEqual(d.loc[80, "roll_cost"],
                               2 * BASE_PAIR_COST * d.loc[80, "held_units"])
        self.assertEqual(d.loc[79, "roll_cost"], 0)

    def test_higher_costs_reduce_net_by_exact_turnover_cost(self):
        d = self.result.daily
        expensive = backtest_signal(self.panel, self.signal,
            pd.Series(True, index=self.panel.index), pair_cost=2 * BASE_PAIR_COST).daily
        self.assertAlmostEqual(expensive.net_pnl_strategy.sum(),
                               d.net_pnl_strategy.sum() - d.cost.sum(), places=8)

    def test_seasonal_window_uses_next_session_month(self):
        panel = pd.DataFrame({"month": [6, 7, 10, 11]})
        self.assertEqual(seasonal_signal(panel, 7, 10).tolist(), [1., 1., 0., 0.])

    def test_published_campaigns_reconcile_to_summary(self):
        root = Path(__file__).resolve().parents[1] / "data/processed"
        trades = pd.read_csv(root / "strategy_trades.csv")
        metrics = pd.read_csv(root / "strategy_metrics.csv")
        full = metrics[(metrics.strategy == "July-October seasonal") &
                       (metrics.period == "2010-2025 full")].iloc[0]
        self.assertEqual(len(trades), 16)
        self.assertAlmostEqual(trades.net_pnl.sum(), full.net_pnl, places=6)
        self.assertAlmostEqual(trades.costs.sum(), full.costs, places=6)

if __name__ == "__main__":
    unittest.main()
