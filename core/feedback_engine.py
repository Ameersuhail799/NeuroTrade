"""
Feedback loop engine for Part 7.

This engine creates historical feedback samples, adapts rule weights, and
evaluates the adapted weights on an out-of-sample validation slice.

Honesty constraints:
- Chronological split only, no shuffling.
- Training updates only use the train slice.
- Validation metrics are reported out-of-sample.
- Outcomes are close-to-close and exclude spread, commission and slippage.
- This is heuristic weighted scoring, not a profitability promise.
"""

from dataclasses import dataclass
from typing import List, Dict, Any

from core.rule_features import (
    RULE_NAMES,
    DEFAULT_WEIGHTS,
    MIN_VALID_RULES,
    compute_rule_features,
    score_from_features,
    action_from_score,
    clip_weight,
    format_weights,
    as_float,
    is_finite,
)


@dataclass
class FeedbackSample:
    index: int
    decision_time: str
    close: float
    future_close: float
    future_return_points: float
    outcome_label: int
    split: str
    raw_scores: Dict[str, float]
    valid_rules: int


class FeedbackEngine:
    """
    Builds feedback samples and adapts rule weights.
    """

    @staticmethod
    def build_samples(
        df,
        point: float,
        horizon: int,
        min_outcome_points: float,
        train_fraction: float,
    ) -> List[FeedbackSample]:
        """
        Build chronological feedback samples.

        For decision candle i, the outcome uses close[i + horizon].
        The last `horizon` candles cannot be used because their future
        outcome is not known yet.
        """
        if df is None or len(df) == 0:
            raise ValueError("Feedback engine received an empty DataFrame.")

        if "close" not in df.columns:
            raise ValueError("Feedback engine requires a close column.")

        point = float(point)
        if point <= 0.0:
            raise ValueError("Symbol point must be greater than zero.")

        horizon = int(horizon)
        if horizon < 1:
            raise ValueError("Outcome horizon must be at least 1 candle.")

        train_fraction = float(train_fraction)
        if not 0.0 < train_fraction < 1.0:
            raise ValueError("Train fraction must be between 0 and 1.")

        if len(df) <= horizon:
            raise ValueError(
                "Not enough candles for the selected outcome horizon."
            )

        min_move_price = float(min_outcome_points) * point
        samples: List[FeedbackSample] = []

        last_decision_index = len(df) - horizon

        for i in range(last_decision_index):
            row = df.iloc[i]
            close = as_float(row.get("close"))
            future_close = as_float(df["close"].iloc[i + horizon])

            if not is_finite(close) or not is_finite(future_close):
                continue

            features = compute_rule_features(row)
            _, valid_rules = score_from_features(features, DEFAULT_WEIGHTS)

            if valid_rules < MIN_VALID_RULES:
                continue

            raw_scores = {
                rule_name: float(features[rule_name]["raw"])
                for rule_name in RULE_NAMES
            }

            price_change = future_close - close
            future_return_points = price_change / point

            if price_change > min_move_price:
                outcome_label = 1
            elif price_change < -min_move_price:
                outcome_label = -1
            else:
                outcome_label = 0

            decision_time = str(row.get("time", f"row_{i}"))

            samples.append(
                FeedbackSample(
                    index=i,
                    decision_time=decision_time,
                    close=float(close),
                    future_close=float(future_close),
                    future_return_points=float(future_return_points),
                    outcome_label=int(outcome_label),
                    split="pending",
                    raw_scores=raw_scores,
                    valid_rules=int(valid_rules),
                )
            )

        if len(samples) < 20:
            raise ValueError(
                "Not enough valid feedback samples. "
                "Load more history or reduce the outcome horizon."
            )

        train_count = int(len(samples) * train_fraction)

        if train_count < 10 or (len(samples) - train_count) < 5:
            raise ValueError(
                "Train/validation split is too small. "
                "Load more history or adjust the train fraction."
            )

        val_start_index = samples[train_count].index

        for index, sample in enumerate(samples):
            if index >= train_count:
                sample.split = "validation"
            elif sample.index + horizon > val_start_index:
                # Purge samples whose future outcome horizon extends into the validation period
                sample.split = "purged"
            else:
                sample.split = "train"

        effective_train = sum(1 for s in samples if s.split == "train")
        effective_val = sum(1 for s in samples if s.split == "validation")

        if effective_train < 10 or effective_val < 5:
            raise ValueError(
                "Train/validation split is too small after purging the embargo gap. "
                "Load more history or adjust the train fraction."
            )

        return samples

    @staticmethod
    def train_weights(
        start_weights: Dict[str, float],
        samples: List[FeedbackSample],
        learning_rate: float,
    ):
        """
        Simple adaptive weighted scoring.

        If a rule vote agrees with the realized outcome direction, its weight
        is increased. If it disagrees, its weight is decreased.

        This is not a calibrated probability model.
        """
        learning_rate = float(learning_rate)
        if learning_rate <= 0.0:
            raise ValueError("Learning rate must be greater than zero.")

        weights = {
            rule_name: float(start_weights.get(rule_name, DEFAULT_WEIGHTS[rule_name]))
            for rule_name in RULE_NAMES
        }

        updates = 0

        for sample in samples:
            if sample.split != "train":
                continue

            if sample.outcome_label == 0:
                continue

            for rule_name in RULE_NAMES:
                raw = float(sample.raw_scores.get(rule_name, 0.0))
                if raw == 0.0:
                    continue

                delta = learning_rate * float(sample.outcome_label) * raw
                weights[rule_name] = clip_weight(weights[rule_name] + delta)
                updates += 1

        return weights, updates

    @staticmethod
    def evaluate_validation(
        samples: List[FeedbackSample],
        weights: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Evaluate a weight set only on the validation slice.
        """
        metrics = {
            "total": 0,
            "signals": 0,
            "long_signals": 0,
            "short_signals": 0,
            "correct": 0,
            "incorrect": 0,
            "neutral_outcomes": 0,
            "avg_signal_return_points": 0.0,
            "accuracy": None,
        }

        returns = []

        for sample in samples:
            if sample.split != "validation":
                continue

            metrics["total"] += 1

            score = 0.0
            for rule_name in RULE_NAMES:
                raw = float(sample.raw_scores.get(rule_name, 0.0))
                weight = float(weights.get(rule_name, 0.0))
                score += raw * weight

            action = action_from_score(score, sample.valid_rules)

            if action == "NO_TRADE":
                continue

            metrics["signals"] += 1

            if action == "LONG_BIAS":
                metrics["long_signals"] += 1
                directional_return = sample.future_return_points
                correct = sample.outcome_label > 0
            else:
                metrics["short_signals"] += 1
                directional_return = -sample.future_return_points
                correct = sample.outcome_label < 0

            returns.append(float(directional_return))

            if sample.outcome_label == 0:
                metrics["neutral_outcomes"] += 1
            elif correct:
                metrics["correct"] += 1
            else:
                metrics["incorrect"] += 1

        if returns:
            metrics["avg_signal_return_points"] = float(sum(returns) / len(returns))

        decided = metrics["correct"] + metrics["incorrect"]
        if decided > 0:
            metrics["accuracy"] = float(metrics["correct"] / decided)

        return metrics

    @staticmethod
    def _format_metrics(metrics: Dict[str, Any]) -> str:
        lines = []

        lines.append(f"  Validation samples: {metrics['total']}")
        lines.append(f"  Signals produced: {metrics['signals']}")

        if metrics["signals"] == 0:
            lines.append("  No signals were produced on the validation slice.")
            return "\n".join(lines)

        lines.append(
            f"  Long signals: {metrics['long_signals']} | "
            f"Short signals: {metrics['short_signals']}"
        )

        if metrics["accuracy"] is None:
            lines.append("  Direction accuracy: N/A (no directional outcomes)")
        else:
            lines.append(
                f"  Direction accuracy: {metrics['accuracy'] * 100.0:.1f}%"
            )

        lines.append(
            f"  Correct: {metrics['correct']} | "
            f"Incorrect: {metrics['incorrect']} | "
            f"Neutral outcomes: {metrics['neutral_outcomes']}"
        )

        lines.append(
            "  Avg signal return (points, before spread/commission/slippage): "
            f"{metrics['avg_signal_return_points']:.2f}"
        )

        return "\n".join(lines)

    @staticmethod
    def format_report(
        meta: Dict[str, Any],
        samples: List[FeedbackSample],
        start_weights: Dict[str, float],
        adapted_weights: Dict[str, float],
        start_metrics: Dict[str, Any],
        adapted_metrics: Dict[str, Any],
        learning_rate: float,
        updates: int,
        horizon: int,
        min_outcome_points: float,
        train_fraction: float,
    ) -> str:
        train_count = sum(1 for sample in samples if sample.split == "train")
        validation_count = sum(
            1 for sample in samples if sample.split == "validation"
        )
        purged_count = sum(1 for sample in samples if sample.split == "purged")

        bullish = sum(1 for sample in samples if sample.outcome_label > 0)
        bearish = sum(1 for sample in samples if sample.outcome_label < 0)
        flat = sum(1 for sample in samples if sample.outcome_label == 0)

        lines = []

        lines.append("NeuroTrade AI Feedback Report")
        lines.append("Version: adaptive-weighted-scoring v1")
        lines.append("")

        lines.append(
            f"Symbol: {meta.get('symbol', 'UNKNOWN')} | "
            f"Timeframe: {meta.get('timeframe', 'UNKNOWN')}"
        )
        lines.append(f"Data source: {meta.get('source', 'UNKNOWN')}")
        lines.append(f"Candles loaded: {meta.get('rows', 0)}")
        lines.append("")

        lines.append("Feedback parameters:")
        lines.append(f"  Outcome horizon: {horizon} candles")
        lines.append(f"  Minimum outcome move: {min_outcome_points:.1f} points")
        lines.append(f"  Learning rate: {learning_rate:.4f}")
        lines.append(f"  Train fraction: {train_fraction * 100.0:.0f}%")
        lines.append("")

        lines.append("Samples:")
        lines.append(f"  Total valid samples: {len(samples)}")
        lines.append(f"  Train samples: {train_count}")
        lines.append(f"  Validation samples: {validation_count}")
        lines.append(f"  Purged embargo samples: {purged_count}")
        lines.append(
            f"  Outcome labels: bullish={bullish}, bearish={bearish}, flat={flat}"
        )
        lines.append("")

        lines.append("Weight updates:")
        lines.append(f"  Rule-weight updates applied: {updates}")
        lines.append("")

        lines.append("Starting weights:")
        lines.append(format_weights(start_weights))
        lines.append("")

        lines.append("Adapted weights:")
        lines.append(format_weights(adapted_weights))
        lines.append("")

        lines.append("Validation with starting weights (out-of-sample):")
        lines.append(FeedbackEngine._format_metrics(start_metrics))
        lines.append("")

        lines.append("Validation with adapted weights (out-of-sample):")
        lines.append(FeedbackEngine._format_metrics(adapted_metrics))
        lines.append("")

        lines.append("Honesty notes:")
        lines.append("  - This is heuristic adaptive scoring, not deep RL.")
        lines.append("  - Confidence is not a calibrated win probability.")
        lines.append("  - Results exclude spread, commission and slippage.")
        lines.append("  - Win rate alone is not sufficient evidence of edge.")
        lines.append("  - No orders are sent by this module.")

        return "\n".join(lines)