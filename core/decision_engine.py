"""
Rule-based decision engine for NeuroTrade AI.

This is Part 5: rule-based decision logic only.

Important honesty constraints:
- The output is a heuristic bias, not a trading signal.
- Confidence is a weighted rule score, not a calibrated win probability.
- No orders are sent.
- No future data may be used. By default, the latest candle is excluded
  because it may still be forming.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any

import numpy as np
import pandas as pd


@dataclass
class RuleResult:
    name: str
    description: str
    weight: float
    raw_score: float
    score: float
    valid: bool
    note: str = ""


@dataclass
class DecisionResult:
    version: str
    action: str
    score: float
    confidence: float
    decision_time: str
    symbol: str
    timeframe: str
    rows_used: int
    exclude_latest: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rules: List[RuleResult] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)


class RuleBasedDecisionEngine:
    """
    Fixed-weight rule-based engine.

    Rules are intentionally simple and explainable:
    - Close vs SMA20
    - SMA20 vs EMA50
    - RSI zone
    - MACD vs MACD signal
    - Close position inside Bollinger Bands

    Adaptive weights are intentionally NOT implemented here.
    Weight adaptation belongs to Part 7.
    """

    VERSION = "rule-based-v1"

    REQUIRED_COLUMNS = [
        "close",
        "sma_20",
        "ema_50",
        "rsi_14",
        "atr_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_middle",
        "bb_upper",
        "bb_lower",
    ]

    WEIGHTS = {
        "trend_close_sma20": 20.0,
        "trend_sma20_ema50": 20.0,
        "momentum_rsi": 20.0,
        "macd_direction": 20.0,
        "bollinger_position": 20.0,
    }

    LONG_THRESHOLD = 40.0
    SHORT_THRESHOLD = -40.0
    MIN_VALID_RULES = 4
    MIN_RECOMMENDED_ROWS = 60

    def evaluate(
        self,
        df: pd.DataFrame,
        meta: Dict[str, Any] = None,
        exclude_latest: bool = True,
    ) -> DecisionResult:
        if df is None or len(df) == 0:
            raise ValueError("Decision engine received an empty DataFrame.")

        missing = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in df.columns
        ]
        if missing:
            raise ValueError(
                "Decision engine requires Part 4 indicator columns. "
                f"Missing columns: {', '.join(missing)}"
            )

        meta = meta or {}
        work = df.copy().reset_index(drop=True)
        warnings: List[str] = []

        if exclude_latest:
            if len(work) <= 1:
                raise ValueError("Not enough candles to evaluate a decision.")

            work = work.iloc[:-1].copy().reset_index(drop=True)
            warnings.append(
                "Latest candle excluded to reduce look-ahead risk."
            )
        else:
            warnings.append(
                "Latest candle included. It may still be forming and "
                "can introduce look-ahead bias."
            )

        if len(work) < self.MIN_RECOMMENDED_ROWS:
            warnings.append(
                f"Only {len(work)} candles available. "
                f"At least {self.MIN_RECOMMENDED_ROWS} are recommended "
                "for stable indicator warm-up."
            )

        row = work.iloc[-1]
        decision_time = str(row.get("time", "unavailable"))

        close = self._float(row.get("close"))
        if not self._finite(close):
            raise ValueError("Decision candle close is missing or invalid.")

        values = {
            "sma_20": self._float(row.get("sma_20")),
            "ema_50": self._float(row.get("ema_50")),
            "rsi_14": self._float(row.get("rsi_14")),
            "atr_14": self._float(row.get("atr_14")),
            "macd": self._float(row.get("macd")),
            "macd_signal": self._float(row.get("macd_signal")),
            "macd_hist": self._float(row.get("macd_hist")),
            "bb_middle": self._float(row.get("bb_middle")),
            "bb_upper": self._float(row.get("bb_upper")),
            "bb_lower": self._float(row.get("bb_lower")),
        }

        rules: List[RuleResult] = []

        def add_rule(
            name: str,
            description: str,
            raw_score: float,
            valid: bool,
            note: str = "",
        ) -> None:
            weight = self.WEIGHTS[name]
            score = float(raw_score) * weight if valid else 0.0
            rules.append(
                RuleResult(
                    name=name,
                    description=description,
                    weight=weight,
                    raw_score=float(raw_score),
                    score=score,
                    valid=valid,
                    note=note,
                )
            )

        # Rule 1: Close vs SMA20
        sma20 = values["sma_20"]
        valid = self._finite(sma20)
        if valid:
            if close > sma20:
                raw = 1.0
                note = "Close above SMA20."
            elif close < sma20:
                raw = -1.0
                note = "Close below SMA20."
            else:
                raw = 0.0
                note = "Close equal to SMA20."
        else:
            raw = 0.0
            note = "SMA20 not available."
        add_rule(
            "trend_close_sma20",
            "Close vs SMA20",
            raw,
            valid,
            note,
        )

        # Rule 2: SMA20 vs EMA50
        ema50 = values["ema_50"]
        valid = self._finite(sma20) and self._finite(ema50)
        if valid:
            if sma20 > ema50:
                raw = 1.0
                note = "SMA20 above EMA50."
            elif sma20 < ema50:
                raw = -1.0
                note = "SMA20 below EMA50."
            else:
                raw = 0.0
                note = "SMA20 equal to EMA50."
        else:
            raw = 0.0
            note = "SMA20/EMA50 not available."
        add_rule(
            "trend_sma20_ema50",
            "SMA20 vs EMA50",
            raw,
            valid,
            note,
        )

        # Rule 3: RSI zone
        rsi = values["rsi_14"]
        valid = self._finite(rsi)
        if valid:
            if rsi > 70.0:
                raw = 0.0
                note = "RSI overbought; no directional score."
                warnings.append("RSI is above 70. Long entries may be overextended.")
            elif rsi < 30.0:
                raw = 0.0
                note = "RSI oversold; no directional score."
                warnings.append("RSI is below 30. Short entries may be overextended.")
            elif rsi > 50.0:
                raw = 1.0
                note = "RSI above 50."
            elif rsi < 50.0:
                raw = -1.0
                note = "RSI below 50."
            else:
                raw = 0.0
                note = "RSI exactly 50."
        else:
            raw = 0.0
            note = "RSI not available."
        add_rule(
            "momentum_rsi",
            "RSI(14) zone",
            raw,
            valid,
            note,
        )

        # Rule 4: MACD direction
        macd = values["macd"]
        macd_signal = values["macd_signal"]
        valid = self._finite(macd) and self._finite(macd_signal)
        if valid:
            if macd > macd_signal:
                raw = 1.0
                note = "MACD above signal."
            elif macd < macd_signal:
                raw = -1.0
                note = "MACD below signal."
            else:
                raw = 0.0
                note = "MACD equal to signal."
        else:
            raw = 0.0
            note = "MACD/signal not available."
        add_rule(
            "macd_direction",
            "MACD vs signal",
            raw,
            valid,
            note,
        )

        # Rule 5: Bollinger position
        bb_middle = values["bb_middle"]
        bb_upper = values["bb_upper"]
        bb_lower = values["bb_lower"]
        valid = (
            self._finite(bb_middle)
            and self._finite(bb_upper)
            and self._finite(bb_lower)
            and bb_upper >= bb_lower
        )

        if valid:
            if close > bb_upper:
                raw = 0.0
                note = "Close above upper Bollinger band; overextended."
                warnings.append(
                    "Close is above the upper Bollinger band. "
                    "Long entries may be overextended."
                )
            elif close < bb_lower:
                raw = 0.0
                note = "Close below lower Bollinger band; overextended."
                warnings.append(
                    "Close is below the lower Bollinger band. "
                    "Short entries may be overextended."
                )
            elif close > bb_middle:
                raw = 1.0
                note = "Close above Bollinger middle band."
            elif close < bb_middle:
                raw = -1.0
                note = "Close below Bollinger middle band."
            else:
                raw = 0.0
                note = "Close equal to Bollinger middle band."
        else:
            raw = 0.0
            note = "Bollinger bands not available."
        add_rule(
            "bollinger_position",
            "Close vs Bollinger bands",
            raw,
            valid,
            note,
        )

        # ATR is used as a data-quality/volatility filter, not a directional rule.
        atr = values["atr_14"]
        if not self._finite(atr):
            warnings.append("ATR(14) is not available.")
        elif atr <= 0.0:
            warnings.append("ATR(14) is zero or negative; volatility filter failed.")

        valid_rules = [rule for rule in rules if rule.valid]
        score = float(sum(rule.score for rule in rules))
        confidence = float(min(100.0, abs(score)))

        if len(valid_rules) < self.MIN_VALID_RULES:
            action = "NO_TRADE"
            warnings.append(
                f"Only {len(valid_rules)} valid rules available. "
                f"At least {self.MIN_VALID_RULES} are required."
            )
        elif score >= self.LONG_THRESHOLD:
            action = "LONG_BIAS"
        elif score <= self.SHORT_THRESHOLD:
            action = "SHORT_BIAS"
        else:
            action = "NO_TRADE"
            warnings.append(
                "Score is below the rule threshold for a directional bias."
            )

        reasons: List[str] = []
        for rule in rules:
            if not rule.valid:
                continue

            if rule.score > 0:
                reasons.append(
                    f"+{rule.score:.0f} {rule.description}: {rule.note}"
                )
            elif rule.score < 0:
                reasons.append(
                    f"{rule.score:.0f} {rule.description}: {rule.note}"
                )
            else:
                reasons.append(
                    f"0 {rule.description}: {rule.note}"
                )

        inputs = {
            "close": self._optional(close),
            "sma_20": self._optional(values["sma_20"]),
            "ema_50": self._optional(values["ema_50"]),
            "rsi_14": self._optional(values["rsi_14"]),
            "atr_14": self._optional(values["atr_14"]),
            "macd": self._optional(values["macd"]),
            "macd_signal": self._optional(values["macd_signal"]),
            "macd_hist": self._optional(values["macd_hist"]),
            "bb_middle": self._optional(values["bb_middle"]),
            "bb_upper": self._optional(values["bb_upper"]),
            "bb_lower": self._optional(values["bb_lower"]),
        }

        return DecisionResult(
            version=self.VERSION,
            action=action,
            score=score,
            confidence=confidence,
            decision_time=decision_time,
            symbol=str(meta.get("symbol", "UNKNOWN")),
            timeframe=str(meta.get("timeframe", "UNKNOWN")),
            rows_used=int(len(work)),
            exclude_latest=bool(exclude_latest),
            reasons=reasons,
            warnings=warnings,
            rules=rules,
            inputs=inputs,
        )

    @staticmethod
    def _float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    @staticmethod
    def _finite(value) -> bool:
        try:
            return bool(np.isfinite(float(value)))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _optional(value):
        try:
            value = float(value)
            if np.isfinite(value):
                return round(value, 5)
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    def format_report(result: DecisionResult) -> str:
        lines = []

        lines.append("NeuroTrade AI Decision Engine")
        lines.append(f"Version: {result.version}")
        lines.append(
            f"Symbol: {result.symbol} | Timeframe: {result.timeframe}"
        )
        lines.append(f"Decision candle time: {result.decision_time}")
        lines.append(
            f"Rows used: {result.rows_used} | "
            f"Exclude latest candle: {'Yes' if result.exclude_latest else 'No'}"
        )
        lines.append("")

        lines.append(f"Action: {result.action}")
        lines.append(
            f"Heuristic confidence: {result.confidence:.0f}/100"
        )
        lines.append(
            "Confidence is a weighted rule score, NOT a win probability."
        )
        lines.append("")

        lines.append("Rule contributions:")
        if result.reasons:
            for reason in result.reasons:
                lines.append(f"  {reason}")
        else:
            lines.append("  No valid rule contributions.")

        if result.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"  {warning}")

        lines.append("")
        lines.append("Decision inputs:")
        for key, value in result.inputs.items():
            lines.append(f"  {key}: {value}")

        lines.append("")
        lines.append(
            "No order is sent. This is a rule-based heuristic, "
            "not trading advice and not a calibrated probability."
        )

        return "\n".join(lines)