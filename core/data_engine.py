"""
MT5 data access for Part 4.

Requires an already initialized MT5 connection.
The GUI worker owns connection lifecycle so the GUI thread never calls MT5.
No orders, no signals, no indicator-based decisions.
"""

from datetime import datetime
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from core.mt5_connector import MT5Connector
from config import DEFAULT_SYMBOL


TIMEFRAME_MAP = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "1H": mt5.TIMEFRAME_H1,
    "4H": mt5.TIMEFRAME_H4,
    "1D": mt5.TIMEFRAME_D1,
}


class DataEngine:
    def __init__(self, symbol: str = DEFAULT_SYMBOL, timeframe: str = "1m", store=None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.store = store
        self.resolved_symbol: Optional[str] = None
        self.digits: int = 2

    def _require_connection(self) -> None:
        if mt5.account_info() is None:
            raise RuntimeError(
                "MT5 is not initialized. Start MT5 and log into a DEMO account."
            )

    def _resolve(self) -> str:
        self._require_connection()

        symbol_info = MT5Connector.get_symbol_info(self.symbol)
        if not symbol_info:
            raise RuntimeError(f"Could not resolve or select symbol: {self.symbol}")

        self.resolved_symbol = symbol_info.name
        self.digits = int(symbol_info.digits)
        return self.resolved_symbol

    @staticmethod
    def _frame_from_rates(rates, symbol: str, timeframe: str) -> pd.DataFrame:
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5 returned no candles for {symbol} {timeframe}. "
                f"MT5 error: {mt5.last_error()}"
            )

        df = pd.DataFrame(rates)
        required = ["time", "open", "high", "low", "close"]
        missing = [column for column in required if column not in df.columns]
        if missing:
            raise RuntimeError(
                f"Unexpected MT5 candle format. Missing columns: {', '.join(missing)}"
            )

        df["time"] = pd.to_datetime(df["time"], unit="s")
        for column in ["open", "high", "low", "close"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        if "tick_volume" not in df.columns:
            df["tick_volume"] = 0
        if "spread" not in df.columns:
            df["spread"] = 0

        df = df[
            ["time", "open", "high", "low", "close", "tick_volume", "spread"]
        ].copy()
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)

        if df.empty:
            raise RuntimeError(f"Candle data was empty after cleaning: {symbol}")

        return df

    def fetch_recent(self, limit: int = 500) -> pd.DataFrame:
        if limit < 10:
            raise ValueError("At least 10 candles are required.")

        resolved = self._resolve()
        timeframe_id = TIMEFRAME_MAP.get(self.timeframe)
        if timeframe_id is None:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")

        rates = mt5.copy_rates_from_pos(resolved, timeframe_id, 0, int(limit))
        return self._frame_from_rates(rates, resolved, self.timeframe)

    def fetch_history(self, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Fetch a historical range using broker server time.
        Both boundaries are interpreted exactly as passed (no tz conversion).
        """
        if start >= end:
            raise ValueError("start must be earlier than end.")

        resolved = self._resolve()
        timeframe_id = TIMEFRAME_MAP.get(self.timeframe)
        if timeframe_id is None:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")

        rates = mt5.copy_rates_range(resolved, timeframe_id, start, end)
        return self._frame_from_rates(rates, resolved, self.timeframe)

    def sync_recent(self, limit: int = 500) -> pd.DataFrame:
        """Fetch real candles from MT5 and persist them if a store is attached."""
        df = self.fetch_recent(limit)

        if self.store is not None:
            self.store.upsert_candles(
                self.resolved_symbol, self.timeframe, df
            )

        return df

    def load_recent(self, limit: int = 500) -> pd.DataFrame:
        """Load previously stored real candles. No MT5 connection required."""
        if self.store is None:
            raise RuntimeError("No CandleStore attached.")

        resolved = self.symbol
        if self.store.conn is not None:
            # Resolve only for label consistency when a store is connected.
            resolved = self.resolved_symbol or self.symbol

        df = self.store.load_candles(resolved, self.timeframe, limit)
        if df.empty:
            raise RuntimeError(
                f"No stored candles for {resolved} {self.timeframe}. "
                "Use 'Sync MT5 History' first."
            )

        self.resolved_symbol = resolved
        return df

    @staticmethod
    def is_supported_timeframe(timeframe: str) -> bool:
        return timeframe in TIMEFRAME_MAP