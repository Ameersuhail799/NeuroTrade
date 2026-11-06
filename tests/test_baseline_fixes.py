import unittest
from unittest.mock import MagicMock

import pandas as pd
import numpy as np

from core.feedback_engine import FeedbackEngine
from core.trade_executor import DemoTradeExecutor


class BaselineFixesTests(unittest.TestCase):
    def test_feedback_purged_embargo_split(self):
        # 100 rows with 50 indicators columns
        rows = 100
        horizon = 10
        train_fraction = 0.70

        df = pd.DataFrame(
            {
                "time": pd.date_range("2026-01-01", periods=rows, freq="15min"),
                "close": np.linspace(2000, 2100, rows),
                "sma_20": np.linspace(1995, 2095, rows),
                "ema_50": np.linspace(1990, 2090, rows),
                "rsi_14": np.full(rows, 55.0),
                "macd": np.full(rows, 1.2),
                "macd_signal": np.full(rows, 0.8),
                "bb_middle": np.linspace(1995, 2095, rows),
                "bb_upper": np.linspace(2010, 2110, rows),
                "bb_lower": np.linspace(1980, 2080, rows),
            }
        )

        samples = FeedbackEngine.build_samples(
            df=df,
            point=0.01,
            horizon=horizon,
            min_outcome_points=10.0,
            train_fraction=train_fraction,
        )

        train_samples = [s for s in samples if s.split == "train"]
        val_samples = [s for s in samples if s.split == "validation"]
        purged_samples = [s for s in samples if s.split == "purged"]

        self.assertTrue(len(train_samples) >= 10)
        self.assertTrue(len(val_samples) >= 5)
        self.assertTrue(len(purged_samples) > 0)

        val_start_index = val_samples[0].index

        # Critical: ensure NO training sample looks into the validation period
        for sample in train_samples:
            future_index = sample.index + horizon
            self.assertLessEqual(
                future_index,
                val_start_index,
                f"Sample index {sample.index} + horizon {horizon} = {future_index} "
                f"leaks into validation start {val_start_index}",
            )

        # Ensure all purged samples were indeed boundary overlaps
        for sample in purged_samples:
            self.assertGreater(sample.index + horizon, val_start_index)
            self.assertLess(sample.index, val_start_index)

    def test_volume_normalization_flooring(self):
        # 0.019 with step 0.01 should floor to 0.01, not round up to 0.02
        vol = DemoTradeExecutor.normalize_volume(
            requested_volume=0.019,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
        self.assertEqual(vol, 0.01)

        vol2 = DemoTradeExecutor.normalize_volume(
            requested_volume=0.058,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
        self.assertEqual(vol2, 0.05)

    def test_volume_below_minimum_raises_runtime_error(self):
        with self.assertRaisesRegex(RuntimeError, "below broker minimum"):
            DemoTradeExecutor.normalize_volume(
                requested_volume=0.008,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
            )

    def test_trade_executor_retcode_handling(self):
        executor = DemoTradeExecutor()

        # DONE (10009) -> success = True
        mock_done = MagicMock()
        mock_done.retcode = 10009
        mock_done.comment = "Done"
        mock_done.order = 101
        mock_done.deal = 201
        res_done = executor._build_execution_result(
            result=mock_done,
            action="open_buy",
            symbol="XAUUSD",
            request={"price": 2300.0, "volume": 0.01},
            notes=[],
        )
        self.assertTrue(res_done.success)
        self.assertIn("Order filled", res_done.message)

        # PLACED (10008) -> success = False (pending order, not a filled deal)
        mock_placed = MagicMock()
        mock_placed.retcode = 10008
        mock_placed.comment = "Placed"
        mock_placed.order = 102
        mock_placed.deal = 0
        res_placed = executor._build_execution_result(
            result=mock_placed,
            action="open_buy",
            symbol="XAUUSD",
            request={"price": 2300.0, "volume": 0.01},
            notes=[],
        )
        self.assertFalse(res_placed.success)
        self.assertIn("Order placed/pending (not filled yet)", res_placed.message)


if __name__ == "__main__":
    unittest.main()
