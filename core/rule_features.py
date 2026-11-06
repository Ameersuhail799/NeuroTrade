"""
Shared rule feature extraction for feedback and adaptive decision scoring.

These rules mirror the Part 5 rule-based engine, but are implemented in a
batch-friendly way for feedback training and validation.

This is adaptive weighted scoring, not deep reinforcement learning.
"""

import numpy as np


RULE_NAMES = [
    "trend_close_sma20",
    "trend_sma20_ema50",
    "momentum_rsi",
    "macd_direction",
    "bollinger_position",
]

DEFAULT_WEIGHTS = {
    "trend_close_sma20": 20.0,
    "trend_sma20_ema50": 20.0,
    "momentum_rsi": 20.0,
    "macd_direction": 20.0,
    "bollinger_position": 20.0,
}

RULE_DESCRIPTIONS = {
    "trend_close_sma20": "Close vs SMA20",
    "trend_sma20_ema50": "SMA20 vs EMA50",
    "momentum_rsi": "RSI(14) zone",
    "macd_direction": "MACD vs signal",
    "bollinger_position": "Close vs Bollinger bands",
}

LONG_THRESHOLD = 40.0
SHORT_THRESHOLD = -40.0
MIN_VALID_RULES = 4

MIN_WEIGHT = 0.0
MAX_WEIGHT = 100.0


def as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def is_finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def compute_rule_features(row) -> dict:
    """
    Compute raw rule votes for one decision row.

    Raw vote:
    +1 = bullish rule evidence
    -1 = bearish rule evidence
     0 = neutral / blocked / unavailable

    Invalid means the indicator data is not available yet.
    """
    close = as_float(row.get("close"))

    sma20 = as_float(row.get("sma_20"))
    ema50 = as_float(row.get("ema_50"))
    rsi = as_float(row.get("rsi_14"))
    macd = as_float(row.get("macd"))
    macd_signal = as_float(row.get("macd_signal"))
    bb_middle = as_float(row.get("bb_middle"))
    bb_upper = as_float(row.get("bb_upper"))
    bb_lower = as_float(row.get("bb_lower"))

    features = {}

    # Rule 1: Close vs SMA20
    valid = is_finite(close) and is_finite(sma20)
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
        note = "Close/SMA20 not available."
    features["trend_close_sma20"] = {"raw": raw, "valid": valid, "note": note}

    # Rule 2: SMA20 vs EMA50
    valid = is_finite(sma20) and is_finite(ema50)
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
    features["trend_sma20_ema50"] = {"raw": raw, "valid": valid, "note": note}

    # Rule 3: RSI zone
    valid = is_finite(rsi)
    if valid:
        if rsi > 70.0:
            raw = 0.0
            note = "RSI overbought; directional vote blocked."
        elif rsi < 30.0:
            raw = 0.0
            note = "RSI oversold; directional vote blocked."
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
    features["momentum_rsi"] = {"raw": raw, "valid": valid, "note": note}

    # Rule 4: MACD direction
    valid = is_finite(macd) and is_finite(macd_signal)
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
    features["macd_direction"] = {"raw": raw, "valid": valid, "note": note}

    # Rule 5: Bollinger position
    valid = (
        is_finite(close)
        and is_finite(bb_middle)
        and is_finite(bb_upper)
        and is_finite(bb_lower)
        and bb_upper >= bb_lower
    )

    if valid:
        if close > bb_upper:
            raw = 0.0
            note = "Close above upper Bollinger band; vote blocked."
        elif close < bb_lower:
            raw = 0.0
            note = "Close below lower Bollinger band; vote blocked."
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
    features["bollinger_position"] = {"raw": raw, "valid": valid, "note": note}

    return features


def score_from_features(features: dict, weights: dict):
    """
    Return weighted score and count of valid rules.
    """
    score = 0.0
    valid_rules = 0

    for rule_name in RULE_NAMES:
        feature = features.get(rule_name)
        if not feature:
            continue

        if feature.get("valid", False):
            valid_rules += 1
            raw = float(feature.get("raw", 0.0))
            weight = float(weights.get(rule_name, 0.0))
            score += raw * weight

    return score, valid_rules


def action_from_score(score: float, valid_rules: int) -> str:
    if valid_rules < MIN_VALID_RULES:
        return "NO_TRADE"

    if score >= LONG_THRESHOLD:
        return "LONG_BIAS"

    if score <= SHORT_THRESHOLD:
        return "SHORT_BIAS"

    return "NO_TRADE"


def clip_weight(value: float) -> float:
    return float(max(MIN_WEIGHT, min(MAX_WEIGHT, float(value))))


def format_weights(weights: dict) -> str:
    lines = []
    for rule_name in RULE_NAMES:
        weight = float(weights.get(rule_name, 0.0))
        description = RULE_DESCRIPTIONS.get(rule_name, rule_name)
        lines.append(f"  {rule_name:<24} {weight:8.3f}   {description}")
    return "\n".join(lines)