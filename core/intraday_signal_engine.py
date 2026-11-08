"""Multi-timeframe intraday signal analysis for NeuroTrade AI.

Strategy outline (initial research version):
- H1: establish the higher-timeframe trend using EMA 50 / EMA 200.
- M15: require trend structure and momentum agreement.
- M5: require a closed-candle breakout or EMA20 reclaim as an entry trigger.
- Build an ATR/swing-based hypothetical risk plan for analysis only.

This module does not connect to MT5, send orders, or claim profitability.
All inputs are expected to be chronological MT5 candle frames. By default,
the final row of each frame is excluded because MT5 position 0 is generally
the still-forming candle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.indicators import IndicatorEngine
from core.market_regimes import (
    InstrumentProfile,
    IntradayStrategyConfig,
    MarketRegimeAnalyzer,
)


@dataclass
class IntradaySignal:
    """A transparent signal candidate. Prices are references, not fills."""

    version: str
    symbol: str
    action: str
    direction: str
    status: str
    market_regime: str
    decision_time: str
    trend_timeframe: str
    setup_timeframe: str
    trigger_timeframe: str
    confluence_score: float
    entry_reference: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_distance: Optional[float] = None
    reward_risk_1: Optional[float] = None
    reward_risk_2: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IntradaySignalEngine:
    """Generate conservative H1/M15/M5 intraday setup candidates.

    This is a deterministic, rule-based research baseline, not an ML model.
    A LONG_SETUP or SHORT_SETUP means the filters aligned on closed candles;
    it does not guarantee that an order should be placed or filled.
    """

    VERSION = "intraday-mtf-v2"
    TREND_TIMEFRAME = "1H"
    SETUP_TIMEFRAME = "15m"
    TRIGGER_TIMEFRAME = "5m"

    MIN_H1_BARS = 220
    MIN_M15_BARS = 60
    MIN_M5_BARS = 60

    H1_EMA_FAST = 50
    H1_EMA_SLOW = 200
    M15_EMA_FAST = 20
    M15_EMA_SLOW = 50
    M5_EMA_FAST = 20
    M5_EMA_SLOW = 50

    STOP_ATR_MULTIPLIER = 1.5
    SWING_LOOKBACK = 5
    STOP_BUFFER_ATR = 0.15
    MAX_STOP_ATR = 3.0
    TARGET_R_MULTIPLES = (1.5, 2.0)
    MAX_ENTRY_EXTENSION_ATR = 1.5

    def __init__(self, config: Optional[IntradayStrategyConfig] = None):
        self.config = config or IntradayStrategyConfig()

    def generate_signal(
        self,
        h1: pd.DataFrame,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        symbol: str = "XAUUSD",
        digits: Optional[int] = None,
        exclude_latest: bool = True,
        point: Optional[float] = None,
    ) -> IntradaySignal:
        """Evaluate aligned H1/M15/M5 candles and return a signal candidate.

        Args:
            h1, m15, m5: Candle DataFrames with open/high/low/close and
                preferably a `time` column, ordered oldest to newest.
            symbol: Broker-resolved symbol label for reporting.
            digits: Broker symbol precision. If omitted, output prices are
                rounded to 5 decimal places; pass MT5 symbol_info.digits when
                available.
            exclude_latest: Exclude the last candle from every timeframe.
                Keep True for MT5 data that includes the current forming bar.
            point: Broker point size. If omitted, looked up from instrument profile.
        """
        profile = MarketRegimeAnalyzer.resolve_profile(symbol)
        effective_point = (
            float(point)
            if (point is not None and float(point) > 0)
            else profile.default_point
        )

        h1_closed = self._prepare_frame(
            h1, "H1", self.MIN_H1_BARS, exclude_latest
        )
        m15_closed = self._prepare_frame(
            m15, "M15", self.MIN_M15_BARS, exclude_latest
        )
        m5_closed = self._prepare_frame(
            m5, "M5", self.MIN_M5_BARS, exclude_latest
        )
        timeframe_alignment_warning = self._validate_timeframe_order(
            h1_closed, m15_closed, m5_closed
        )

        h1_ind = self._add_moving_averages(h1_closed, include_slow=True)
        m15_ind = self._add_setup_indicators(m15_closed)
        m5_ind = self._add_setup_indicators(m5_closed)

        h1_last = h1_ind.iloc[-1]
        m15_last = m15_ind.iloc[-1]
        m5_last = m5_ind.iloc[-1]

        decision_time = self._format_time(m5_last.get("time", "unavailable"))
        decision_ts = (
            pd.Timestamp(m5_last.get("time"))
            if ("time" in m5_last and pd.notna(m5_last.get("time")))
            else None
        )
        session_name = (
            MarketRegimeAnalyzer.classify_session(decision_ts)
            if decision_ts is not None
            else "UNKNOWN"
        )
        in_rollover = (
            MarketRegimeAnalyzer.is_in_rollover(decision_ts, profile.rollover_hours_utc)
            if decision_ts is not None
            else False
        )
        in_prime = (
            MarketRegimeAnalyzer.is_in_prime_session(decision_ts, profile.prime_hours_utc)
            if decision_ts is not None
            else True
        )

        regime, trend_direction, trend_reasons = self._classify_h1_trend(h1_ind)
        setup_direction, setup_reasons, setup_conflicts = self._classify_m15_setup(
            m15_ind, profile=profile
        )
        trigger_direction, trigger_reasons, trigger_conflicts = self._classify_m5_trigger(
            m5_ind,
            m15_last,
            session_name=session_name,
            block_asian_breakouts=self.config.block_asian_breakouts,
        )

        # Microstructure & regime diagnostics
        m15_er_series = MarketRegimeAnalyzer.kaufman_efficiency_ratio(
            m15_closed["close"], period=10
        )
        m15_er = (
            float(m15_er_series.iloc[-1])
            if (len(m15_er_series) > 0 and pd.notna(m15_er_series.iloc[-1]))
            else 0.5
        )
        m15_atr_pct = MarketRegimeAnalyzer.atr_percentile_rank(
            m15_ind["atr_14"], lookback=100
        )
        m5_body_ratio = MarketRegimeAnalyzer.candle_body_ratio(
            self._safe_float(m5_last.get("open")),
            self._safe_float(m5_last.get("high")),
            self._safe_float(m5_last.get("low")),
            self._safe_float(m5_last.get("close")),
        )

        reasons = trend_reasons + setup_reasons + trigger_reasons
        conflicts = setup_conflicts + trigger_conflicts

        session_conflicts: List[str] = []
        if self.config.enable_rollover_block and in_rollover:
            session_conflicts.append(
                "Setup blocked: timestamp falls inside the daily rollover spread blackout (21:00-23:00 UTC)."
            )
        if self.config.restrict_to_prime_sessions and not in_prime:
            session_conflicts.append(
                f"Setup blocked: timestamp ({decision_ts.strftime('%H:%M') if decision_ts else 'N/A'} UTC) is outside prime liquidity hours for {profile.symbol}."
            )

        regime_conflicts: List[str] = []
        if self.config.enable_regime_filter:
            if m15_atr_pct < self.config.min_atr_percentile:
                regime_conflicts.append(
                    f"Market regime filter: M15 ATR percentile ({m15_atr_pct:.1f}%) is below minimum threshold ({self.config.min_atr_percentile:.1f}%). Market is dead/compressed."
                )
            if m15_atr_pct > self.config.max_atr_percentile:
                regime_conflicts.append(
                    f"Market regime filter: M15 ATR percentile ({m15_atr_pct:.1f}%) exceeds maximum threshold ({self.config.max_atr_percentile:.1f}%). Extreme volatility spike."
                )
            if m15_er < self.config.min_efficiency_ratio:
                regime_conflicts.append(
                    f"Market regime filter: M15 efficiency ratio ({m15_er:.2f}) is below minimum threshold ({self.config.min_efficiency_ratio:.2f}). Market is choppy whipsaw."
                )

        warnings = [
            "Analysis uses completed candles only; the latest row was excluded "
            "from each timeframe." if exclude_latest else
            "Latest candles were included. They may still be forming and can repaint.",
            "Entry is a candle-close reference, not an executable fill. "
            "Spread, commission, slippage and broker constraints are not modeled.",
            "Confluence score is a rule-alignment score, not a win probability.",
            "Research signal only. This module never sends orders.",
        ]
        if timeframe_alignment_warning:
            warnings.append(timeframe_alignment_warning)

        raw_aligned = (
            trend_direction in ("LONG", "SHORT")
            and setup_direction == trend_direction
            and trigger_direction == trend_direction
        )

        spread_to_risk = 0.0
        confluence_breakdown: Dict[str, Any] = {}

        if raw_aligned and not session_conflicts and not regime_conflicts:
            direction = trend_direction
            entry, stop, tp1, tp2, risk = self._build_risk_plan(
                direction=direction,
                m5=m5_ind,
                m15_last=m15_last,
                digits=digits,
                stop_atr_multiplier=profile.stop_atr_multiplier,
                max_stop_atr=profile.max_stop_atr,
            )

            if risk is None:
                action = "NO_TRADE"
                direction = "NONE"
                status = "NO_TRADE"
                confluence_score = 0.0
                warnings.append(
                    "Risk plan rejected: stop distance was invalid or exceeded "
                    f"{profile.max_stop_atr:.1f} x M15 ATR."
                )
                entry = stop = tp1 = tp2 = risk = None
            else:
                # Spread filter
                bar_spread = self._safe_float(m5_last.get("spread", 0.0))
                spread_price = max(0.0, bar_spread) * effective_point
                spread_to_risk = spread_price / risk if risk > 0 else 0.0

                if (
                    self.config.enable_spread_filter
                    and spread_price > 0
                    and spread_to_risk > profile.max_spread_to_risk
                ):
                    conflicts.append(
                        f"Spread-to-risk ratio ({spread_to_risk:.3f}) exceeds maximum allowed ({profile.max_spread_to_risk:.3f})."
                    )
                    action = "NO_TRADE"
                    direction = "NONE"
                    status = "NO_TRADE"
                    confluence_score = 0.0
                    entry = stop = tp1 = tp2 = risk = None
                else:
                    # Graded confluence score
                    confluence_score, confluence_breakdown = self._calculate_confluence_score(
                        direction=direction,
                        h1_ind=h1_ind,
                        h1_last=h1_last,
                        m15_ind=m15_ind,
                        m15_last=m15_last,
                        m5_last=m5_last,
                        profile=profile,
                        session_name=session_name,
                        m5_body_ratio=m5_body_ratio,
                        spread_to_risk=spread_to_risk,
                    )

                    if confluence_score < self.config.min_confluence_score:
                        conflicts.append(
                            f"Confluence score ({confluence_score:.1f}) is below minimum threshold ({self.config.min_confluence_score:.1f})."
                        )
                        action = "NO_TRADE"
                        direction = "NONE"
                        status = "NO_TRADE"
                        entry = stop = tp1 = tp2 = risk = None
                    else:
                        action = f"{direction}_SETUP"
                        status = "SETUP"
        else:
            action = "NO_TRADE"
            direction = "NONE"
            status = "NO_TRADE"
            entry = stop = tp1 = tp2 = risk = None
            confluence_score = (
                self._partial_score(trend_direction, setup_direction, trigger_direction)
                if not (session_conflicts or regime_conflicts)
                else 0.0
            )

            conflicts.extend(session_conflicts)
            conflicts.extend(regime_conflicts)

            if trend_direction == "NONE":
                conflicts.append("H1 trend is mixed or not sufficiently established.")
            if setup_direction != trend_direction or trend_direction == "NONE":
                conflicts.append(
                    "M15 setup does not align with the H1 directional filter."
                )
            if trigger_direction != trend_direction or trend_direction == "NONE":
                conflicts.append(
                    "M5 entry trigger does not align with the H1 directional filter."
                )

        inputs = {
            "h1": {
                "close": self._safe_float(h1_last.get("close")),
                "ema_50": self._safe_float(h1_last.get("ema_50")),
                "ema_200": self._safe_float(h1_last.get("ema_200")),
                "ema_50_slope_5": self._safe_float(
                    h1_ind["ema_50"].iloc[-1] - h1_ind["ema_50"].iloc[-6]
                ),
            },
            "m15": {
                "close": self._safe_float(m15_last.get("close")),
                "ema_20": self._safe_float(m15_last.get("ema_20")),
                "ema_50": self._safe_float(m15_last.get("ema_50")),
                "rsi_14": self._safe_float(m15_last.get("rsi_14")),
                "macd_hist": self._safe_float(m15_last.get("macd_hist")),
                "atr_14": self._safe_float(m15_last.get("atr_14")),
            },
            "m5": {
                "open": self._safe_float(m5_last.get("open")),
                "high": self._safe_float(m5_last.get("high")),
                "low": self._safe_float(m5_last.get("low")),
                "close": self._safe_float(m5_last.get("close")),
                "ema_20": self._safe_float(m5_last.get("ema_20")),
                "ema_50": self._safe_float(m5_last.get("ema_50")),
                "rsi_14": self._safe_float(m5_last.get("rsi_14")),
                "macd_hist": self._safe_float(m5_last.get("macd_hist")),
                "atr_14": self._safe_float(m5_last.get("atr_14")),
            },
            "regime_and_microstructure": {
                "session": session_name,
                "m15_efficiency_ratio": round(m15_er, 3),
                "m15_atr_percentile": round(m15_atr_pct, 1),
                "m5_body_ratio": m5_body_ratio,
                "spread_to_risk_ratio": round(spread_to_risk, 4),
                "confluence_breakdown": confluence_breakdown,
                "profile_symbol": profile.symbol,
            },
        }

        rr1 = self.TARGET_R_MULTIPLES[0] if risk is not None else None
        rr2 = self.TARGET_R_MULTIPLES[1] if risk is not None else None

        return IntradaySignal(
            version=self.VERSION,
            symbol=str(symbol),
            action=action,
            direction=direction,
            status=status,
            market_regime=regime,
            decision_time=decision_time,
            trend_timeframe=self.TREND_TIMEFRAME,
            setup_timeframe=self.SETUP_TIMEFRAME,
            trigger_timeframe=self.TRIGGER_TIMEFRAME,
            confluence_score=round(float(confluence_score), 1),
            entry_reference=self._round_price(entry, digits),
            stop_loss=self._round_price(stop, digits),
            take_profit_1=self._round_price(tp1, digits),
            take_profit_2=self._round_price(tp2, digits),
            risk_distance=self._round_price(risk, digits),
            reward_risk_1=rr1,
            reward_risk_2=rr2,
            reasons=reasons,
            conflicts=conflicts,
            warnings=warnings,
            inputs=inputs,
        )

    @staticmethod
    def _validate_timeframe_order(
        h1: pd.DataFrame,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
    ) -> Optional[str]:
        """Reject reversed/future timeframe ordering and warn on stale higher-timeframe data."""
        frames = (h1, m15, m5)
        if not all("time" in frame.columns for frame in frames):
            return (
                "Cross-timeframe timestamp ordering could not be verified "
                "because one or more frames has no time column."
            )

        h1_time = pd.Timestamp(h1.iloc[-1]["time"])
        m15_time = pd.Timestamp(m15.iloc[-1]["time"])
        m5_time = pd.Timestamp(m5.iloc[-1]["time"])
        if not (h1_time <= m15_time <= m5_time):
            raise ValueError(
                "Timeframe data is not aligned: expected the latest closed "
                "H1 candle <= M15 candle <= M5 candle. Sync all three timeframes."
            )

        # Causal bar completion check:
        # 'time' is the open timestamp of the bar.
        # A closed bar covers [open_time, open_time + bar_duration].
        h1_close = h1_time + pd.Timedelta(hours=1)
        m15_close = m15_time + pd.Timedelta(minutes=15)
        m5_close = m5_time + pd.Timedelta(minutes=5)

        if h1_close > m15_close:
            raise ValueError(
                f"Timeframe data is not aligned: H1 candle close ({h1_close}) is after "
                f"M15 candle close ({m15_close}). Look-ahead bias detected."
            )

        if h1_close > m5_close:
            raise ValueError(
                f"Timeframe data is not aligned: H1 candle close ({h1_close}) is after "
                f"M5 candle close ({m5_close}). Look-ahead bias detected."
            )

        if m15_close > m5_close:
            raise ValueError(
                f"Timeframe data is not aligned: M15 candle close ({m15_close}) is after "
                f"M5 candle close ({m5_close}). Look-ahead bias detected."
            )

        staleness_warnings: List[str] = []
        if m5_close - h1_close > pd.Timedelta(hours=2):
            staleness_warnings.append(
                f"Higher-timeframe H1 data appears stale (lag: {m5_close - h1_close}). "
                "Re-sync H1 history."
            )
        if m5_close - m15_close > pd.Timedelta(minutes=45):
            staleness_warnings.append(
                f"Higher-timeframe M15 data appears stale (lag: {m5_close - m15_close}). "
                "Re-sync M15 history."
            )

        if staleness_warnings:
            return " ".join(staleness_warnings)

        return None

    @staticmethod
    def _prepare_frame(
        frame: pd.DataFrame,
        label: str,
        minimum_bars: int,
        exclude_latest: bool,
    ) -> pd.DataFrame:
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError(f"{label} candle data is empty.")

        required = ["open", "high", "low", "close"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(
                f"{label} candles are missing required columns: {', '.join(missing)}"
            )

        work = frame.copy().reset_index(drop=True)
        if exclude_latest:
            if len(work) <= 1:
                raise ValueError(f"{label} has no completed candle after exclusion.")
            work = work.iloc[:-1].copy().reset_index(drop=True)

        if len(work) < minimum_bars:
            raise ValueError(
                f"{label} needs at least {minimum_bars} completed candles; "
                f"received {len(work)}. Increase the requested history bars."
            )

        for column in required:
            work[column] = pd.to_numeric(work[column], errors="coerce")

        numeric = work[required].to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError(f"{label} candles contain missing or non-finite prices.")

        invalid_range = (
            (work["high"] < work[["open", "close"]].max(axis=1))
            | (work["low"] > work[["open", "close"]].min(axis=1))
            | (work["high"] < work["low"])
        )
        if invalid_range.any():
            raise ValueError(f"{label} candles contain invalid OHLC ranges.")

        if "time" in work.columns:
            timestamps = pd.to_datetime(work["time"], errors="coerce")
            if timestamps.isna().any():
                raise ValueError(f"{label} candles contain invalid timestamps.")
            if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
                raise ValueError(
                    f"{label} timestamps must be unique and oldest-to-newest."
                )
            work["time"] = timestamps

        return work

    @staticmethod
    def _add_moving_averages(
        frame: pd.DataFrame,
        include_slow: bool,
    ) -> pd.DataFrame:
        result = frame.copy()
        close = pd.to_numeric(result["close"], errors="coerce").astype(float)
        result["ema_20"] = IndicatorEngine.ema(close, 20)
        result["ema_50"] = IndicatorEngine.ema(close, 50)
        if include_slow:
            result["ema_200"] = IndicatorEngine.ema(close, 200)
        return result

    @classmethod
    def _add_setup_indicators(cls, frame: pd.DataFrame) -> pd.DataFrame:
        result = cls._add_moving_averages(frame, include_slow=False)
        close = result["close"].astype(float)
        result["rsi_14"] = IndicatorEngine.rsi(close, 14)
        result["atr_14"] = IndicatorEngine.atr(result, 14)
        macd = IndicatorEngine.macd(close)
        result["macd"] = macd["macd"]
        result["macd_signal"] = macd["macd_signal"]
        result["macd_hist"] = macd["macd_hist"]
        return result

    @classmethod
    def _classify_h1_trend(
        cls,
        frame: pd.DataFrame,
    ) -> Tuple[str, str, List[str]]:
        last = frame.iloc[-1]
        ema_fast = cls._safe_float(last.get("ema_50"))
        ema_slow = cls._safe_float(last.get("ema_200"))
        close = cls._safe_float(last.get("close"))
        slope = cls._safe_float(frame["ema_50"].iloc[-1] - frame["ema_50"].iloc[-6])

        if not all(np.isfinite(value) for value in (ema_fast, ema_slow, close, slope)):
            return "MIXED", "NONE", ["H1 trend indicators are not fully warmed up."]

        if close > ema_fast > ema_slow and slope > 0:
            return "UPTREND", "LONG", [
                "H1 bullish trend: close > EMA50 > EMA200 and EMA50 is rising."
            ]
        if close < ema_fast < ema_slow and slope < 0:
            return "DOWNTREND", "SHORT", [
                "H1 bearish trend: close < EMA50 < EMA200 and EMA50 is falling."
            ]

        return "MIXED", "NONE", [
            "H1 moving averages do not establish a clean directional trend."
        ]

    @classmethod
    def _classify_m15_setup(
        cls,
        frame: pd.DataFrame,
        profile: Optional[InstrumentProfile] = None,
    ) -> Tuple[str, List[str], List[str]]:
        last = frame.iloc[-1]
        close = cls._safe_float(last.get("close"))
        ema20 = cls._safe_float(last.get("ema_20"))
        ema50 = cls._safe_float(last.get("ema_50"))
        rsi = cls._safe_float(last.get("rsi_14"))
        macd_hist = cls._safe_float(last.get("macd_hist"))

        values = (close, ema20, ema50, rsi, macd_hist)
        if not all(np.isfinite(value) for value in values):
            return "NONE", [], ["M15 setup indicators are not fully warmed up."]

        rsi_long_min, rsi_long_max = profile.m15_rsi_long if profile else (50.0, 68.0)
        rsi_short_min, rsi_short_max = profile.m15_rsi_short if profile else (32.0, 50.0)

        if close > ema20 > ema50 and rsi_long_min < rsi < rsi_long_max and macd_hist > 0:
            return "LONG", [
                "M15 bullish setup: price > EMA20 > EMA50.",
                f"M15 RSI is constructive at {rsi:.1f} and MACD histogram is positive.",
            ], []

        if close < ema20 < ema50 and rsi_short_min < rsi < rsi_short_max and macd_hist < 0:
            return "SHORT", [
                "M15 bearish setup: price < EMA20 < EMA50.",
                f"M15 RSI is constructive for a short at {rsi:.1f} and MACD histogram is negative.",
            ], []

        conflicts = [
            "M15 trend structure, RSI range and MACD momentum are not aligned."
        ]
        if rsi >= rsi_long_max:
            conflicts.append("M15 RSI is extended above the long-entry filter.")
        elif rsi <= rsi_short_min:
            conflicts.append("M15 RSI is extended below the short-entry filter.")
        return "NONE", [], conflicts

    @classmethod
    def _classify_m5_trigger(
        cls,
        frame: pd.DataFrame,
        m15_last: pd.Series,
        session_name: str = "",
        block_asian_breakouts: bool = False,
    ) -> Tuple[str, List[str], List[str]]:
        if len(frame) < 4:
            return "NONE", [], ["M5 history is too short for the trigger lookback."]

        last = frame.iloc[-1]
        previous = frame.iloc[-2]
        prior_three = frame.iloc[-4:-1]

        close = cls._safe_float(last.get("close"))
        open_price = cls._safe_float(last.get("open"))
        ema20 = cls._safe_float(last.get("ema_20"))
        ema50 = cls._safe_float(last.get("ema_50"))
        rsi = cls._safe_float(last.get("rsi_14"))
        macd_hist = cls._safe_float(last.get("macd_hist"))
        atr5 = cls._safe_float(last.get("atr_14"))
        atr15 = cls._safe_float(m15_last.get("atr_14"))

        values = (close, open_price, ema20, ema50, rsi, macd_hist, atr5, atr15)
        if not all(np.isfinite(value) for value in values) or atr5 <= 0 or atr15 <= 0:
            return "NONE", [], ["M5 trigger indicators or ATR are unavailable."]

        prior_high = float(prior_three["high"].max())
        prior_low = float(prior_three["low"].min())
        previous_close = cls._safe_float(previous.get("close"))
        previous_ema20 = cls._safe_float(previous.get("ema_20"))

        bullish_candle = close > open_price
        bearish_candle = close < open_price

        allow_breakout = not (block_asian_breakouts and session_name == "ASIAN")

        long_breakout = allow_breakout and bullish_candle and close > prior_high
        long_reclaim = (
            bullish_candle
            and np.isfinite(previous_close)
            and np.isfinite(previous_ema20)
            and previous_close <= previous_ema20
            and close > ema20
        )
        short_breakdown = allow_breakout and bearish_candle and close < prior_low
        short_reject = (
            bearish_candle
            and np.isfinite(previous_close)
            and np.isfinite(previous_ema20)
            and previous_close >= previous_ema20
            and close < ema20
        )

        extension = abs(close - ema20) / atr5
        if extension > cls.MAX_ENTRY_EXTENSION_ATR:
            return "NONE", [], [
                f"M5 trigger is overextended ({extension:.2f} x M5 ATR from EMA20)."
            ]

        if (
            close > ema20 > ema50
            and 50.0 < rsi < 75.0
            and macd_hist > 0
            and (long_breakout or long_reclaim)
        ):
            trigger_name = "breakout" if long_breakout else "EMA20 reclaim"
            return "LONG", [
                f"M5 bullish confirmation: {trigger_name} on a completed candle.",
                "M5 price, RSI and MACD momentum support the long direction.",
            ], []

        if (
            close < ema20 < ema50
            and 25.0 < rsi < 50.0
            and macd_hist < 0
            and (short_breakdown or short_reject)
        ):
            trigger_name = "breakdown" if short_breakdown else "EMA20 rejection"
            return "SHORT", [
                f"M5 bearish confirmation: {trigger_name} on a completed candle.",
                "M5 price, RSI and MACD momentum support the short direction.",
            ], []

        return "NONE", [], [
            "No qualifying M5 breakout or EMA20 pullback trigger was found."
        ]

    @classmethod
    def _build_risk_plan(
        cls,
        direction: str,
        m5: pd.DataFrame,
        m15_last: pd.Series,
        digits: Optional[int],
        stop_atr_multiplier: float = 1.5,
        max_stop_atr: float = 3.0,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
        entry = float(m5.iloc[-1]["close"])
        atr15 = cls._safe_float(m15_last.get("atr_14"))
        if not np.isfinite(atr15) or atr15 <= 0:
            return None, None, None, None, None

        swing = m5.iloc[-cls.SWING_LOOKBACK:]
        buffer = atr15 * cls.STOP_BUFFER_ATR

        if direction == "LONG":
            swing_stop = float(swing["low"].min()) - buffer
            atr_stop = entry - atr15 * stop_atr_multiplier
            stop = min(swing_stop, atr_stop)
            risk = entry - stop
            if risk <= 0 or risk > atr15 * max_stop_atr:
                return None, None, None, None, None
            tp1 = entry + risk * cls.TARGET_R_MULTIPLES[0]
            tp2 = entry + risk * cls.TARGET_R_MULTIPLES[1]
        elif direction == "SHORT":
            swing_stop = float(swing["high"].max()) + buffer
            atr_stop = entry + atr15 * stop_atr_multiplier
            stop = max(swing_stop, atr_stop)
            risk = stop - entry
            if risk <= 0 or risk > atr15 * max_stop_atr:
                return None, None, None, None, None
            tp1 = entry - risk * cls.TARGET_R_MULTIPLES[0]
            tp2 = entry - risk * cls.TARGET_R_MULTIPLES[1]
        else:
            return None, None, None, None, None

        return entry, stop, tp1, tp2, risk

    def _calculate_confluence_score(
        self,
        direction: str,
        h1_ind: pd.DataFrame,
        h1_last: pd.Series,
        m15_ind: pd.DataFrame,
        m15_last: pd.Series,
        m5_last: pd.Series,
        profile: InstrumentProfile,
        session_name: str,
        m5_body_ratio: float,
        spread_to_risk: float,
    ) -> Tuple[float, Dict[str, float]]:
        """Compute graded confluence score (60.0 to 100.0) based on multi-timeframe alignment."""
        # 1. H1 Trend Strength (up to 30 pts)
        base_h1 = 20.0
        ema_diff = abs(float(h1_last.get("ema_50", 0.0)) - float(h1_last.get("ema_200", 0.0)))
        h1_atr = (
            float(h1_ind["atr_14"].iloc[-1])
            if ("atr_14" in h1_ind.columns and pd.notna(h1_ind["atr_14"].iloc[-1]) and float(h1_ind["atr_14"].iloc[-1]) > 0)
            else float((h1_ind["high"] - h1_ind["low"]).tail(14).mean())
        )
        h1_atr = max(1e-6, h1_atr)
        sep_score = min(5.0, (ema_diff / (h1_atr * 2.0)) * 5.0)
        slope_5 = abs(float(h1_ind["ema_50"].iloc[-1] - h1_ind["ema_50"].iloc[-6])) if len(h1_ind) >= 6 else 0.0
        slope_score = min(5.0, (slope_5 / (h1_atr * 0.5)) * 5.0)
        h1_score = round(base_h1 + sep_score + slope_score, 1)

        # 2. M15 Setup Quality (up to 30 pts)
        base_m15 = 20.0
        rsi_val = float(m15_last.get("rsi_14", 50.0))
        if direction == "LONG":
            sweet_rsi = (profile.m15_rsi_long[0] + profile.m15_rsi_long[1]) / 2.0
            half_span = max(1.0, (profile.m15_rsi_long[1] - profile.m15_rsi_long[0]) / 2.0)
            rsi_bonus = max(0.0, 5.0 * (1.0 - abs(rsi_val - sweet_rsi) / half_span))
        else:
            sweet_rsi = (profile.m15_rsi_short[0] + profile.m15_rsi_short[1]) / 2.0
            half_span = max(1.0, (profile.m15_rsi_short[1] - profile.m15_rsi_short[0]) / 2.0)
            rsi_bonus = max(0.0, 5.0 * (1.0 - abs(rsi_val - sweet_rsi) / half_span))
        macd_cur = abs(float(m15_last.get("macd_hist", 0.0)))
        macd_prev = abs(float(m15_ind["macd_hist"].iloc[-2])) if len(m15_ind) > 1 else 0.0
        macd_bonus = 5.0 if macd_cur >= macd_prev else 2.5
        m15_score = round(base_m15 + rsi_bonus + macd_bonus, 1)

        # 3. M5 Trigger Conviction (up to 25 pts)
        base_m5 = 15.0
        body_bonus = min(5.0, m5_body_ratio * 5.0)
        m5_range = max(1e-12, float(m5_last.get("high", 0.0)) - float(m5_last.get("low", 0.0)))
        if direction == "LONG":
            extreme_dist = (float(m5_last.get("close", 0.0)) - float(m5_last.get("low", 0.0))) / m5_range
        else:
            extreme_dist = (float(m5_last.get("high", 0.0)) - float(m5_last.get("close", 0.0))) / m5_range
        extreme_bonus = min(5.0, max(0.0, (extreme_dist - 0.5) * 10.0))
        m5_score = round(base_m5 + body_bonus + extreme_bonus, 1)

        # 4. Session & Spread Quality (up to 15 pts)
        if session_name == "LONDON_NY_OVERLAP":
            session_base = 15.0
        elif session_name in ("LONDON", "NY_AFTERNOON"):
            session_base = 12.0
        elif session_name == "ASIAN":
            session_base = 8.0
        else:
            session_base = 4.0

        if spread_to_risk > 0:
            spread_penalty = min(4.0, (spread_to_risk / profile.max_spread_to_risk) * 4.0)
        else:
            spread_penalty = 0.0
        session_score = round(max(0.0, min(15.0, session_base - spread_penalty)), 1)

        raw_sum = h1_score + m15_score + m5_score + session_score
        total_score = round(max(self.config.min_confluence_score, min(100.0, raw_sum)), 1)
        breakdown = {
            "h1_score": h1_score,
            "m15_score": m15_score,
            "m5_score": m5_score,
            "session_score": session_score,
            "total": total_score,
        }
        return total_score, breakdown

    @staticmethod
    def _partial_score(trend: str, setup: str, trigger: str) -> float:
        score = 0.0
        if trend in ("LONG", "SHORT"):
            score += 35.0
        if setup == trend and trend != "NONE":
            score += 35.0
        if trigger == trend and trend != "NONE":
            score += 30.0
        return score

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    @staticmethod
    def _format_time(value: Any) -> str:
        if value is None:
            return "unavailable"
        try:
            return pd.Timestamp(value).isoformat(sep=" ")
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _round_price(value: Optional[float], digits: Optional[int]) -> Optional[float]:
        if value is None:
            return None
        precision = 5 if digits is None else max(0, int(digits))
        return round(float(value), precision)
