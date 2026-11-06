"""
Adaptive decision engine for Part 7.

Uses persisted or in-memory adaptive rule weights.
This is heuristic weighted scoring, not a calibrated probability model.
"""

from typing import Dict, Any

import numpy as np
import pandas as pd

from core.decision_engine import DecisionResult, RuleResult
from core.rule_features import (
    RULE_NAMES,
    DEFAULT_WEIGHTS,
    RULE_DESCRIPTIONS,
    LONG_THRESHOLD,
    SHORT_THRESHOLD,
    MIN_VALID_RULES,
    compute_rule_features,
    score_from_features,
    action_from_score,
    as_float,
    is_finite,
)


class AdaptiveDecisionEngine:
    def __init__(self, weights: Dict[str, float] = None):
        if weights is None:
            self.weights = dict(DEFAULT_WEIGHTS)
        else:
            self.weights = {
                rule_name: float(weights.get(rule_name, DEFAULT_WEIGHTS[rule_name]))
                for rule_name in RULE_NAMES
            }

    def evaluate(
        self,
        df: pd.DataFrame,
        meta: Dict[str, Any] = None,
        exclude_latest: bool = True,
    ) -> DecisionResult:
        if df is None or len(df) == 0:
            raise ValueError("Adaptive decision engine received an empty DataFrame.")

        if "close" not in df.columns:
            raise ValueError("Adaptive decision engine requires a close column.")

        meta = meta or {}
        work = df.copy().reset_index(drop=True)
        warnings = []

        if exclude_latest:
            if len(work) <= 1:
                raise ValueError("Not enough candles to evaluate a decision.")

            work = work.iloc[:-1].copy().reset_index(drop=True)
            warnings.append("Latest candle excluded to reduce look-ahead risk.")
        else:
            warnings.append(
                "Latest candle included. It may still be forming and "
                "can introduce look-ahead bias."
            )

        row = work.iloc[-1]
        decision_time = str(row.get("time", "unavailable"))

        features = compute_rule_features(row)
        score, valid_rules = score_from_features(features, self.weights)
        action = action_from_score(score, valid_rules)

        if valid_rules < MIN_VALID_RULES:
            warnings.append(
                f"Only {valid_rules} valid rules available. "
                f"At least {MIN_VALID_RULES} are required."
            )

        if action == "NO_TRADE" and valid_rules >= MIN_VALID_RULES:
            warnings.append("Score is below the rule threshold for a directional bias.")

        rules = []
        reasons = []

        for rule_name in RULE_NAMES:
            feature = features.get(rule_name, {})
            raw = float(feature.get("raw", 0.0))
            valid = bool(feature.get("valid", False))
            note = str(feature.get("note", ""))
            weight = float(self.weights.get(rule_name, 0.0))
            weighted_score = raw * weight if valid else 0.0

            rules.append(
                RuleResult(
                    name=rule_name,
                    description=RULE_DESCRIPTIONS.get(rule_name, rule_name),
                    weight=weight,
                    raw_score=raw,
                    score=weighted_score,
                    valid=valid,
                    note=note,
                )
            )

            if not valid:
                continue

            if weighted_score > 0:
                reasons.append(
                    f"+{weighted_score:.1f} "
                    f"{RULE_DESCRIPTIONS.get(rule_name, rule_name)}: {note}"
                )
            elif weighted_score < 0:
                reasons.append(
                    f"{weighted_score:.1f} "
                    f"{RULE_DESCRIPTIONS.get(rule_name, rule_name)}: {note}"
                )
            else:
                reasons.append(
                    f"0.0 {RULE_DESCRIPTIONS.get(rule_name, rule_name)}: {note}"
                )

        total_weight = sum(
            max(0.0, float(self.weights.get(rule_name, 0.0)))
            for rule_name in RULE_NAMES
        )

        if total_weight <= 0.0:
            total_weight = 1.0

        confidence = min(100.0, abs(score) / total_weight * 100.0)

        inputs = {
            "close": self._optional(row.get("close")),
            "sma_20": self._optional(row.get("sma_20")),
            "ema_50": self._optional(row.get("ema_50")),
            "rsi_14": self._optional(row.get("rsi_14")),
            "atr_14": self._optional(row.get("atr_14")),
            "macd": self._optional(row.get("macd")),
            "macd_signal": self._optional(row.get("macd_signal")),
            "macd_hist": self._optional(row.get("macd_hist")),
            "bb_middle": self._optional(row.get("bb_middle")),
            "bb_upper": self._optional(row.get("bb_upper")),
            "bb_lower": self._optional(row.get("bb_lower")),
        }

        return DecisionResult(
            version="adaptive-weighted-scoring-v1",
            action=action,
            score=float(score),
            confidence=float(confidence),
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
    def _optional(value):
        numeric = as_float(value)
        if is_finite(numeric):
            return round(numeric, 5)
        return None