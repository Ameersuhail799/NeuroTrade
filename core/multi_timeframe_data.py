"""Multi-timeframe candle data coordinator for NeuroTrade AI.

Coordinates causal fetching and loading of H1, M15, and M5 candles.
Ensures correct sync order (1H -> 15m -> 5m) so higher timeframes never
outpace or lag lower-timeframe decision bars during live boundaries.
"""

import logging
from typing import Dict, Optional

import pandas as pd

from core.data_engine import DataEngine
from core.data_store import CandleStore
from core.mt5_connector import MT5Connector
from core.web_market_data import WebMarketDataProvider


class MultiTimeframeDataCoordinator:
    """Coordinates multi-timeframe candle synchronization and offline loading."""

    TIMEFRAMES = ("1H", "15m", "5m")
    MIN_BARS = {
        "1H": 250,   # At least 221 needed (220 completed + 1 forming) for EMA-200
        "15m": 100,  # At least 61 needed (60 completed + 1 forming)
        "5m": 100,   # At least 61 needed (60 completed + 1 forming)
    }

    def __init__(self, symbol: str, store: Optional[CandleStore] = None):
        self.symbol = symbol
        self.store = store

    @classmethod
    def get_required_bars(cls, timeframe: str, requested_bars: int = 500) -> int:
        """Return the required bars ensuring minimum count for indicator warm-up."""
        min_required = cls.MIN_BARS.get(timeframe, 100)
        return max(int(requested_bars), min_required)

    def sync_all(
        self,
        requested_bars: int = 500,
        use_web_fallback: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch candles in 1H -> 15m -> 5m order and persist if store attached.

        Tries live MT5 connection first; if MT5 is offline/uninstalled, falls back to WebMarketDataProvider.
        """
        # Try live MT5 connection first
        if MT5Connector.initialize():
            try:
                results = {}
                for tf in self.TIMEFRAMES:
                    bars = self.get_required_bars(tf, requested_bars)
                    engine = DataEngine(symbol=self.symbol, timeframe=tf, store=self.store)
                    df = engine.sync_recent(limit=bars)
                    results[tf] = df
                return results
            except Exception as exc:
                logging.warning(
                    f"MT5 multi-timeframe sync failed ({exc}). Falling back to Web feed."
                )

        # Fallback to WebMarketDataProvider
        if use_web_fallback:
            logging.info(
                f"Syncing market data for {self.symbol} via WebMarketDataProvider fallback..."
            )
            mtf_data = WebMarketDataProvider.fetch_mtf_candles(
                self.symbol, requested_bars=requested_bars
            )
            if self.store is not None:
                resolved = WebMarketDataProvider.resolve_symbol(self.symbol)
                for tf, df in mtf_data.items():
                    self.store.upsert_candles(resolved, tf, df)
            return mtf_data

        raise RuntimeError(
            f"MT5 is unavailable and web fallback is disabled for {self.symbol}."
        )

    def load_all(
        self,
        requested_bars: int = 500,
    ) -> Dict[str, pd.DataFrame]:
        """Load stored candles from SQLite in 1H, 15m, 5m format."""
        if self.store is None:
            raise RuntimeError("No CandleStore attached to MultiTimeframeDataCoordinator.")

        results = {}
        for tf in self.TIMEFRAMES:
            bars = self.get_required_bars(tf, requested_bars)
            engine = DataEngine(symbol=self.symbol, timeframe=tf, store=self.store)
            df = engine.load_recent(limit=bars)
            results[tf] = df

        return results
