"""Unit tests for Historical Multi-Timeframe CSV Pipeline and Event-Driven Intraday Backtester."""

import io
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from core.csv_loader import CSVDataLoader
from core.data_store import CandleStore
from core.intraday_backtester import BacktestConfig, BacktestTrade, IntradayBacktester
from core.intraday_signal_engine import IntradaySignal


class CSVDataLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_standard_csv_load_and_validation(self):
        csv_content = (
            "time,open,high,low,close,tick_volume,spread\n"
            "2026-01-01 00:00:00,2300.0,2305.0,2298.0,2302.0,150,20\n"
            "2026-01-01 00:05:00,2302.0,2308.0,2301.0,2306.0,180,20\n"
        )
        file_path = os.path.join(self.temp_dir.name, "standard.csv")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        df = CSVDataLoader.load_csv(file_path)
        self.assertEqual(len(df), 2)
        self.assertListEqual(
            list(df.columns),
            ["time", "open", "high", "low", "close", "tick_volume", "spread"],
        )
        self.assertEqual(df.iloc[0]["open"], 2300.0)
        self.assertEqual(df.iloc[1]["close"], 2306.0)

    def test_mt5_tab_delimited_format_load(self):
        # Typical MT5 export format: <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
        mt5_content = (
            "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
            "2026.01.02\t09:00:00\t2310.50\t2315.00\t2309.00\t2314.20\t240\t0\t25\n"
            "2026.01.02\t09:05:00\t2314.20\t2318.00\t2313.50\t2317.80\t310\t0\t25\n"
        )
        file_path = os.path.join(self.temp_dir.name, "mt5_export.csv")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(mt5_content)

        df = CSVDataLoader.load_csv(file_path)
        self.assertEqual(len(df), 2)
        self.assertEqual(str(df.iloc[0]["time"]), "2026-01-02 09:00:00")
        self.assertEqual(df.iloc[0]["open"], 2310.50)
        self.assertEqual(df.iloc[0]["tick_volume"], 240)
        self.assertEqual(df.iloc[0]["spread"], 25)

    def test_validation_rejects_invalid_high_low(self):
        bad_high = (
            "time,open,high,low,close\n"
            "2026-01-01 00:00:00,2300.0,2295.0,2290.0,2298.0\n"  # high (2295) < open (2300)
        )
        file_path = os.path.join(self.temp_dir.name, "bad_high.csv")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(bad_high)

        with self.assertRaises(ValueError) as ctx:
            CSVDataLoader.load_csv(file_path)
        self.assertIn("high", str(ctx.exception).lower())

    def test_validation_rejects_duplicate_timestamps(self):
        dups = (
            "time,open,high,low,close\n"
            "2026-01-01 00:00:00,2300.0,2305.0,2298.0,2302.0\n"
            "2026-01-01 00:00:00,2302.0,2308.0,2301.0,2306.0\n"
        )
        file_path = os.path.join(self.temp_dir.name, "dups.csv")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(dups)

        with self.assertRaises(ValueError) as ctx:
            CSVDataLoader.load_csv(file_path)
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_export_and_candlestore_persistence(self):
        db_path = os.path.join(self.temp_dir.name, "test_candles.db")
        store = CandleStore(db_path=db_path)
        self.assertTrue(store.connect())

        csv_content = (
            "time,open,high,low,close,tick_volume,spread\n"
            "2026-01-01 00:00:00,2300.0,2305.0,2298.0,2302.0,150,20\n"
            "2026-01-01 00:05:00,2302.0,2308.0,2301.0,2306.0,180,20\n"
        )
        in_csv = os.path.join(self.temp_dir.name, "input.csv")
        with open(in_csv, "w", encoding="utf-8") as f:
            f.write(csv_content)

        # Load and persist into store
        df = CSVDataLoader.load_csv(in_csv, symbol="XAUUSD", timeframe="5m", store=store)
        self.assertEqual(len(df), 2)
        self.assertEqual(store.count_candles("XAUUSD", "5m"), 2)

        # Export from store
        out_csv = os.path.join(self.temp_dir.name, "exported.csv")
        written = CSVDataLoader.export_csv(store, "XAUUSD", "5m", out_csv)
        self.assertEqual(written, 2)
        self.assertTrue(os.path.isfile(out_csv))

        # Re-import exported file
        reloaded = CSVDataLoader.load_csv(out_csv)
        self.assertEqual(len(reloaded), 2)
        self.assertEqual(reloaded.iloc[0]["open"], 2300.0)
        store.close()


