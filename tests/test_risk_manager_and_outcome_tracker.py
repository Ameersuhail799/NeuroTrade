"""
Unit tests for Level 6 (Portfolio Risk Management) and Level 7 (Signal Outcome Tracker & Calibration).
"""

import unittest
from datetime import datetime
import pandas as pd

from core.risk_manager import RiskManager, RiskProfile
from core.signal_outcome_tracker import SignalOutcomeTracker, SignalOutcomeRecord
from core.signal_history import SignalRecord
from core.signal_store import SignalStore


class RiskManagerAndOutcomeTrackerTests(unittest.TestCase):
    def test_calculate_lot_size_math_and_flooring(self):
        """
        Verify calculate_lot_size accurately computes lots, floors to volume_step,
        and never rounds up risk.
        """
        contract = {
            "point": 0.01,
            "tick_value": 1.0,
            "volume_step": 0.01,
            "volume_min": 0.01,
            "volume_max": 50.0,
        }

        # 10,000 equity, 1% risk = $100. Stop distance = 2.0 (200 points).
        # raw_volume = 100 / (200 * 1.0) = 0.50
        lots = RiskManager.calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            stop_distance_price=2.0,
            contract_info=contract,
        )
        self.assertEqual(lots, 0.50)

        # Stop distance = 1.85 -> ticks = 185 -> raw_volume = 100 / 185 = 0.54054...
        # Floored to 0.01 step must be 0.54 (never 0.55)
        lots_floor = RiskManager.calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            stop_distance_price=1.85,
            contract_info=contract,
        )
        self.assertEqual(lots_floor, 0.54)
        self.assertLessEqual(lots_floor, 100.0 / 185.0)

    def test_calculate_lot_size_below_min_rejection(self):
        """
        Verify calculate_lot_size rejects lot sizes below broker volume_min.
        """
        contract = {
            "point": 0.01,
            "tick_value": 1.0,
            "volume_step": 0.01,
            "volume_min": 0.01,
            "volume_max": 50.0,
        }

        # $100 equity, 1% risk = $1. Stop distance = 5.0 (500 ticks).
        # raw_volume = 1.0 / 500 = 0.002, which is < 0.01
        with self.assertRaises(ValueError):
            RiskManager.calculate_lot_size(
                equity=100.0,
                risk_pct=1.0,
                stop_distance_price=5.0,
                contract_info=contract,
                raise_on_below_min=True,
            )

        zero_lots = RiskManager.calculate_lot_size(
            equity=100.0,
            risk_pct=1.0,
            stop_distance_price=5.0,
            contract_info=contract,
            raise_on_below_min=False,
        )
        self.assertEqual(zero_lots, 0.0)

    def test_daily_drawdown_circuit_breaker(self):
        """
        Verify daily drawdown circuit breaker trips at >= 2.0% loss.
        """
        starting_equity = 10000.0

        # Loss of $150 (1.5%) -> Allowed
        self.assertTrue(
            RiskManager.check_daily_drawdown_limit(
                starting_daily_equity=starting_equity,
                current_equity=9850.0,
                max_loss_pct=2.0,
            )
        )

        # Loss of $200 (2.0%) -> Blocked
        self.assertFalse(
            RiskManager.check_daily_drawdown_limit(
                starting_daily_equity=starting_equity,
                current_equity=9800.0,
                max_loss_pct=2.0,
            )
        )

        # Loss of $500 (5.0%) -> Blocked
        self.assertFalse(
            RiskManager.check_daily_drawdown_limit(
                starting_daily_equity=starting_equity,
                current_equity=9500.0,
                max_loss_pct=2.0,
            )
        )

    def test_max_open_positions_guardrail(self):
        """
        Verify position limit enforcement per symbol and total.
        """
        positions = [
            {"symbol": "XAUUSD", "ticket": 101},
        ]

        # Same symbol blocked (max_per_symbol=1)
        self.assertFalse(
            RiskManager.check_max_open_positions(
                positions, symbol="XAUUSD", max_per_symbol=1, max_total=2
            )
        )

        # Different symbol allowed
        self.assertTrue(
            RiskManager.check_max_open_positions(
                positions, symbol="EURUSD", max_per_symbol=1, max_total=2
            )
        )

        # Two positions open -> Total limit of 2 reached
        positions.append({"symbol": "EURUSD", "ticket": 102})
        self.assertFalse(
            RiskManager.check_max_open_positions(
                positions, symbol="GBPUSD", max_per_symbol=1, max_total=2
            )
        )

    def test_signal_outcome_tracker_hit_tp1_and_hit_sl(self):
        """
        Verify SignalOutcomeTracker simulates next-bar entry, evaluates intrabar
        stops/targets, and enforces pessimistic stop-first tie breaking.
        """
        m5_data = pd.DataFrame([
            {"time": "2026-05-12 10:00:00", "open": 2350.0, "high": 2351.0, "low": 2349.0, "close": 2350.5},
            {"time": "2026-05-12 10:05:00", "open": 2350.5, "high": 2353.0, "low": 2350.0, "close": 2352.0},
            {"time": "2026-05-12 10:10:00", "open": 2352.0, "high": 2356.0, "low": 2351.0, "close": 2355.5},
        ])

        # Test Long setup hitting TP1
        long_signal = {
            "record_id": 1,
            "symbol": "XAUUSD",
            "decision_time": "2026-05-12 10:00:00",
            "action": "LONG_SETUP",
            "confidence": 80.0,
            "inputs": {
                "intraday_metadata": {
                    "direction": "long",
                    "entry_reference": 2350.5,
                    "stop_loss": 2345.0,
                    "take_profit_1": 2355.0,
                    "take_profit_2": 2362.0,
                }
            },
        }

        outcomes = SignalOutcomeTracker.evaluate_outcomes([long_signal], m5_data)
        self.assertEqual(len(outcomes), 1)
        res = outcomes[0]
        self.assertEqual(res.outcome, "HIT_TP1 (+1.5R)")
        self.assertEqual(res.outcome_r, 1.5)
        self.assertEqual(res.holding_bars, 2)

        # Test Stop Loss Hit
        m5_loss_data = pd.DataFrame([
            {"time": "2026-05-12 10:00:00", "open": 2350.0, "high": 2351.0, "low": 2349.0, "close": 2350.5},
            {"time": "2026-05-12 10:05:00", "open": 2350.5, "high": 2351.0, "low": 2344.0, "close": 2344.5},
        ])
        loss_outcomes = SignalOutcomeTracker.evaluate_outcomes([long_signal], m5_loss_data)
        self.assertEqual(loss_outcomes[0].outcome, "HIT_SL (-1.0R)")
        self.assertEqual(loss_outcomes[0].outcome_r, -1.0)

        # Test Pessimistic Stop-First Tie-Breaking (bar touches both SL and TP1)
        m5_tie_data = pd.DataFrame([
            {"time": "2026-05-12 10:00:00", "open": 2350.0, "high": 2351.0, "low": 2349.0, "close": 2350.5},
            {"time": "2026-05-12 10:05:00", "open": 2350.5, "high": 2357.0, "low": 2344.0, "close": 2352.0},
        ])
        tie_outcomes = SignalOutcomeTracker.evaluate_outcomes([long_signal], m5_tie_data)
        self.assertEqual(tie_outcomes[0].outcome, "HIT_SL (-1.0R)")
        self.assertEqual(tie_outcomes[0].outcome_r, -1.0)

    def test_signal_outcome_tracker_stopped_at_breakeven(self):
        """
        Verify that after hitting TP1, stop moves to breakeven and triggers STOPPED_AT_BE (0.0R).
        """
        m5_data = pd.DataFrame([
            {"time": "2026-05-12 10:00:00", "open": 2350.0, "high": 2351.0, "low": 2349.0, "close": 2350.0},
            # Bar 1 enters at 2350.0, hits TP1 at 2355.0
            {"time": "2026-05-12 10:05:00", "open": 2350.0, "high": 2355.5, "low": 2349.5, "close": 2354.0},
            # Bar 2 pulls back and touches breakeven entry at 2350.0
            {"time": "2026-05-12 10:10:00", "open": 2354.0, "high": 2354.5, "low": 2349.0, "close": 2351.0},
        ])

        signal = {
            "record_id": 2,
            "symbol": "XAUUSD",
            "decision_time": "2026-05-12 10:00:00",
            "action": "LONG_SETUP",
            "confidence": 75.0,
            "inputs": {
                "intraday_metadata": {
                    "direction": "long",
                    "entry_reference": 2350.0,
                    "stop_loss": 2345.0,
                    "take_profit_1": 2355.0,
                    "take_profit_2": 2365.0,
                }
            },
        }

        outcomes = SignalOutcomeTracker.evaluate_outcomes([signal], m5_data)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].outcome, "STOPPED_AT_BE (0.0R)")
        self.assertEqual(outcomes[0].outcome_r, 0.0)

    def test_calibration_report_confluence_buckets(self):
        """
        Verify calibration report categorizes signals into Low/Mod, High, and Prime
        buckets and formats metrics cleanly.
        """
        records = [
            SignalOutcomeRecord(1, "XAUUSD", "2026-05-12 10:00", "LONG_SETUP", 68.0, "HIT_SL (-1.0R)", -1.0, "2026-05-12 10:15", 3, 2350.0, 2345.0),
            SignalOutcomeRecord(2, "XAUUSD", "2026-05-12 11:00", "LONG_SETUP", 70.0, "HIT_TP1 (+1.5R)", 1.5, "2026-05-12 11:30", 6, 2350.0, 2355.0),
            SignalOutcomeRecord(3, "XAUUSD", "2026-05-12 12:00", "SHORT_SETUP", 80.0, "HIT_TP2 (+2.0R)", 2.0, "2026-05-12 12:45", 9, 2350.0, 2340.0),
            SignalOutcomeRecord(4, "XAUUSD", "2026-05-12 13:00", "LONG_SETUP", 92.0, "HIT_TP2 (+2.0R)", 2.0, "2026-05-12 13:40", 8, 2350.0, 2360.0),
        ]

        report = SignalOutcomeTracker.compute_calibration_report(records)
        self.assertIn("NEUROTRADE AI CONFLUENCE CALIBRATION REPORT", report)
        self.assertIn("Low/Mod (60.0 - 74.9)", report)
        self.assertIn("High    (75.0 - 84.9)", report)
        self.assertIn("Prime   (85.0 - 100.0)", report)
        self.assertIn("TOTAL", report)

    def test_signal_store_outcome_persistence(self):
        """
        Verify SignalStore persists and reloads outcome records in intraday_signal_outcomes table.
        """
        store = SignalStore(db_path=":memory:")
        self.assertTrue(store.connect())

        # Save a signal record
        record = SignalRecord(
            record_id=0,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            engine="intraday_mtf",
            engine_version="2.0.0",
            symbol="XAUUSD",
            timeframe="1H/15m/5m",
            decision_time="2026-05-12 10:00:00",
            action="LONG_SETUP",
            score=2.5,
            confidence=85.0,
            rows_used=500,
            exclude_latest=True,
            inputs={"intraday_metadata": {"entry_reference": 2350.0}},
            reasons=["Bullish alignment"],
            warnings=[],
            weights={},
        )
        sig_id = store.save(record)
        self.assertIsNotNone(sig_id)

        # Save an outcome
        outcome = SignalOutcomeRecord(
            signal_id=sig_id,
            symbol="XAUUSD",
            decision_time="2026-05-12 10:00:00",
            action="LONG_SETUP",
            confluence_score=85.0,
            outcome="HIT_TP1 (+1.5R)",
            outcome_r=1.5,
            resolved_at="2026-05-12 10:30:00",
            holding_bars=6,
            entry_price=2350.0,
            exit_price=2355.0,
            notes="Clean TP1 hit",
        )
        self.assertTrue(store.save_outcome(outcome))

        # Load outcomes
        outcomes_map = store.load_outcomes()
        self.assertIn(sig_id, outcomes_map)
        self.assertEqual(outcomes_map[sig_id]["outcome"], "HIT_TP1 (+1.5R)")
        self.assertEqual(outcomes_map[sig_id]["outcome_r"], 1.5)

        # Load all with outcomes
        records_with_outcomes = store.load_all_with_outcomes()
        self.assertEqual(len(records_with_outcomes), 1)
        self.assertIn("outcome", records_with_outcomes[0].inputs)
        self.assertEqual(
            records_with_outcomes[0].inputs["outcome"]["outcome"], "HIT_TP1 (+1.5R)"
        )

        store.close()


if __name__ == "__main__":
    unittest.main()
