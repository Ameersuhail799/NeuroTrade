"""Market Regime Analysis, Instrument Microstructure Profiles, and Strategy Configuration.

Provides:
- InstrumentProfile registry for multi-instrument trading (XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD)
- IntradayStrategyConfig for modular feature toggling and ablation studies
- MarketRegimeAnalyzer for causal session mapping, Kaufman efficiency, and ATR percentiles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InstrumentProfile:
    """Microstructure and session specifications for an instrument."""

    symbol: str
    default_point: float
    prime_hours_utc: Tuple[Tuple[int, int], ...]
    rollover_hours_utc: Tuple[int, int] = (21, 23)
    m15_rsi_long: Tuple[float, float] = (50.0, 68.0)
    m15_rsi_short: Tuple[float, float] = (32.0, 50.0)
    max_spread_to_risk: float = 0.12
    stop_atr_multiplier: float = 1.5
    max_stop_atr: float = 3.0


INSTRUMENT_PROFILES: Dict[str, InstrumentProfile] = {
    "XAUUSD": InstrumentProfile(
        symbol="XAUUSD",
        default_point=0.01,
        prime_hours_utc=((7, 20),),
        rollover_hours_utc=(21, 23),
        m15_rsi_long=(50.0, 68.0),
        m15_rsi_short=(32.0, 50.0),
        max_spread_to_risk=0.12,
        stop_atr_multiplier=1.5,
        max_stop_atr=3.0,
    ),
    "EURUSD": InstrumentProfile(
        symbol="EURUSD",
        default_point=0.00001,
        prime_hours_utc=((7, 17),),
        rollover_hours_utc=(21, 23),
        m15_rsi_long=(48.0, 65.0),
        m15_rsi_short=(35.0, 52.0),
        max_spread_to_risk=0.10,
        stop_atr_multiplier=1.3,
        max_stop_atr=2.5,
    ),
    "GBPUSD": InstrumentProfile(
        symbol="GBPUSD",
        default_point=0.00001,
        prime_hours_utc=((7, 17),),
        rollover_hours_utc=(21, 23),
        m15_rsi_long=(50.0, 68.0),
        m15_rsi_short=(32.0, 50.0),
        max_spread_to_risk=0.12,
        stop_atr_multiplier=1.6,
        max_stop_atr=3.0,
    ),
    "USDJPY": InstrumentProfile(
        symbol="USDJPY",
        default_point=0.001,
        prime_hours_utc=((0, 4), (12, 17)),
        rollover_hours_utc=(21, 23),
        m15_rsi_long=(52.0, 70.0),
        m15_rsi_short=(30.0, 48.0),
        max_spread_to_risk=0.10,
        stop_atr_multiplier=1.4,
        max_stop_atr=2.8,
    ),
    "AUDUSD": InstrumentProfile(
        symbol="AUDUSD",
        default_point=0.00001,
        prime_hours_utc=((0, 6), (12, 17)),
        rollover_hours_utc=(21, 23),
        m15_rsi_long=(48.0, 65.0),
        m15_rsi_short=(35.0, 52.0),
        max_spread_to_risk=0.15,
        stop_atr_multiplier=1.4,
        max_stop_atr=2.8,
    ),
}

DEFAULT_FALLBACK_PROFILE = InstrumentProfile(
    symbol="DEFAULT",
    default_point=0.00001,
    prime_hours_utc=((7, 17),),
    rollover_hours_utc=(21, 23),
    m15_rsi_long=(50.0, 68.0),
    m15_rsi_short=(32.0, 50.0),
    max_spread_to_risk=0.12,
    stop_atr_multiplier=1.5,
    max_stop_atr=3.0,
)


@dataclass
class IntradayStrategyConfig:
    """Configurable strategy parameters and ablation toggles for IntradaySignalEngine v2."""

    enable_rollover_block: bool = True  # Block 21:00-23:00 UTC spread spike window
    restrict_to_prime_sessions: bool = False  # Enforce symbol prime trading hours
    block_asian_breakouts: bool = False  # Block M5 3-bar breakout triggers in Asian session (keep reclaims)
    enable_spread_filter: bool = True  # Reject setup if spread / risk > max_spread_to_risk
    enable_regime_filter: bool = False  # Enforce ATR percentile and Kaufman ER bounds
    min_atr_percentile: float = 10.0  # Reject bottom 10% compressed dead volume
    max_atr_percentile: float = 96.0  # Reject top 4% extreme volatility spikes
    min_efficiency_ratio: float = 0.20  # Minimum 10-bar efficiency ratio on M15
    min_confluence_score: float = 60.0  # Minimum confluence score required for SETUP


class MarketRegimeAnalyzer:
    """Microstructure, session, and regime calculation utilities."""

    @staticmethod
    def resolve_profile(symbol: str) -> InstrumentProfile:
        """Resolve broker symbol name to matching InstrumentProfile."""
        clean = str(symbol).upper().replace("/", "").replace("_", "")
        # Strip broker suffixes like .A, .ECN, M, .PRO
        base_candidates = ["XAUUSD", "GOLD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        for base in base_candidates:
            if clean.startswith(base):
                mapped = "XAUUSD" if base == "GOLD" else base
                return INSTRUMENT_PROFILES[mapped]

        # Check if symbol contains gold indicator
        if "GOLD" in clean or "XAU" in clean:
            return INSTRUMENT_PROFILES["XAUUSD"]

        return DEFAULT_FALLBACK_PROFILE

    @staticmethod
    def classify_session(ts: Union[pd.Timestamp, datetime, str]) -> str:
        """Map UTC timestamp to standard forex trading session.

        - ASIAN: 00:00 - 07:00 UTC and 23:00 - 24:00 UTC
        - LONDON: 07:00 - 13:00 UTC
        - LONDON_NY_OVERLAP: 13:00 - 17:00 UTC
        - NY_AFTERNOON: 17:00 - 21:00 UTC
        - ROLLOVER: 21:00 - 23:00 UTC
        """
        if not isinstance(ts, (pd.Timestamp, datetime)):
            ts = pd.to_datetime(ts)
        hour = ts.hour

        if 0 <= hour < 7 or hour == 23:
            return "ASIAN"
        elif 7 <= hour < 13:
            return "LONDON"
        elif 13 <= hour < 17:
            return "LONDON_NY_OVERLAP"
        elif 17 <= hour < 21:
            return "NY_AFTERNOON"
        else:
            return "ROLLOVER"

    @staticmethod
    def is_in_rollover(
        ts: Union[pd.Timestamp, datetime, str],
        rollover_hours: Tuple[int, int] = (21, 23),
    ) -> bool:
        """Check whether timestamp falls within daily settlement rollover blackout."""
        if not isinstance(ts, (pd.Timestamp, datetime)):
            ts = pd.to_datetime(ts)
        start_hour, end_hour = rollover_hours
        return start_hour <= ts.hour < end_hour

    @staticmethod
    def is_in_prime_session(
        ts: Union[pd.Timestamp, datetime, str],
        prime_hours_utc: Tuple[Tuple[int, int], ...],
    ) -> bool:
        """Check whether timestamp is within an instrument's prime liquidity hours."""
        if not isinstance(ts, (pd.Timestamp, datetime)):
            ts = pd.to_datetime(ts)
        hour = ts.hour
        return any(start <= hour < end for start, end in prime_hours_utc)

    @staticmethod
    def kaufman_efficiency_ratio(close: pd.Series, period: int = 10) -> pd.Series:
        """Calculate causal Kaufman Efficiency Ratio |close_t - close_{t-n}| / sum(|diff|)."""
        if close is None or len(close) < period:
            return pd.Series(0.5, index=close.index if close is not None else [0])

        direction = (close - close.shift(period)).abs()
        volatility = (close - close.shift(1)).abs().rolling(period).sum()

        er = np.where(volatility > 1e-12, direction / volatility, 0.0)
        return pd.Series(er, index=close.index).fillna(0.0).clip(0.0, 1.0)

    @staticmethod
    def atr_percentile_rank(atr_series: pd.Series, lookback: int = 100) -> float:
        """Compute percentile rank (0.0 to 100.0) of latest ATR value relative to lookback."""
        if atr_series is None or len(atr_series) == 0:
            return 50.0

        valid = atr_series.dropna().tail(lookback)
        if len(valid) == 0:
            return 50.0

        latest = float(valid.iloc[-1])
        percentile = float(np.mean(valid.values <= latest) * 100.0)
        return round(percentile, 1)

    @staticmethod
    def candle_body_ratio(
        open_p: float, high_p: float, low_p: float, close_p: float
    ) -> float:
        """Compute ratio of candle body to full candle range [0.0, 1.0]."""
        body = abs(float(close_p) - float(open_p))
        total_range = max(float(high_p) - float(low_p), 1e-12)
        ratio = min(1.0, max(0.0, body / total_range))
        return round(ratio, 3)
