"""
Live Web Market Data Provider for NeuroTrade AI.

Zero-dependency, no-account live market feed using Python standard library urllib.
Fetches real multi-timeframe candle data for XAUUSD, EURUSD, GBPUSD, USDJPY, and AUDUSD
from Yahoo Finance's v8 chart API.

Acts as an automatic, transparent fallback whenever MetaTrader 5 is offline or not installed.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.data_store import CandleStore
from core.weight_store import WeightStore

# Web symbol specifications and broker equivalents
WEB_SYMBOL_SPECS: Dict[str, Dict[str, Any]] = {
    "XAUUSD": {
        "ticker": "GC=F",
        "resolved_symbol": "XAUUSD",
        "point": 0.01,
        "digits": 2,
        "default_spread": 20.0,
        "rollover_spread": 45.0,
        "description": "Gold Spot / Futures Proxy (GC=F)",
    },
    "EURUSD": {
        "ticker": "EURUSD=X",
        "resolved_symbol": "EURUSD",
        "point": 0.00001,
        "digits": 5,
        "default_spread": 12.0,
        "rollover_spread": 30.0,
        "description": "EUR/USD Currency Pair",
    },
    "GBPUSD": {
        "ticker": "GBPUSD=X",
        "resolved_symbol": "GBPUSD",
        "point": 0.00001,
        "digits": 5,
        "default_spread": 15.0,
        "rollover_spread": 35.0,
        "description": "GBP/USD Currency Pair",
    },
    "USDJPY": {
        "ticker": "JPY=X",
        "resolved_symbol": "USDJPY",
        "point": 0.001,
        "digits": 3,
        "default_spread": 12.0,
        "rollover_spread": 30.0,
        "description": "USD/JPY Currency Pair",
    },
    "AUDUSD": {
        "ticker": "AUDUSD=X",
        "resolved_symbol": "AUDUSD",
        "point": 0.00001,
        "digits": 5,
        "default_spread": 14.0,
        "rollover_spread": 32.0,
        "description": "AUD/USD Currency Pair",
    },
}

# Supported timeframes and Yahoo interval/range parameters
TIMEFRAME_CONFIG: Dict[str, Dict[str, str]] = {
    "1m": {"interval": "1m", "range": "7d"},
    "5m": {"interval": "5m", "range": "60d"},
    "15m": {"interval": "15m", "range": "60d"},
    "1H": {"interval": "60m", "range": "730d"},
    "60m": {"interval": "60m", "range": "730d"},
    "1h": {"interval": "60m", "range": "730d"},
    "4H": {"interval": "60m", "range": "730d"},  # Fetched as 60m and resampled to 4H
    "4h": {"interval": "60m", "range": "730d"},
    "1D": {"interval": "1d", "range": "2y"},
    "1d": {"interval": "1d", "range": "2y"},
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class WebMarketDataProvider:
    """Zero-dependency live and historical market candle provider via Web HTTP."""

    @classmethod
    def resolve_symbol(cls, symbol: str) -> str:
        """Normalize symbol string to canonical internal symbol (e.g. XAUUSD.a -> XAUUSD)."""
        clean = str(symbol).strip().upper().replace("/", "").replace("_", "")
        # Strip common broker suffixes like .A, .ECN, M, .PRO, etc.
        for base in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
            if clean.startswith(base):
                return base
        if "GOLD" in clean or "XAU" in clean:
            return "XAUUSD"
        if clean in WEB_SYMBOL_SPECS:
            return clean
        # Default fallback
        return "XAUUSD"

    @classmethod
    def get_symbol_spec(cls, symbol: str) -> Dict[str, Any]:
        """Return instrument specifications (point, digits, spreads, ticker)."""
        resolved = cls.resolve_symbol(symbol)
        return dict(WEB_SYMBOL_SPECS.get(resolved, WEB_SYMBOL_SPECS["XAUUSD"]))

    @classmethod
    def fetch_candles(
        cls,
        symbol: str,
        timeframe: str,
        bars: Optional[int] = None,
        timeout: int = 15,
    ) -> pd.DataFrame:
        """Fetch historical or latest candle DataFrame for symbol and timeframe.

        Returns DataFrame matching DataEngine standard:
            ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
        """
        spec = cls.get_symbol_spec(symbol)
        ticker = spec["ticker"]
        digits = spec["digits"]
        default_spread = spec["default_spread"]
        rollover_spread = spec["rollover_spread"]

        tf_norm = timeframe.strip()
        tf_cfg = TIMEFRAME_CONFIG.get(tf_norm)
        if not tf_cfg:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. Supported: {list(TIMEFRAME_CONFIG.keys())}"
            )

        interval = tf_cfg["interval"]
        range_str = tf_cfg["range"]

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={range_str}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"Web market data request failed for {symbol} ({ticker}): {exc}"
            ) from exc

        chart_data = data.get("chart", {})
        error_info = chart_data.get("error")
        if error_info:
            raise RuntimeError(
                f"Yahoo Finance returned API error for {ticker}: {error_info}"
            )

        results = chart_data.get("result")
        if not results or not isinstance(results, list) or len(results) == 0:
            raise RuntimeError(f"No chart data returned by web feed for {ticker}.")

        result = results[0]
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators", {})
        quote_list = indicators.get("quote", [{}])
        quote = quote_list[0] if quote_list else {}

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        num_points = min(len(timestamps), len(opens), len(highs), len(lows), len(closes))
        if num_points == 0:
            raise RuntimeError(f"No valid OHLC price points returned for {ticker}.")

        records: List[Dict[str, Any]] = []
        for i in range(num_points):
            ts = timestamps[i]
            op = opens[i]
            hp = highs[i]
            lp = lows[i]
            cp = closes[i]
            vol = volumes[i] if i < len(volumes) else 0

            # Filter out missing, null, or non-finite records (e.g. weekend quotes)
            if any(val is None or not np.isfinite(val) for val in (ts, op, hp, lp, cp)):
                continue

            dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)

            op = round(float(op), digits)
            hp = round(float(hp), digits)
            lp = round(float(lp), digits)
            cp = round(float(cp), digits)

            # Ensure strict high/low boundaries
            hp = max(hp, op, cp)
            lp = min(lp, op, cp)

            # Realistic session-aware spread
            if 21 <= dt.hour <= 23:
                sp = rollover_spread
            else:
                sp = default_spread

            records.append({
                "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": op,
                "high": hp,
                "low": lp,
                "close": cp,
                "tick_volume": int(vol or 0),
                "spread": float(sp),
            })

        if not records:
            raise RuntimeError(f"No clean candle records remained after validation for {ticker}.")

        df = pd.DataFrame(records)
        df["time"] = pd.to_datetime(df["time"])
        df.sort_values("time", inplace=True)
        df.drop_duplicates(subset=["time"], keep="last", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Handle 4H resampling if requested
        if tf_norm in ("4H", "4h"):
            df.set_index("time", inplace=True)
            resampled = (
                df.resample("4h", label="left", closed="left")
                .agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "tick_volume": "sum",
                    "spread": "median",
                })
                .dropna(subset=["open", "high", "low", "close"])
                .reset_index()
            )
            resampled["high"] = np.maximum(
                resampled["high"], np.maximum(resampled["open"], resampled["close"])
            )
            resampled["low"] = np.minimum(
                resampled["low"], np.minimum(resampled["open"], resampled["close"])
            )
            df = resampled

        # Limit to requested bar count if specified
        if bars is not None and bars > 0 and len(df) > bars:
            df = df.iloc[-bars:].copy().reset_index(drop=True)

        # Standardize 'time' as string representation to match CSVDataLoader & SQLite CandleStore
        df["time"] = df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return df

    @classmethod
    def fetch_mtf_candles(
        cls,
        symbol: str,
        requested_bars: int = 500,
        timeout: int = 15,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch causally aligned 1H, 15m, and 5m market candle DataFrames.

        Guarantees required minimum bars for technical warm-up (EMA-200 on H1).
        """
        # H1 needs at least 250 bars (minimum 220 completed bars for EMA-200)
        h1_bars = max(250, int(requested_bars / 12) + 250)
        # M15 needs at least 150 bars
        m15_bars = max(150, int(requested_bars / 3) + 100)
        # M5 gets requested_bars (or minimum 500 for good intraday resolution)
        m5_bars = max(500, int(requested_bars))

        logging.info(
            f"Fetching Web market data for {symbol}: 1H={h1_bars}, 15m={m15_bars}, 5m={m5_bars} bars..."
        )

        df_h1 = cls.fetch_candles(symbol, "1H", bars=h1_bars, timeout=timeout)
        df_m15 = cls.fetch_candles(symbol, "15m", bars=m15_bars, timeout=timeout)
        df_m5 = cls.fetch_candles(symbol, "5m", bars=m5_bars, timeout=timeout)

        return {
            "1H": df_h1,
            "15m": df_m15,
            "5m": df_m5,
        }

    @classmethod
    def sync_to_sqlite(
        cls,
        symbol: str,
        store: CandleStore,
        weight_store: Optional[WeightStore] = None,
        requested_bars: int = 500,
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch live web market candles and persist directly to CandleStore & WeightStore.

        If timeframe is specified (e.g. '1m', '5m', '15m', '1H'), syncs that single timeframe.
        If timeframe is None, syncs full multi-timeframe suite ('1H', '15m', '5m').
        """
        spec = cls.get_symbol_spec(symbol)
        resolved = spec["resolved_symbol"]
        point = float(spec["point"])
        digits = int(spec["digits"])

        # Cache contract info in WeightStore
        if weight_store is not None:
            weight_store.save_contract(symbol, resolved, point, digits)
            weight_store.save_contract(resolved, resolved, point, digits)

        if timeframe is not None:
            df = cls.fetch_candles(symbol, timeframe, bars=requested_bars)
            written = store.upsert_candles(resolved, timeframe, df)
            return {
                "symbol": resolved,
                "timeframe": timeframe,
                "bars": written,
                "data": df,
                "point": point,
                "digits": digits,
            }

        mtf_data = cls.fetch_mtf_candles(symbol, requested_bars=requested_bars)
        w_h1 = store.upsert_candles(resolved, "1H", mtf_data["1H"])
        w_m15 = store.upsert_candles(resolved, "15m", mtf_data["15m"])
        w_m5 = store.upsert_candles(resolved, "5m", mtf_data["5m"])

        logging.info(
            f"Synced Web market data to SQLite for {resolved}: 1H={w_h1}, 15m={w_m15}, 5m={w_m5} candles."
        )

        return {
            "symbol": resolved,
            "timeframes": {"1H": w_h1, "15m": w_m15, "5m": w_m5},
            "mtf_data": mtf_data,
            "point": point,
            "digits": digits,
        }
