"""Multi-timeframe candle data coordinator for NeuroTrade AI.

Coordinates causal fetching and loading of H1, M15, and M5 candles.
Ensures correct sync order (1H -> 15m -> 5m) so higher timeframes never
outpace or lag lower-timeframe decision bars during live boundaries.
"""

from typing import Dict, Optional

import pandas as pd

from core.data_engine import DataEngine
from core.data_store import CandleStore


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
    ) -> Dict[str, pd.DataFrame]:
        """Fetch real candles from MT5 in strict 1H -> 15m -> 5m order and persist if store attached."""
        results = {}
        for tf in self.TIMEFRAMES:
            bars = self.get_required_bars(tf, requested_bars)
            engine = DataEngine(symbol=self.symbol, timeframe=tf, store=self.store)
            df = engine.sync_recent(limit=bars)
            results[tf] = df

        return results

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
