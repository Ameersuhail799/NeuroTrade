"""
Live Paper-Trading Forward Tracker & Confluence Calibration for Level 7.

Evaluates forward outcomes for recorded intraday signals against subsequent M5
market data. Analyzes empirical calibration across heuristic confluence score buckets.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class SignalOutcomeRecord:
    """
    Resolved forward tracking outcome for a recorded intraday setup.
    """
    signal_id: int
    symbol: str
    decision_time: str
    action: str
    confluence_score: float
    outcome: str            # 'HIT_TP1 (+1.5R)', 'HIT_TP2 (+2.0R)', 'STOPPED_AT_BE (0.0R)', 'HIT_SL (-1.0R)', 'EXPIRED', 'OPEN'
    outcome_r: float        # e.g. 1.5, 2.0, 0.0, -1.0
    resolved_at: str        # Timestamp string of resolving bar
    holding_bars: int       # Number of M5 bars held
    entry_price: float      # Actual next-bar fill price
    exit_price: float       # Price at exit/resolution
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "decision_time": self.decision_time,
            "action": self.action,
            "confluence_score": self.confluence_score,
            "outcome": self.outcome,
            "outcome_r": self.outcome_r,
            "resolved_at": self.resolved_at,
            "holding_bars": self.holding_bars,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "notes": self.notes,
        }


class SignalOutcomeTracker:
    """
    Tracks and calibrates real forward outcomes of recorded intraday signals.
    """

    @staticmethod
    def evaluate_outcomes(
        signals: List[Any],
        m5_candles_df: pd.DataFrame,
        point: float = 0.01,
        max_holding_bars: int = 288,
    ) -> List[SignalOutcomeRecord]:
        """
        Evaluate recorded signals against subsequent M5 candles without lookahead.

        Parameters:
        -----------
        signals: List of SignalRecord objects or dictionaries.
        m5_candles_df: DataFrame with M5 candles ('time', 'open', 'high', 'low', 'close').
        point: Instrument point size.
        max_holding_bars: Maximum holding period before expiry (default 288 = 24h on M5).
        """
        if m5_candles_df.empty or "time" not in m5_candles_df.columns:
            return []

        # Ensure candles are sorted chronologically
        candles = m5_candles_df.sort_values("time").reset_index(drop=True)
        results: List[SignalOutcomeRecord] = []

        for sig in signals:
            if isinstance(sig, dict):
                action = sig.get("action", "")
                sig_id = int(sig.get("id") or sig.get("record_id", 0))
                symbol = str(sig.get("symbol", ""))
                decision_time = str(sig.get("decision_time", ""))
                confidence = float(sig.get("confidence", 0.0))
                inputs = sig.get("inputs", {})
            else:
                action = getattr(sig, "action", "")
                sig_id = int(getattr(sig, "record_id", 0))
                symbol = str(getattr(sig, "symbol", ""))
                decision_time = str(getattr(sig, "decision_time", ""))
                confidence = float(getattr(sig, "confidence", 0.0))
                inputs = getattr(sig, "inputs", {})

            if action not in ("LONG_SETUP", "SHORT_SETUP"):
                continue

            intraday_meta = inputs.get("intraday_metadata", {}) if isinstance(inputs, dict) else {}
            stop_loss = intraday_meta.get("stop_loss")
            tp1 = intraday_meta.get("take_profit_1")
            tp2 = intraday_meta.get("take_profit_2")
            entry_ref = intraday_meta.get("entry_reference")
            direction = intraday_meta.get(
                "direction", "long" if action == "LONG_SETUP" else "short"
            ).lower()

            if stop_loss is None or tp1 is None:
                continue

            stop_loss = float(stop_loss)
            tp1 = float(tp1)
            tp2_val = float(tp2) if tp2 is not None else (
                tp1 + abs(tp1 - stop_loss) if direction == "long" else tp1 - abs(tp1 - stop_loss)
            )

            # Restrict strictly to candles AFTER decision_time
            subsequent = candles[candles["time"] > decision_time]
            if subsequent.empty:
                results.append(
                    SignalOutcomeRecord(
                        signal_id=sig_id,
                        symbol=symbol,
                        decision_time=decision_time,
                        action=action,
                        confluence_score=confidence,
                        outcome="OPEN",
                        outcome_r=0.0,
                        resolved_at="",
                        holding_bars=0,
                        entry_price=0.0,
                        exit_price=0.0,
                        notes="No forward candles available yet.",
                    )
                )
                continue

            # Enforce realistic next-bar open fill
            entry_price = float(subsequent.iloc[0]["open"])
            current_stop = stop_loss
            tp1_hit = False
            resolved = False
            outcome_str = "OPEN"
            outcome_r = 0.0
            resolved_at = ""
            exit_price = 0.0
            holding_bars = 0

            for _, bar in subsequent.iterrows():
                holding_bars += 1
                b_time = str(bar["time"])
                b_high = float(bar["high"])
                b_low = float(bar["low"])
                b_close = float(bar["close"])

                if direction == "long":
                    if not tp1_hit:
                        # Pessimistic stop-first tie breaking
                        if b_low <= current_stop and b_high >= tp1:
                            outcome_str = "HIT_SL (-1.0R)"
                            outcome_r = -1.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_low <= current_stop:
                            outcome_str = "HIT_SL (-1.0R)"
                            outcome_r = -1.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_high >= tp1:
                            tp1_hit = True
                            current_stop = entry_price  # Move stop to breakeven
                            if b_high >= tp2_val:
                                outcome_str = "HIT_TP2 (+2.0R)"
                                outcome_r = 2.0
                                resolved_at = b_time
                                exit_price = tp2_val
                                resolved = True
                                break
                    else:
                        # TP1 already hit, testing breakeven stop or TP2
                        if b_low <= current_stop and b_high >= tp2_val:
                            outcome_str = "STOPPED_AT_BE (0.0R)"
                            outcome_r = 0.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_low <= current_stop:
                            outcome_str = "STOPPED_AT_BE (0.0R)"
                            outcome_r = 0.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_high >= tp2_val:
                            outcome_str = "HIT_TP2 (+2.0R)"
                            outcome_r = 2.0
                            resolved_at = b_time
                            exit_price = tp2_val
                            resolved = True
                            break

                else:  # Short direction
                    if not tp1_hit:
                        # Pessimistic stop-first tie breaking
                        if b_high >= current_stop and b_low <= tp1:
                            outcome_str = "HIT_SL (-1.0R)"
                            outcome_r = -1.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_high >= current_stop:
                            outcome_str = "HIT_SL (-1.0R)"
                            outcome_r = -1.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_low <= tp1:
                            tp1_hit = True
                            current_stop = entry_price  # Move stop to breakeven
                            if b_low <= tp2_val:
                                outcome_str = "HIT_TP2 (+2.0R)"
                                outcome_r = 2.0
                                resolved_at = b_time
                                exit_price = tp2_val
                                resolved = True
                                break
                    else:
                        # TP1 already hit, testing breakeven stop or TP2
                        if b_high >= current_stop and b_low <= tp2_val:
                            outcome_str = "STOPPED_AT_BE (0.0R)"
                            outcome_r = 0.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_high >= current_stop:
                            outcome_str = "STOPPED_AT_BE (0.0R)"
                            outcome_r = 0.0
                            resolved_at = b_time
                            exit_price = current_stop
                            resolved = True
                            break
                        elif b_low <= tp2_val:
                            outcome_str = "HIT_TP2 (+2.0R)"
                            outcome_r = 2.0
                            resolved_at = b_time
                            exit_price = tp2_val
                            resolved = True
                            break

                if holding_bars >= max_holding_bars:
                    if not resolved:
                        if tp1_hit:
                            outcome_str = "HIT_TP1 (+1.5R)"
                            outcome_r = 1.5
                        else:
                            outcome_str = "EXPIRED"
                            outcome_r = 0.0
                        resolved_at = b_time
                        exit_price = b_close
                        resolved = True
                    break

            if not resolved:
                if tp1_hit:
                    outcome_str = "HIT_TP1 (+1.5R)"
                    outcome_r = 1.5
                    resolved_at = str(subsequent.iloc[-1]["time"])
                    exit_price = float(subsequent.iloc[-1]["close"])
                else:
                    outcome_str = "OPEN"
                    outcome_r = 0.0
                    resolved_at = ""
                    exit_price = 0.0

            results.append(
                SignalOutcomeRecord(
                    signal_id=sig_id,
                    symbol=symbol,
                    decision_time=decision_time,
                    action=action,
                    confluence_score=confidence,
                    outcome=outcome_str,
                    outcome_r=outcome_r,
                    resolved_at=resolved_at,
                    holding_bars=holding_bars,
                    entry_price=entry_price,
                    exit_price=exit_price,
                )
            )

        return results

    @staticmethod
    def compute_calibration_report(resolved_records: List[SignalOutcomeRecord]) -> str:
        """
        Groups resolved signals by confluence score buckets and computes realized
        win rate, average R-multiple, and profit factor to verify empirical calibration.
        """
        buckets = [
            ("Low/Mod (60.0 - 74.9)", 60.0, 75.0),
            ("High    (75.0 - 84.9)", 75.0, 85.0),
            ("Prime   (85.0 - 100.0)", 85.0, 100.01),
        ]

        lines = [
            "=" * 92,
            "                    NEUROTRADE AI CONFLUENCE CALIBRATION REPORT",
            "=" * 92,
            f"{'Confluence Bucket':<24} {'Total':>6} {'Wins':>6} {'Losses':>7} {'BE/Exp':>7} {'Win Rate':>10} {'Avg R':>10} {'Profit Factor':>14}",
            "-" * 92,
        ]

        total_all = 0
        wins_all = 0
        losses_all = 0
        be_all = 0
        pos_r_all = 0.0
        neg_r_all = 0.0
        total_r_all = 0.0

        for name, lower, upper in buckets:
            bucket_recs = [
                r for r in resolved_records
                if lower <= r.confluence_score < upper and r.outcome != "OPEN"
            ]
            total = len(bucket_recs)
            wins = sum(1 for r in bucket_recs if r.outcome_r > 0)
            losses = sum(1 for r in bucket_recs if r.outcome_r < 0)
            be_exp = sum(1 for r in bucket_recs if r.outcome_r == 0)

            pos_r = sum(r.outcome_r for r in bucket_recs if r.outcome_r > 0)
            neg_r = sum(abs(r.outcome_r) for r in bucket_recs if r.outcome_r < 0)
            tot_r = sum(r.outcome_r for r in bucket_recs)

            win_rate = (wins / total * 100.0) if total > 0 else 0.0
            avg_r = (tot_r / total) if total > 0 else 0.0
            pf = (pos_r / neg_r) if neg_r > 0 else (99.99 if pos_r > 0 else 0.0)
            pf_str = f"{pf:6.2f}" if pf < 90 else ("   Inf" if pos_r > 0 else "  0.00")

            lines.append(
                f"{name:<24} {total:>6} {wins:>6} {losses:>7} {be_exp:>7} {win_rate:>9.2f}% {avg_r:>+9.2f}R {pf_str:>14}"
            )

            total_all += total
            wins_all += wins
            losses_all += losses
            be_all += be_exp
            pos_r_all += pos_r
            neg_r_all += neg_r
            total_r_all += tot_r

        lines.append("-" * 92)
        total_win_rate = (wins_all / total_all * 100.0) if total_all > 0 else 0.0
        total_avg_r = (total_r_all / total_all) if total_all > 0 else 0.0
        total_pf = (pos_r_all / neg_r_all) if neg_r_all > 0 else (99.99 if pos_r_all > 0 else 0.0)
        total_pf_str = f"{total_pf:6.2f}" if total_pf < 90 else ("   Inf" if pos_r_all > 0 else "  0.00")

        lines.append(
            f"{'TOTAL':<24} {total_all:>6} {wins_all:>6} {losses_all:>7} {be_all:>7} {total_win_rate:>9.2f}% {total_avg_r:>+9.2f}R {total_pf_str:>14}"
        )
        lines.append("=" * 92)
        lines.append("Empirical Calibration Rule: Realized Win Rate and Avg R should rise monotonically")
        lines.append("from Low/Mod -> High -> Prime buckets to validate score-to-edge alignment.")
        lines.append("=" * 92)

        return "\n".join(lines)
