"""
Unit tests for the Overextension Guard, Confluence Safety Shield, and Post-Mortem Diagnostic Engine.
Ensures the core 5 rules remain intact while preventing false 100% confidence traps at market extremes.
"""

import unittest
import pandas as pd
import numpy as np

from core.decision_engine import RuleBasedDecisionEngine
from core.adaptive_decision_engine import AdaptiveDecisionEngine
from core.signal_outcome_tracker import SignalOutcomeTracker


class OverextensionAndPostMortemTests(unittest.TestCase):
    def setUp(self):
        self.rule_engine = RuleBasedDecisionEngine()
        self.adaptive_engine = AdaptiveDecisionEngine()

    def test_rule_engine_caps_confidence_on_extreme_oversold_short(self):
        """
        Verifies that when Gold drops aggressively (e.g. 2.5x ATR from 20MA, RSI 28.0),
        even if all 5 trend rules vote bearish (-100 score), the engine:
        1. Issues an OVEREXTENSION WARNING.
        2. Issues an EXHAUSTION WARNING.
        3. Caps confidence at 40.0% so the trader isn't tricked into selling the bottom.
        """
        rows = 70
        # Build synthetic data where price crashes at the end
        close = np.linspace(3770, 3750, rows)
        close[-1] = 3725.0  # Massive crash on final closed candle

        sma_20 = np.full(rows, 3755.0)
        ema_50 = np.full(rows, 3765.0)
        rsi = np.full(rows, 28.0)  # Extreme oversold
        atr = np.full(rows, 10.0)  # ATR = 10.0 -> distance = (3755 - 3725) = 30.0 -> 3.0x ATR!
        macd = np.full(rows, -5.0)
        macd_signal = np.full(rows, -2.0)
        bb_middle = np.full(rows, 3755.0)
        bb_upper = np.full(rows, 3780.0)
        bb_lower = np.full(rows, 3720.0)

        df = pd.DataFrame({
            "close": close,
            "sma_20": sma_20,
            "ema_50": ema_50,
            "rsi_14": rsi,
            "atr_14": atr,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd - macd_signal,
            "bb_middle": bb_middle,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
        })

        result = self.rule_engine.evaluate(df, meta={"symbol": "XAUUSD", "timeframe": "15m"}, exclude_latest=False)

        # 1. Action is SHORT_BIAS because all 5 rules align
        self.assertEqual(result.action, "SHORT_BIAS")

        # 2. Overextension inputs are recorded
        self.assertTrue(result.inputs.get("is_overextended"))
        self.assertGreaterEqual(result.inputs.get("overextension_ratio"), 1.5)

        # 3. Warnings are present
        warnings_text = " ".join(result.warnings)
        self.assertIn("OVEREXTENSION WARNING", warnings_text)
        self.assertIn("EXHAUSTION WARNING", warnings_text)

        # 4. Confidence is capped at 40.0% (NOT 100.0%) to prevent chasing!
        self.assertLessEqual(result.confidence, 40.0)

    def test_adaptive_engine_caps_confidence_on_overextension(self):
        """
        Verifies that AdaptiveDecisionEngine also applies the overextension and exhaustion guard.
        """
        rows = 70
        close = np.linspace(3770, 3750, rows)
        close[-1] = 3725.0

        df = pd.DataFrame({
            "close": close,
            "sma_20": np.full(rows, 3755.0),
            "ema_50": np.full(rows, 3765.0),
            "rsi_14": np.full(rows, 29.0),
            "atr_14": np.full(rows, 10.0),
            "macd": np.full(rows, -5.0),
            "macd_signal": np.full(rows, -2.0),
            "macd_hist": np.full(rows, -3.0),
            "bb_middle": np.full(rows, 3755.0),
            "bb_upper": np.full(rows, 3780.0),
            "bb_lower": np.full(rows, 3720.0),
        })

        result = self.adaptive_engine.evaluate(df, meta={"symbol": "XAUUSD", "timeframe": "15m"}, exclude_latest=False)

        self.assertEqual(result.action, "SHORT_BIAS")
        self.assertTrue(result.inputs.get("is_overextended"))
        self.assertLessEqual(result.confidence, 40.0)
        warnings_text = " ".join(result.warnings)
        self.assertIn("OVEREXTENSION WARNING", warnings_text)

    def test_clean_setup_retains_full_confidence(self):
        """
        Verifies that when a setup is NOT overextended (e.g. fresh breakout near 20MA with healthy RSI 45),
        the engine maintains healthy confidence and does NOT trigger overextension warnings.
        """
        rows = 70
        df = pd.DataFrame({
            "close": np.full(rows, 3750.0),
            "sma_20": np.full(rows, 3752.0),  # Distance is only 2.0 pts
            "ema_50": np.full(rows, 3760.0),
            "rsi_14": np.full(rows, 45.0),    # Healthy neutral-bearish RSI
            "atr_14": np.full(rows, 8.0),     # Ratio = 2.0 / 8.0 = 0.25x ATR
            "macd": np.full(rows, -1.0),
            "macd_signal": np.full(rows, 0.0),
            "macd_hist": np.full(rows, -1.0),
            "bb_middle": np.full(rows, 3752.0),
            "bb_upper": np.full(rows, 3768.0),
            "bb_lower": np.full(rows, 3736.0),
        })

        result = self.rule_engine.evaluate(df, meta={"symbol": "XAUUSD", "timeframe": "15m"}, exclude_latest=False)

        self.assertEqual(result.action, "SHORT_BIAS")
        self.assertFalse(result.inputs.get("is_overextended"))
        self.assertEqual(result.confidence, 100.0)  # Healthy 100.0 confluence preserved!
        warnings_text = " ".join(result.warnings)
        self.assertNotIn("OVEREXTENSION WARNING", warnings_text)

    def test_post_mortem_diagnose_loss(self):
        """
        Verifies that SignalOutcomeTracker accurately diagnoses why a trade hit SL.
        """
        # Case A: Chased overextension + oversold trap
        inputs_overextended = {
            "atr_14": 10.0,
            "sma_20": 3755.0,
            "rsi_14": 29.5,
            "intraday_metadata": {
                "conflicts": ["M5 trigger is overextended (1.6x ATR from EMA20)"]
            },
            "regime_and_microstructure": {
                "session": "ASIAN_ROLLOVER"
            }
        }
        diagnosis = SignalOutcomeTracker.diagnose_loss(
            sig_inputs=inputs_overextended,
            action="SHORT_SETUP",
            entry_price=3730.0,  # 25.0 pts away from 3755 = 2.5x ATR
            exit_price=3745.0,
        )
        self.assertIn("Chased overextended move", diagnosis)
        self.assertIn("Oversold exhaustion trap", diagnosis)
        self.assertIn("MTF conflict", diagnosis)
        self.assertIn("Low liquidity rollover session", diagnosis)

        # Case B: Clean setup that took normal statistical loss
        inputs_clean = {
            "atr_14": 10.0,
            "sma_20": 3750.0,
            "rsi_14": 46.0,
        }
        clean_diagnosis = SignalOutcomeTracker.diagnose_loss(
            sig_inputs=inputs_clean,
            action="SHORT_SETUP",
            entry_price=3748.0,  # Only 0.2x ATR
            exit_price=3758.0,
        )
        self.assertIn("Normal adverse stop sweep", clean_diagnosis)


if __name__ == "__main__":
    unittest.main()
