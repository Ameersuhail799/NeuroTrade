"""Unit tests for core.web_market_data (WebMarketDataProvider)."""

import io
import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from core.data_store import CandleStore
from core.weight_store import WeightStore
from core.web_market_data import WebMarketDataProvider, WEB_SYMBOL_SPECS


class TestWebMarketDataProvider(unittest.TestCase):
    def test_symbol_normalization(self):
        self.assertEqual(WebMarketDataProvider.resolve_symbol("XAUUSD"), "XAUUSD")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("XAUUSD.a"), "XAUUSD")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("GOLD"), "XAUUSD")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("EURUSD.pro"), "EURUSD")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("GBPUSD_ecn"), "GBPUSD")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("USDJPY"), "USDJPY")
        self.assertEqual(WebMarketDataProvider.resolve_symbol("AUDUSD/m"), "AUDUSD")

        # Unknown fallback defaults safely to XAUUSD
        self.assertEqual(WebMarketDataProvider.resolve_symbol("UNKNOWN_SYM"), "XAUUSD")

    def test_get_symbol_spec(self):
        gold_spec = WebMarketDataProvider.get_symbol_spec("XAUUSD")
        self.assertEqual(gold_spec["ticker"], "GC=F")
        self.assertEqual(gold_spec["point"], 0.01)
        self.assertEqual(gold_spec["digits"], 2)
        self.assertEqual(gold_spec["default_spread"], 20.0)
        self.assertEqual(gold_spec["rollover_spread"], 45.0)

        eur_spec = WebMarketDataProvider.get_symbol_spec("EURUSD")
        self.assertEqual(eur_spec["ticker"], "EURUSD=X")
        self.assertEqual(eur_spec["point"], 0.00001)
        self.assertEqual(eur_spec["digits"], 5)

    def test_unsupported_timeframe_raises(self):
        with self.assertRaises(ValueError):
            WebMarketDataProvider.fetch_candles("XAUUSD", "99m")

    @patch("urllib.request.urlopen")
    def test_fetch_candles_mocked(self, mock_urlopen):
        # Synthetic Yahoo response with:
        # 1. Normal hour candle (10:00 UTC)
        # 2. Rollover hour candle (22:00 UTC)
        # 3. Candle with missing/None data (should be filtered out)
        # 4. Inverted high/low (should be clamped)
        sample_response = {
            "chart": {
                "result": [
                    {
                        "timestamp": [
                            1700042400,  # 2023-11-15 10:00:00 UTC
                            1700085600,  # 2023-11-15 22:00:00 UTC (rollover)
                            1700089200,  # Missing/None quote
                            1700092800,  # Inverted high/low
                        ],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [1980.10, 1985.20, None, 1990.00],
                                    "high": [1983.50, 1988.00, None, 1988.00],  # inverted: lower than open
                                    "low": [1979.00, 1984.00, None, 1995.00],   # inverted: higher than close
                                    "close": [1982.40, 1986.50, None, 1992.00],
                                    "volume": [100, 200, None, 300],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(sample_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        df = WebMarketDataProvider.fetch_candles("XAUUSD", "1H")

        # Row with None should have been skipped, leaving 3 rows
        self.assertEqual(len(df), 3)
        self.assertListEqual(
            list(df.columns),
            ["time", "open", "high", "low", "close", "tick_volume", "spread"],
        )

        # First row (10:00 UTC) should have default spread (20.0)
        self.assertEqual(df.iloc[0]["spread"], 20.0)
        self.assertEqual(df.iloc[0]["open"], 1980.10)

        # Second row (22:00 UTC) should have rollover spread (45.0)
        self.assertEqual(df.iloc[1]["spread"], 45.0)

        # Third row should have clamped high >= max(open, close) and low <= min(open, close)
        self.assertGreaterEqual(df.iloc[2]["high"], df.iloc[2]["close"])
        self.assertLessEqual(df.iloc[2]["low"], df.iloc[2]["open"])

    @patch("core.web_market_data.WebMarketDataProvider.fetch_candles")
    def test_sync_to_sqlite(self, mock_fetch):
        # Create small synthetic DataFrames for 1H, 15m, 5m
        def side_effect(symbol, timeframe, bars=None, timeout=15):
            t_base = pd.date_range("2024-01-01 00:00:00", periods=10, freq="1h" if timeframe == "1H" else "5min")
            return pd.DataFrame({
                "time": t_base.strftime("%Y-%m-%d %H:%M:%S"),
                "open": [2000.0] * 10,
                "high": [2005.0] * 10,
                "low": [1995.0] * 10,
                "close": [2002.0] * 10,
                "tick_volume": [100] * 10,
                "spread": [20.0] * 10,
            })

        mock_fetch.side_effect = side_effect

        candle_store = CandleStore(db_path=":memory:")
        candle_store.connect()

        weight_store = WeightStore(db_path=":memory:")
        weight_store.connect()

        try:
            res = WebMarketDataProvider.sync_to_sqlite(
                symbol="XAUUSD",
                store=candle_store,
                weight_store=weight_store,
                requested_bars=10,
            )

            self.assertEqual(res["symbol"], "XAUUSD")
            self.assertEqual(res["point"], 0.01)
            self.assertEqual(res["digits"], 2)

            # Contract should be persisted in WeightStore
            contract = weight_store.load_contract("XAUUSD")
            self.assertIsNotNone(contract)
            self.assertEqual(contract["point"], 0.01)
            self.assertEqual(contract["digits"], 2)

            # Candles should be persisted in CandleStore
            self.assertEqual(candle_store.count_candles("XAUUSD", "1H"), 10)
            self.assertEqual(candle_store.count_candles("XAUUSD", "15m"), 10)
            self.assertEqual(candle_store.count_candles("XAUUSD", "5m"), 10)
        finally:
            candle_store.close()
            weight_store.close()


if __name__ == "__main__":
    unittest.main()
