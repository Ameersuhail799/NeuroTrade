import unittest

import numpy as np
import pandas as pd

from core.intraday_signal_engine import IntradaySignalEngine


def make_candles(
    count: int,
    frequency: str,
    drift: float,
    amplitude: float = 0.20,
    start_price: float = 2300.0,
) -> pd.DataFrame:
    """Deterministic synthetic candles for engine unit tests only."""
    x = np.arange(count, dtype=float)
    close = (
        start_price
        + drift * x
        + amplitude * np.sin(x / 5.0)
        + (amplitude * 0.35) * np.sin(x / 2.2)
    )
    open_price = close - 0.025 * np.sin(x / 2.7)
    high = np.maximum(open_price, close) + 0.12
    low = np.minimum(open_price, close) - 0.12

    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=count, freq=frequency),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
        }
    )
    return frame


def make_random_walk_candles(
    count: int,
    frequency: str,
    drift: float,
    volatility: float,
    seed: int,
    start_price: float,
) -> pd.DataFrame:
    """Seeded synthetic walk with less artificial momentum than a straight line."""
    rng = np.random.default_rng(seed)
    steps = drift + rng.normal(0.0, volatility, count)
    close = start_price + np.cumsum(steps)
    open_price = close - rng.normal(0.0, volatility * 0.30, count)
    high = np.maximum(open_price, close) + volatility * 0.8
    low = np.minimum(open_price, close) - volatility * 0.8
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=count, freq=frequency),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
        }
    )


def align_fixture_times(h1, m15, m5):
    """Give synthetic frames realistic H1 <= M15 <= M5 end ordering."""
    h1["time"] = pd.date_range(end="2026-02-15 00:00", periods=len(h1), freq="h")
    m15["time"] = pd.date_range(end="2026-02-15 00:45", periods=len(m15), freq="15min")
    m5["time"] = pd.date_range(end="2026-02-15 00:55", periods=len(m5), freq="5min")
    return h1, m15, m5


def bullish_fixture():
    # H1 establishes a clear trend. M15/M5 use seeded noisy walks so RSI is
    # not artificially pinned near 100 by a perfectly smooth rising series.
    h1 = make_candles(260, "h", drift=0.10, amplitude=0.15, start_price=2275)
    m15 = make_random_walk_candles(
        100, "15min", drift=0.02, volatility=0.18, seed=4, start_price=2297
    )
    m5 = make_random_walk_candles(
        100, "5min", drift=0.006, volatility=0.06, seed=1, start_price=2299
    )

    # The second-last M5 candle is the last completed candle when excluding
    # the final (forming) row. Force a modest breakout for this unit test.
    breakout_index = len(m5) - 2
    prior_high = float(m5.loc[breakout_index - 3:breakout_index - 1, "high"].max())
    breakout_close = prior_high + 0.03
    m5.loc[breakout_index, "open"] = breakout_close - 0.04
    m5.loc[breakout_index, "close"] = breakout_close
    m5.loc[breakout_index, "high"] = breakout_close + 0.02
    m5.loc[breakout_index, "low"] = breakout_close - 0.08
    return align_fixture_times(h1, m15, m5)


def bearish_fixture():
    h1 = make_candles(260, "h", drift=-0.10, amplitude=0.15, start_price=2325)
    m15 = make_random_walk_candles(
        100, "15min", drift=-0.01, volatility=0.18, seed=1, start_price=2303
    )
    m5 = make_random_walk_candles(
        100, "5min", drift=-0.012, volatility=0.06, seed=0, start_price=2301
    )

    breakdown_index = len(m5) - 2
    prior_low = float(m5.loc[breakdown_index - 3:breakdown_index - 1, "low"].min())
    breakdown_close = prior_low - 0.03
    m5.loc[breakdown_index, "open"] = breakdown_close + 0.04
    m5.loc[breakdown_index, "close"] = breakdown_close
    m5.loc[breakdown_index, "high"] = breakdown_close + 0.08
    m5.loc[breakdown_index, "low"] = breakdown_close - 0.02
    return align_fixture_times(h1, m15, m5)


class IntradaySignalEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntradaySignalEngine()

    def test_requires_sufficient_history(self):
        h1 = make_candles(100, "h", drift=0.1)
        m15 = make_candles(100, "15min", drift=0.02)
        m5 = make_candles(100, "5min", drift=0.01)

        with self.assertRaisesRegex(ValueError, "H1 needs at least 220"):
            self.engine.generate_signal(h1, m15, m5)

    def test_bullish_setup_produces_risk_plan(self):
        h1, m15, m5 = bullish_fixture()
        result = self.engine.generate_signal(
            h1, m15, m5, symbol="XAUUSD.a", digits=2, exclude_latest=True
        )

        self.assertEqual(result.action, "LONG_SETUP")
        self.assertEqual(result.direction, "LONG")
        self.assertEqual(result.status, "SETUP")
        self.assertEqual(result.market_regime, "UPTREND")
        self.assertIsNotNone(result.entry_reference)
        self.assertIsNotNone(result.stop_loss)
        self.assertIsNotNone(result.take_profit_1)
        self.assertIsNotNone(result.take_profit_2)
        self.assertLess(result.stop_loss, result.entry_reference)
        self.assertGreater(result.take_profit_1, result.entry_reference)
        self.assertGreater(result.take_profit_2, result.take_profit_1)
        self.assertAlmostEqual(result.reward_risk_1, 1.5)
        self.assertAlmostEqual(result.reward_risk_2, 2.0)
        self.assertTrue(any("completed candle" in reason for reason in result.reasons))

    def test_bearish_setup_produces_short_risk_plan(self):
        h1, m15, m5 = bearish_fixture()
        result = self.engine.generate_signal(
            h1, m15, m5, symbol="XAUUSD.a", digits=2, exclude_latest=True
        )

        self.assertEqual(result.action, "SHORT_SETUP")
        self.assertEqual(result.direction, "SHORT")
        self.assertEqual(result.market_regime, "DOWNTREND")
        self.assertGreater(result.stop_loss, result.entry_reference)
        self.assertLess(result.take_profit_1, result.entry_reference)
        self.assertLess(result.take_profit_2, result.take_profit_1)
        self.assertAlmostEqual(result.reward_risk_1, 1.5)
        self.assertAlmostEqual(result.reward_risk_2, 2.0)

    def test_mixed_h1_trend_returns_no_trade(self):
        h1, m15, m5 = bullish_fixture()
        # Replace H1 with a flat/ranging sequence so the H1 trend filter fails.
        h1 = make_candles(260, "h", drift=0.0, amplitude=0.0, start_price=2300)
        h1["time"] = pd.date_range(
            end="2026-02-15 00:00", periods=len(h1), freq="h"
        )
        result = self.engine.generate_signal(h1, m15, m5)

        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.direction, "NONE")
        self.assertIsNone(result.entry_reference)
        self.assertTrue(result.conflicts)

    def test_unsorted_timestamps_are_rejected(self):
        h1, m15, m5 = bullish_fixture()
        h1.loc[[10, 11], "time"] = h1.loc[[11, 10], "time"].to_numpy()

        with self.assertRaisesRegex(ValueError, "oldest-to-newest"):
            self.engine.generate_signal(h1, m15, m5)

    def test_timeframes_must_be_chronologically_aligned(self):
        h1, m15, m5 = bullish_fixture()
        # Make the most recent completed H1 candle newer than the M15 candle.
        h1["time"] = pd.date_range(
            end="2026-02-15 02:00", periods=len(h1), freq="h"
        )
        with self.assertRaisesRegex(ValueError, "Timeframe data is not aligned"):
            self.engine.generate_signal(h1, m15, m5)

    def test_forming_last_candle_is_excluded(self):
        h1, m15, m5 = bullish_fixture()
        baseline = self.engine.generate_signal(h1, m15, m5, exclude_latest=True)

        # Mutating the final (forming) candle must not alter a closed-candle signal.
        m5.loc[len(m5) - 1, ["open", "high", "low", "close"]] = [
            2500.0, 2600.0, 2400.0, 2550.0
        ]
        changed = self.engine.generate_signal(h1, m15, m5, exclude_latest=True)

        self.assertEqual(baseline.action, changed.action)
        self.assertEqual(baseline.entry_reference, changed.entry_reference)
        self.assertEqual(baseline.stop_loss, changed.stop_loss)

    def test_nan_prices_are_rejected(self):
        h1, m15, m5 = bullish_fixture()
        m5.loc[10, "close"] = np.nan
        with self.assertRaisesRegex(ValueError, "missing or non-finite prices"):
            self.engine.generate_signal(h1, m15, m5)

    def test_infinity_prices_are_rejected(self):
        h1, m15, m5 = bullish_fixture()
        h1.loc[15, "high"] = np.inf
        with self.assertRaisesRegex(ValueError, "missing or non-finite prices"):
            self.engine.generate_signal(h1, m15, m5)

    def test_duplicate_timestamps_are_rejected(self):
        h1, m15, m5 = bullish_fixture()
        m15.loc[12, "time"] = m15.loc[11, "time"]
        with self.assertRaisesRegex(ValueError, "timestamps must be unique"):
            self.engine.generate_signal(h1, m15, m5)

    def test_causal_close_time_alignment_rejected_when_h1_unclosed(self):
        h1, m15, m5 = bullish_fixture()
        # Set H1 open so that H1 close time (h1_open + 1h) extends past M15 and M5 close time
        h1_len = len(h1)
        h1["time"] = pd.date_range(end="2026-02-15 01:15", periods=h1_len, freq="h")
        with self.assertRaisesRegex(ValueError, "Timeframe data is not aligned: H1 candle close"):
            self.engine.generate_signal(h1, m15, m5)

    def test_causal_close_time_alignment_rejected_when_h1_after_m15(self):
        h1, m15, m5 = bullish_fixture()
        # In fixture, m15 close is 00:45, m5 close is 00:55.
        # Set H1 close to 00:50 (open 23:50 + 1h = 00:50). H1 close is <= M5 close (00:55),
        # but > M15 close (00:45).
        h1_len = len(h1)
        h1["time"] = pd.date_range(end="2026-02-15 00:50", periods=h1_len, freq="h")
        with self.assertRaisesRegex(ValueError, "H1 candle close .* is after M15 candle close"):
            self.engine.generate_signal(h1, m15, m5)

    def test_causal_close_time_alignment_rejected_when_m15_unclosed(self):
        h1, m15, m5 = bullish_fixture()
        # Set M15 open so that M15 close (m15_open + 15m) extends past M5 close (m5_open + 5m)
        # If M15 closed candle open is 00:45, M15 close is 01:00 > 00:55.
        m15_len = len(m15)
        m15["time"] = pd.date_range(end="2026-02-15 01:00", periods=m15_len, freq="15min")
        with self.assertRaisesRegex(ValueError, "Timeframe data is not aligned: M15 candle close"):
            self.engine.generate_signal(h1, m15, m5)

    def test_stale_higher_timeframe_generates_warning(self):
        h1, m15, m5 = bullish_fixture()
        # Make H1 end 5 hours before M5 (stale H1)
        h1["time"] = pd.date_range(end="2026-02-14 20:00", periods=len(h1), freq="h")
        result = self.engine.generate_signal(h1, m15, m5)
        self.assertTrue(any("Higher-timeframe H1 data appears stale" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
