"""Unit tests for Level 5 Purged Walk-Forward Validator, Ablation Study, and Backtest UI Tab."""

import unittest
import numpy as np
import pandas as pd

from core.intraday_backtester import BacktestConfig, IntradayBacktester
from core.market_regimes import IntradayStrategyConfig
from core.walk_forward_validator import (
    AblationRow,
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardSummary,
    WalkForwardValidator,
)


def make_aligned_test_dataset(
    h1_count: int = 230,
    m15_count: int = 80,
    m5_count: int = 200,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate compact aligned synthetic frames with sufficient bars for warm-up and fast unit testing."""
    rng = np.random.default_rng(seed)

    # 1. H1 Frame
    h1_end = pd.Timestamp("2026-03-01 11:00")
    h1_times = pd.date_range(end=h1_end, periods=h1_count, freq="h")
    h1_steps = rng.normal(0.05, 0.20, h1_count)
    h1_close = 2300.0 + np.cumsum(h1_steps)
    h1_open = h1_close - rng.normal(0.0, 0.10, h1_count)
    h1_high = np.maximum(h1_open, h1_close) + 0.30
    h1_low = np.minimum(h1_open, h1_close) - 0.30
    h1 = pd.DataFrame(
        {
            "time": h1_times,
            "open": h1_open,
            "high": h1_high,
            "low": h1_low,
            "close": h1_close,
        }
    )

    # 2. M15 Frame
    m15_end = pd.Timestamp("2026-03-01 11:45")
    m15_times = pd.date_range(end=m15_end, periods=m15_count, freq="15min")
    m15_steps = rng.normal(0.01, 0.10, m15_count)
    m15_close = 2300.0 + np.cumsum(m15_steps)
    m15_open = m15_close - rng.normal(0.0, 0.05, m15_count)
    m15_high = np.maximum(m15_open, m15_close) + 0.15
    m15_low = np.minimum(m15_open, m15_close) - 0.15
    m15 = pd.DataFrame(
        {
            "time": m15_times,
            "open": m15_open,
            "high": m15_high,
            "low": m15_low,
            "close": m15_close,
        }
    )

    # 3. M5 Frame
    m5_end = pd.Timestamp("2026-03-01 11:55")
    m5_times = pd.date_range(end=m5_end, periods=m5_count, freq="5min")
    m5_steps = rng.normal(0.003, 0.05, m5_count)
    m5_close = 2300.0 + np.cumsum(m5_steps)
    m5_open = m5_close - rng.normal(0.0, 0.02, m5_count)
    m5_high = np.maximum(m5_open, m5_close) + 0.08
    m5_low = np.minimum(m5_open, m5_close) - 0.08
    m5 = pd.DataFrame(
        {
            "time": m5_times,
            "open": m5_open,
            "high": m5_high,
            "low": m5_low,
            "close": m5_close,
            "spread": [5] * m5_count,
        }
    )

    return h1, m15, m5


class WalkForwardAndAblationTests(unittest.TestCase):
    def setUp(self):
        self.h1, self.m15, self.m5 = make_aligned_test_dataset()

    def test_eval_window_restricts_trade_entries_with_warmup(self):
        """Verify eval_start_time / eval_end_time confines trades to the evaluation window."""
        window_start = self.m5.iloc[80]["time"]
        window_end = self.m5.iloc[150]["time"]

        bt = IntradayBacktester(
            config=BacktestConfig(symbol="XAUUSD", default_spread_points=5.0)
        )
        res = bt.run(
            self.h1,
            self.m15,
            self.m5,
            eval_start_time=window_start,
            eval_end_time=window_end,
        )

        self.assertIsNotNone(res.start_time)
        self.assertIsNotNone(res.end_time)
        self.assertEqual(res.start_time, window_start)
        self.assertEqual(res.end_time, window_end)
        self.assertEqual(res.total_bars_m5, 71)  # 150 - 80 + 1

        for t in res.trades:
            self.assertGreaterEqual(t.entry_time, window_start)

    def test_purged_walk_forward_validation_folds(self):
        """Verify WalkForwardValidator creates purged, non-overlapping out-of-sample folds."""
        wf_cfg = WalkForwardConfig(n_folds=3, embargo_m5_bars=6)
        summary = WalkForwardValidator.run_walk_forward(
            h1=self.h1,
            m15=self.m15,
            m5=self.m5,
            symbol="XAUUSD",
            wf_config=wf_cfg,
        )

        self.assertEqual(summary.symbol, "XAUUSD")
        self.assertEqual(summary.total_folds, 3)
        self.assertEqual(len(summary.folds), 3)

        # Check fold ordering and embargo gap
        prev_end_time = None
        for fold in summary.folds:
            self.assertLess(fold.start_time, fold.end_time)
            if prev_end_time is not None:
                self.assertGreater(fold.start_time, prev_end_time)
                gap = fold.start_time - prev_end_time
                self.assertGreaterEqual(gap, pd.Timedelta(minutes=30))
            prev_end_time = fold.end_time

        # Report formatting
        report = WalkForwardValidator.format_walk_forward_report(summary)
        self.assertIn("NEUROTRADE AI - ROLLING WALK-FORWARD VALIDATION SCORECARD", report)
        self.assertIn("Consistency Ratio:", report)
        self.assertIn("#1", report)
        self.assertIn("#2", report)
        self.assertIn("#3", report)

    def test_5_stage_ablation_study(self):
        """Verify 5-stage ablation study executes all stages and produces comparative rows."""
        rows = WalkForwardValidator.run_ablation_study(
            h1=self.h1,
            m15=self.m15,
            m5=self.m5,
            symbol="XAUUSD",
        )

        self.assertEqual(len(rows), 5)
        expected_names = [
            "1_Baseline_v1",
            "2_Plus_Session_Rollover",
            "3_Plus_Spread_Gate",
            "4_Full_v2_Regime_Gate",
            "5_Full_v2_ScaleOut_TP1_BE",
        ]
        self.assertListEqual([r.stage_name for r in rows], expected_names)

        for r in rows:
            self.assertIsInstance(r.total_trades, int)
            self.assertIsInstance(r.win_rate, float)
            self.assertIsInstance(r.expectancy_r, float)
            self.assertIsInstance(r.profit_factor, float)
            self.assertIsInstance(r.net_profit, float)

        report = WalkForwardValidator.format_ablation_report(rows)
        self.assertIn("NEUROTRADE AI - 5-STAGE STRATEGY ABLATION STUDY", report)
        for name in expected_names:
            self.assertIn(name, report)


if __name__ == "__main__":
    unittest.main()
