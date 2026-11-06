import json
import os
import tempfile
import unittest

from core.signal_formatter import SignalFormatter
from core.signal_history import SignalRecord
from core.signal_store import SignalStore


class SignalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.store = SignalStore(db_path=self.temp_db.name)
        self.assertTrue(self.store.connect())

    def tearDown(self):
        self.store.close()
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    def test_intraday_signal_record_persistence(self):
        record = SignalRecord(
            record_id=0,
            created_at="2026-11-06 12:00:00",
            engine="intraday_mtf",
            engine_version="intraday-mtf-v1",
            symbol="XAUUSD",
            timeframe="1H/15m/5m",
            decision_time="2026-11-06 11:55:00",
            action="LONG_SETUP",
            score=100.0,
            confidence=100.0,
            rows_used=100,
            exclude_latest=True,
            inputs={
                "intraday_metadata": {
                    "market_regime": "UPTREND",
                    "direction": "LONG",
                    "status": "SETUP",
                    "entry_reference": 2350.50,
                    "stop_loss": 2345.00,
                    "take_profit_1": 2358.75,
                    "take_profit_2": 2361.50,
                    "risk_distance": 5.50,
                    "reward_risk_1": 1.5,
                    "reward_risk_2": 2.0,
                    "conflicts": [],
                }
            },
            reasons=["M5 bullish confirmation: breakout on a completed candle."],
            warnings=["Analysis uses completed candles only."],
            weights={},
        )

        row_id = self.store.save(record)
        self.assertIsNotNone(row_id)

        # Duplicate insertion ignored
        duplicate_id = self.store.save(record)
        self.assertIsNone(duplicate_id)

        # Load back
        loaded = self.store.load_all()
        self.assertEqual(len(loaded), 1)
        loaded_record = loaded[0]
        self.assertEqual(loaded_record.engine, "intraday_mtf")
        self.assertEqual(loaded_record.action, "LONG_SETUP")
        self.assertEqual(loaded_record.timeframe, "1H/15m/5m")
        self.assertIn("intraday_metadata", loaded_record.inputs)
        self.assertEqual(
            loaded_record.inputs["intraday_metadata"]["entry_reference"], 2350.50
        )

    def test_signal_formatter_text_and_json(self):
        record = SignalRecord(
            record_id=1,
            created_at="2026-11-06 12:00:00",
            engine="intraday_mtf",
            engine_version="intraday-mtf-v1",
            symbol="XAUUSD",
            timeframe="1H/15m/5m",
            decision_time="2026-11-06 11:55:00",
            action="SHORT_SETUP",
            score=100.0,
            confidence=100.0,
            rows_used=100,
            exclude_latest=True,
            inputs={
                "intraday_metadata": {
                    "market_regime": "DOWNTREND",
                    "direction": "SHORT",
                    "status": "SETUP",
                    "entry_reference": 2320.00,
                    "stop_loss": 2325.00,
                    "take_profit_1": 2312.50,
                    "take_profit_2": 2310.00,
                    "risk_distance": 5.00,
                    "reward_risk_1": 1.5,
                    "reward_risk_2": 2.0,
                    "conflicts": ["M15 momentum is weak."],
                }
            },
            reasons=["M5 bearish breakdown on completed candle."],
            warnings=["Test warning."],
            weights={},
        )

        text = SignalFormatter.to_text(record)
        self.assertIn("Intraday Multi-Timeframe Plan:", text)
        self.assertIn("Market Regime: DOWNTREND", text)
        self.assertIn("Entry Reference: 2320.0", text)
        self.assertIn("Stop Loss: 2325.0", text)
        self.assertIn("Take Profit 1: 2312.5", text)
        self.assertIn("M15 momentum is weak.", text)

        json_str = SignalFormatter.to_json(record)
        data = json.loads(json_str)
        self.assertEqual(data["engine"], "intraday_mtf")
        self.assertEqual(data["action"], "SHORT_SETUP")
        self.assertIn("intraday_mtf_plan", data)
        self.assertEqual(data["intraday_mtf_plan"]["entry_reference"], 2320.00)


if __name__ == "__main__":
    unittest.main()
