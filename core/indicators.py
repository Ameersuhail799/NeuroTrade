"""
Indicator calculations using pandas/numpy only.

All calculations are causal: each row uses only that row and earlier rows.
No centered windows, no future rows, no forward filling.
Insufficient history produces NaN, never a fabricated value.
"""

import numpy as np
import pandas as pd


class IndicatorEngine:
    REQUIRED_COLUMNS = ("open", "high", "low", "close")

    @staticmethod
    def validate_candles(df: pd.DataFrame) -> None:
        if df is None or len(df) == 0:
            raise ValueError("Candle DataFrame is empty.")

        missing = [
            column
            for column in IndicatorEngine.REQUIRED_COLUMNS
            if column not in df.columns
        ]
        if missing:
            raise ValueError(
                f"Missing required candle columns: {', '.join(missing)}"
            )

    @staticmethod
    def _series(close: pd.Series) -> pd.Series:
        return pd.to_numeric(close, errors="coerce").astype(float)

    @staticmethod
    def sma(close: pd.Series, period: int = 20) -> pd.Series:
        if period < 1:
            raise ValueError("SMA period must be >= 1.")
        return IndicatorEngine._series(close).rolling(
            window=period, min_periods=period
        ).mean()

    @staticmethod
    def ema(close: pd.Series, period: int = 50) -> pd.Series:
        if period < 1:
            raise ValueError("EMA period must be >= 1.")
        return IndicatorEngine._series(close).ewm(
            span=period, min_periods=period, adjust=False
        ).mean()

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Wilder RSI. Undefined/flat cases are handled explicitly."""
        if period < 1:
            raise ValueError("RSI period must be >= 1.")

        series = IndicatorEngine._series(close)
        delta = series.diff()

        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)

        avg_gain = gain.ewm(
            alpha=1.0 / period, min_periods=period, adjust=False
        ).mean()
        avg_loss = loss.ewm(
            alpha=1.0 / period, min_periods=period, adjust=False
        ).mean()

        result = pd.Series(np.nan, index=series.index, dtype=float)

        valid = avg_loss.notna() & (avg_loss > 0.0)
        result.loc[valid] = 100.0 - (
            100.0 / (1.0 + avg_gain.loc[valid] / avg_loss.loc[valid])
        )

        # No losses and positive gains: RSI 100.
        flat_up = (avg_loss == 0.0) & (avg_gain > 0.0) & avg_gain.notna()
        result.loc[flat_up] = 100.0

        # Completely flat: RSI is undefined; use neutral 50 and document it.
        flat = (avg_loss == 0.0) & (avg_gain == 0.0) & avg_gain.notna()
        result.loc[flat] = 50.0

        return result

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Wilder ATR based on true range."""
        if period < 1:
            raise ValueError("ATR period must be >= 1.")
        IndicatorEngine.validate_candles(df)

        high = pd.to_numeric(df["high"], errors="coerce").astype(float)
        low = pd.to_numeric(df["low"], errors="coerce").astype(float)
        close = pd.to_numeric(df["close"], errors="coerce").astype(float)
        prev_close = close.shift(1)

        range_1 = high - low
        range_2 = (high - prev_close).abs()
        range_3 = (low - prev_close).abs()

        true_range = pd.concat(
            [range_1, range_2, range_3], axis=1
        ).max(axis=1)

        # First bar has no previous close: use its high-low range.
        true_range = true_range.fillna(range_1)

        return true_range.ewm(
            alpha=1.0 / period, min_periods=period, adjust=False
        ).mean()

    @staticmethod
    def macd(
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> pd.DataFrame:
        if fast < 1 or slow < 1 or signal < 1:
            raise ValueError("MACD periods must be >= 1.")
        if fast >= slow:
            raise ValueError("MACD fast period must be smaller than slow.")

        series = IndicatorEngine._series(close)
        fast_ema = series.ewm(span=fast, min_periods=fast, adjust=False).mean()
        slow_ema = series.ewm(span=slow, min_periods=slow, adjust=False).mean()

        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(
            span=signal, min_periods=signal, adjust=False
        ).mean()

        return pd.DataFrame(
            {
                "macd": macd_line,
                "macd_signal": signal_line,
                "macd_hist": macd_line - signal_line,
            },
            index=series.index,
        )

    @staticmethod
    def bollinger(
        close: pd.Series,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> pd.DataFrame:
        if period < 2:
            raise ValueError("Bollinger period must be >= 2.")
        if std_dev <= 0:
            raise ValueError("Bollinger standard deviation must be > 0.")

        series = IndicatorEngine._series(close)
        middle = series.rolling(window=period, min_periods=period).mean()
        deviation = series.rolling(window=period, min_periods=period).std(ddof=0)

        return pd.DataFrame(
            {
                "bb_middle": middle,
                "bb_upper": middle + std_dev * deviation,
                "bb_lower": middle - std_dev * deviation,
            },
            index=series.index,
        )

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy enriched with indicator columns."""
        IndicatorEngine.validate_candles(df)
        result = df.copy().reset_index(drop=True)

        close = pd.to_numeric(result["close"], errors="coerce").astype(float)

        result["sma_20"] = IndicatorEngine.sma(close, 20)
        result["ema_50"] = IndicatorEngine.ema(close, 50)
        result["rsi_14"] = IndicatorEngine.rsi(close, 14)
        result["atr_14"] = IndicatorEngine.atr(result, 14)

        macd_frame = IndicatorEngine.macd(close)
        for column in macd_frame.columns:
            result[column] = macd_frame[column]

        bb_frame = IndicatorEngine.bollinger(close)
        for column in bb_frame.columns:
            result[column] = bb_frame[column]

        return result

    @staticmethod
    def format_summary(df: pd.DataFrame) -> str:
        """Human-readable latest-candle indicator readout. No signals."""
        if df is None or len(df) == 0:
            return "No indicator data available."

        last = df.iloc[-1]

        if "time" in df.columns:
            candle_time = str(last["time"])
        else:
            candle_time = "unavailable"

        entries = [
            ("sma_20", "SMA(20)"),
            ("ema_50", "EMA(50)"),
            ("rsi_14", "RSI(14)"),
            ("atr_14", "ATR(14)"),
            ("macd", "MACD(12,26)"),
            ("macd_signal", "MACD signal(9)"),
            ("macd_hist", "MACD histogram"),
            ("bb_middle", "BB middle(20)"),
            ("bb_upper", "BB upper(20,2)"),
            ("bb_lower", "BB lower(20,2)"),
        ]

        lines = [f"Decision candle (MT5 server time): {candle_time}", ""]

        for key, label in entries:
            value = last.get(key, np.nan)
            try:
                is_valid = bool(np.isfinite(float(value)))
            except (TypeError, ValueError):
                is_valid = False

            if is_valid:
                text = f"{float(value):.5f}"
            else:
                text = "N/A (warm-up / insufficient history)"

            lines.append(f"{label:<20} {text}")

        lines.append("")
        lines.append("Indicator values only. Not a trading signal.")
        lines.append("RSI/ATR are unitless/price-unit values, not probabilities.")

        return "\n".join(lines)