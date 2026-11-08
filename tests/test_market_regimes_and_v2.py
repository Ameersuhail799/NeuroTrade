"""Unit tests for Level 4 High-Precision Signal Engine v2, Market Regimes & Multi-Instrument Profiles."""

import unittest
import pandas as pd
import numpy as np

from core.intraday_signal_engine import IntradaySignalEngine
from core.market_regimes import (
    INSTRUMENT_PROFILES,
    InstrumentProfile,
    IntradayStrategyConfig,
    MarketRegimeAnalyzer,
)
from core.signal_formatter import SignalFormatter
from core.signal_history import SignalRecord
from tests.test_intraday_signal_engine import (
    bullish_fixture,
    bearish_fixture,
    align_fixture_times,
    make_candles,
    make_random_walk_candles,
)


class MarketRegimesAndV2Tests(unittest.TestCase):
    def test_instrument_profile_resolution(self):
        # Broker suffix stripping and alias resolution
        p_xau = MarketRegimeAnalyzer.resolve_profile("XAUUSD.a")
        self.assertEqual(p_xau.symbol, "XAUUSD")
        self.assertEqual(p_xau.default_point, 0.01)
        self.assertEqual(p_xau.max_spread_to_risk, 0.12)

        p_gold = MarketRegimeAnalyzer.resolve_profile("GOLD_pro")
        self.assertEqual(p_gold.symbol, "XAUUSD")

        p_eur = MarketRegimeAnalyzer.resolve_profile("EURUSDm")
        self.assertEqual(p_eur.symbol, "EURUSD")
        self.assertEqual(p_eur.default_point, 0.00001)
        self.assertEqual(p_eur.max_spread_to_risk, 0.10)

        p_jpy = MarketRegimeAnalyzer.resolve_profile("USDJPY.ecn")
        self.assertEqual(p_jpy.symbol, "USDJPY")
        self.assertEqual(p_jpy.default_point, 0.001)

        p_aud = MarketRegimeAnalyzer.resolve_profile("AUDUSD")
        self.assertEqual(p_aud.symbol, "AUDUSD")
        self.assertEqual(p_aud.max_spread_to_risk, 0.15)

    def test_session_classification_hours(self):
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 02:00:00"), "ASIAN")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 09:30:00"), "LONDON")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 14:15:00"), "LONDON_NY_OVERLAP")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 18:45:00"), "NY_AFTERNOON")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 21:30:00"), "ROLLOVER")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 22:15:00"), "ROLLOVER")
        self.assertEqual(MarketRegimeAnalyzer.classify_session("2026-03-01 23:05:00"), "ASIAN")

    def test_kaufman_efficiency_ratio(self):
        # Straight line trend: efficiency ratio must be 1.0
        straight = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0])
        er_straight = MarketRegimeAnalyzer.kaufman_efficiency_ratio(straight, period=10)
        self.assertAlmostEqual(float(er_straight.iloc[-1]), 1.0, places=3)

        # Oscillating chop: 100, 101, 100, 101... -> net change is small, volatility sum is large
        choppy = pd.Series([100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0])
        er_choppy = MarketRegimeAnalyzer.kaufman_efficiency_ratio(choppy, period=10)
        self.assertLess(float(er_choppy.iloc[-1]), 0.10)

    def test_rollover_blackout_blocks_trade(self):
        # Set up a bullish fixture ending at 21:55 UTC (in rollover window)
        h1, m15, m5 = bullish_fixture()
        h1["time"] = pd.date_range(end="2026-02-15 21:00", periods=len(h1), freq="h")
        m15["time"] = pd.date_range(end="2026-02-15 21:45", periods=len(m15), freq="15min")
        m5["time"] = pd.date_range(end="2026-02-15 21:55", periods=len(m5), freq="5min")

        # 1. With enable_rollover_block=True (default) -> setup is blocked
        engine_blocked = IntradaySignalEngine(config=IntradayStrategyConfig(enable_rollover_block=True))
        sig_blocked = engine_blocked.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)

        self.assertEqual(sig_blocked.action, "NO_TRADE")
        self.assertTrue(any("rollover spread blackout" in c for c in sig_blocked.conflicts))

        # 2. With enable_rollover_block=False -> setup is permitted
        engine_allowed = IntradaySignalEngine(config=IntradayStrategyConfig(enable_rollover_block=False))
        sig_allowed = engine_allowed.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)

        self.assertEqual(sig_allowed.action, "LONG_SETUP")
        self.assertEqual(sig_allowed.direction, "LONG")

    def test_spread_to_risk_gate(self):
        h1, m15, m5 = bullish_fixture()
        # In synthetic fixture, risk distance is ~0.55.
        # Normal spread: 5 points (0.05 on XAUUSD -> ratio ~0.09 < 0.12)
        m5["spread"] = 5
        engine = IntradaySignalEngine(config=IntradayStrategyConfig(enable_spread_filter=True))
        sig_normal = engine.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True, point=0.01)
        self.assertEqual(sig_normal.action, "LONG_SETUP")

        # Wide spread spike: 50 points (0.50 on XAUUSD -> ratio ~0.90 > 0.12)
        m5["spread"] = 50
        sig_wide = engine.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True, point=0.01)
        self.assertEqual(sig_wide.action, "NO_TRADE")
        self.assertTrue(any("Spread-to-risk ratio" in c for c in sig_wide.conflicts))

    def test_block_asian_breakouts(self):
        # Fixture timestamps end at 02:55 UTC (Asian session)
        h1, m15, m5 = bullish_fixture()
        h1["time"] = pd.date_range(end="2026-02-15 02:00", periods=len(h1), freq="h")
        m15["time"] = pd.date_range(end="2026-02-15 02:45", periods=len(m15), freq="15min")
        m5["time"] = pd.date_range(end="2026-02-15 02:55", periods=len(m5), freq="5min")

        # 1. With block_asian_breakouts=True in Asian session -> Breakout is rejected
        cfg_block = IntradayStrategyConfig(block_asian_breakouts=True)
        engine_block = IntradaySignalEngine(config=cfg_block)
        sig_asian = engine_block.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)
        self.assertEqual(sig_asian.action, "NO_TRADE")

        # 2. Same setup moved to London session (09:55 UTC) -> Permitted
        h1_lon, m15_lon, m5_lon = bullish_fixture()
        h1_lon["time"] = pd.date_range(end="2026-02-15 09:00", periods=len(h1_lon), freq="h")
        m15_lon["time"] = pd.date_range(end="2026-02-15 09:45", periods=len(m15_lon), freq="15min")
        m5_lon["time"] = pd.date_range(end="2026-02-15 09:55", periods=len(m5_lon), freq="5min")

        sig_london = engine_block.generate_signal(h1_lon, m15_lon, m5_lon, symbol="XAUUSD", exclude_latest=True)
        self.assertEqual(sig_london.action, "LONG_SETUP")

        # 3. With block_asian_breakouts=False in Asian session -> Permitted
        cfg_allow = IntradayStrategyConfig(block_asian_breakouts=False)
        engine_allow = IntradaySignalEngine(config=cfg_allow)
        sig_asian_allow = engine_allow.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)
        self.assertEqual(sig_asian_allow.action, "LONG_SETUP")

    def test_regime_filter_rejections(self):
        h1, m15, m5 = bullish_fixture()
        # Test low efficiency ratio rejection
        cfg_regime = IntradayStrategyConfig(
            enable_regime_filter=True,
            min_efficiency_ratio=0.80,  # Unusually high requirement to trigger rejection
        )
        engine = IntradaySignalEngine(config=cfg_regime)
        sig = engine.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)
        self.assertEqual(sig.action, "NO_TRADE")
        self.assertTrue(any("efficiency ratio" in c for c in sig.conflicts))

    def test_graded_confluence_score_and_microstructure_inputs(self):
        h1, m15, m5 = bullish_fixture()
        # Set London/NY overlap timestamp: 14:55 UTC
        h1["time"] = pd.date_range(end="2026-02-15 14:00", periods=len(h1), freq="h")
        m15["time"] = pd.date_range(end="2026-02-15 14:45", periods=len(m15), freq="15min")
        m5["time"] = pd.date_range(end="2026-02-15 14:55", periods=len(m5), freq="5min")
        m5["spread"] = 5

        engine = IntradaySignalEngine()
        sig = engine.generate_signal(h1, m15, m5, symbol="XAUUSD", exclude_latest=True)

        self.assertEqual(sig.action, "LONG_SETUP")
        self.assertGreaterEqual(sig.confluence_score, 60.0)
        self.assertLessEqual(sig.confluence_score, 100.0)

        # Verify regime_and_microstructure in inputs
        self.assertIn("regime_and_microstructure", sig.inputs)
        regime = sig.inputs["regime_and_microstructure"]
        self.assertEqual(regime["session"], "LONDON_NY_OVERLAP")
        self.assertIn("m15_efficiency_ratio", regime)
        self.assertIn("m15_atr_percentile", regime)
        self.assertIn("confluence_breakdown", regime)
        self.assertEqual(regime["profile_symbol"], "XAUUSD")

    def test_signal_formatter_displays_microstructure(self):
        record = SignalRecord(
            record_id=42,
            created_at="2026-03-01 14:55:00",
            engine="intraday_mtf",
            engine_version="intraday-mtf-v2",
            symbol="XAUUSD",
            timeframe="1H/15m/5m",
            decision_time="2026-03-01 14:50:00",
            action="LONG_SETUP",
            score=88.5,
            confidence=88.5,
            rows_used=100,
            exclude_latest=True,
            inputs={
                "intraday_metadata": {
                    "market_regime": "UPTREND",
                    "direction": "LONG",
                    "status": "SETUP",
                    "entry_reference": 2350.0,
                    "stop_loss": 2340.0,
                    "take_profit_1": 2365.0,
                    "take_profit_2": 2375.0,
                    "risk_distance": 10.0,
                    "reward_risk_1": 1.5,
                    "reward_risk_2": 2.5,
                },
                "regime_and_microstructure": {
                    "session": "LONDON_NY_OVERLAP",
                    "spread_to_risk_ratio": 0.02,
                    "m15_efficiency_ratio": 0.65,
                    "m15_atr_percentile": 55.4,
                    "profile_symbol": "XAUUSD",
                },
            },
        )

        formatted = SignalFormatter.to_text(record)
        self.assertIn("Market Regime & Microstructure:", formatted)
        self.assertIn("Trading Session: LONDON_NY_OVERLAP", formatted)
        self.assertIn("Spread-to-Risk Ratio: 2.00%", formatted)
        self.assertIn("M15 Kaufman Efficiency: 0.65", formatted)
        self.assertIn("M15 ATR Percentile: 55.4%", formatted)


if __name__ == "__main__":
    unittest.main()