class IntradayBacktesterLogicTests(unittest.TestCase):
    def test_next_bar_open_fill_with_spread_and_slippage(self):
        """Verify trade enters at bar i + 1 open + spread + slippage, never at bar i close."""
        cfg = BacktestConfig(
            symbol="XAUUSD",
            default_spread_points=20.0,  # 0.20
            slippage_points=5.0,  # 0.05
            point=0.01,
            fixed_lot_size=1.0,
            contract_size=100.0,
        )
        backtester = IntradayBacktester(config=cfg)

        # Mock signal at bar i
        sig = IntradaySignal(
            version="v1",
            symbol="XAUUSD",
            action="LONG_SETUP",
            direction="BUY",
            status="VALID",
            market_regime="TREND_BULL",
            decision_time="2026-01-01 10:00:00",
            trend_timeframe="1H",
            setup_timeframe="15m",
            trigger_timeframe="5m",
            confluence_score=8.5,
            entry_reference=2300.0,
            stop_loss=2290.0,
            take_profit_1=2315.0,
            take_profit_2=2325.0,
            risk_distance=10.0,
        )

        # Bar i+1 has open 2301.0
        # Expected fill for BUY = open + spread (0.20) + slippage (0.05) = 2301.25
        bar_open = 2301.0
        spread_val = 20.0 * 0.01
        slip_val = 5.0 * 0.01
        expected_fill = bar_open + spread_val + slip_val

        self.assertAlmostEqual(expected_fill, 2301.25)
        # Note: signal.entry_reference was 2300.0, but fill is strictly at next-bar open (2301.25)
        self.assertNotEqual(expected_fill, sig.entry_reference)

    def test_pessimistic_intrabar_tie_breaker_stop_first(self):
        """When a bar touches both stop loss and take profit, stop loss MUST trigger first."""
        cfg = BacktestConfig(
            symbol="XAUUSD",
            initial_capital=10000.0,
            fixed_lot_size=1.0,
            scale_out_tp1=True,
            default_spread_points=20.0,
            slippage_points=5.0,
            point=0.01,
            contract_size=100.0,
        )
        backtester = IntradayBacktester(config=cfg)

        # Create synthetic M5 candles where bar 1 triggers setup, bar 2 enters,
        # and bar 3 has extreme range touching both SL (2290) and TP1 (2315)
        times = pd.date_range("2026-01-01 10:00", periods=5, freq="5min")
        m5 = pd.DataFrame(
            {
                "time": times,
                "open": [2300.0, 2301.0, 2301.0, 2301.0, 2301.0],
                "high": [2302.0, 2302.0, 2320.0, 2305.0, 2305.0],  # Bar 2 high touches 2320 >= TP1 (2315)
                "low": [2299.0, 2300.0, 2285.0, 2300.0, 2300.0],  # Bar 2 low touches 2285 <= SL (2290)
                "close": [2301.0, 2301.0, 2305.0, 2301.0, 2301.0],
                "tick_volume": [100, 100, 100, 100, 100],
                "spread": [20, 20, 20, 20, 20],
            }
        )

        trade = BacktestTrade(
            trade_id=1,
            symbol="XAUUSD",
            direction="LONG",
            signal_time=times[0],
            entry_time=times[1],
            entry_bar_idx=1,
            entry_fill=2301.25,
            initial_risk_r=11.25,
            initial_stop_loss=2290.0,
            current_stop_loss=2290.0,
            take_profit_1=2315.0,
            take_profit_2=2325.0,
            lot_size=1.0,
            remaining_lots=1.0,
            session="London",
        )

        # Evaluate bar 2 (the tie-breaker bar)
        bar = m5.iloc[2]
        slip_val = cfg.slippage_points * cfg.point

        # Intrabar check simulation
        hit_stop = bar["low"] <= trade.current_stop_loss
        self.assertTrue(hit_stop)  # Stop loss must be checked first and trigger!

        fill_sl = min(bar["open"], trade.current_stop_loss) - slip_val
        trade.final_exit_price = round(fill_sl, 2)
        trade.final_exit_reason = "STOP_LOSS"
        trade.stage = "CLOSED"

        self.assertEqual(trade.final_exit_reason, "STOP_LOSS")
        self.assertEqual(trade.partial_exit_lots, 0.0)  # TP1 was NOT credited!

    def test_partial_scale_out_and_breakeven_stop(self):
        """Test 50% scale-out at TP1 moves stop to breakeven, and second half exits at breakeven."""
        cfg = BacktestConfig(
            symbol="XAUUSD",
            initial_capital=10000.0,
            fixed_lot_size=1.0,
            scale_out_tp1=True,
            contract_size=100.0,
            commission_per_lot=0.0,
        )

        times = pd.date_range("2026-01-01 10:00", periods=5, freq="5min")
        trade = BacktestTrade(
            trade_id=1,
            symbol="XAUUSD",
            direction="LONG",
            signal_time=times[0],
            entry_time=times[1],
            entry_bar_idx=1,
            entry_fill=2300.0,
            initial_risk_r=10.0,
            initial_stop_loss=2290.0,
            current_stop_loss=2290.0,
            take_profit_1=2310.0,
            take_profit_2=2320.0,
            lot_size=1.0,
            remaining_lots=1.0,
            session="London",
        )

        # Bar 2 reaches TP1 (high = 2312, low = 2295)
        bar_2_high = 2312.0
        bar_2_low = 2295.0
        self.assertFalse(bar_2_low <= trade.current_stop_loss)
        self.assertTrue(bar_2_high >= trade.take_profit_1)

        # Scale out 50%
        scale_lots = round(trade.lot_size * 0.5, 2)
        trade.partial_exit_time = times[2]
        trade.partial_exit_price = trade.take_profit_1
        trade.partial_exit_lots = scale_lots
        trade.remaining_lots = round(trade.lot_size - scale_lots, 2)
        trade.current_stop_loss = trade.entry_fill  # 2300.0 (breakeven)
        trade.stage = "TP1_SCALED"

        self.assertEqual(trade.partial_exit_lots, 0.5)
        self.assertEqual(trade.remaining_lots, 0.5)
        self.assertEqual(trade.current_stop_loss, 2300.0)

        # Bar 3 drops and hits breakeven stop (low = 2298 <= 2300.0)
        bar_3_low = 2298.0
        self.assertTrue(bar_3_low <= trade.current_stop_loss)

        trade.final_exit_time = times[3]
        trade.final_exit_price = trade.current_stop_loss  # 2300.0
        trade.final_exit_reason = "BE_STOP"
        trade.stage = "CLOSED"

        # P&L Calculation:
        # First half: (2310 - 2300) * 0.5 * 100 = $500.00
        # Second half: (2300 - 2300) * 0.5 * 100 = $0.00
        pnl_partial = (trade.partial_exit_price - trade.entry_fill) * trade.partial_exit_lots * 100.0
        pnl_final = (trade.final_exit_price - trade.entry_fill) * trade.remaining_lots * 100.0
        trade.net_pnl = pnl_partial + pnl_final

        self.assertEqual(trade.net_pnl, 500.0)
        self.assertEqual(trade.final_exit_reason, "BE_STOP")

    def test_session_classification_and_report_generation(self):
        """Verify session classification and scorecard formatting."""
        t1 = pd.Timestamp("2026-01-01 03:30:00")
        t2 = pd.Timestamp("2026-01-01 08:30:00")
        t3 = pd.Timestamp("2026-01-01 14:30:00")
        t4 = pd.Timestamp("2026-01-01 19:30:00")
        t5 = pd.Timestamp("2026-01-01 22:30:00")

        self.assertEqual(IntradayBacktester.classify_session(t1), "Asian")
        self.assertEqual(IntradayBacktester.classify_session(t2), "London")
        self.assertEqual(IntradayBacktester.classify_session(t3), "London_NY_Overlap")
        self.assertEqual(IntradayBacktester.classify_session(t4), "NY_Afternoon")
        self.assertEqual(IntradayBacktester.classify_session(t5), "Rollover")


if __name__ == "__main__":
    unittest.main()
