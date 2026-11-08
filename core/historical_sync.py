"""Historical multi-timeframe synchronization from MT5 to CandleStore.

Fetches large historical date ranges in chunked requests to prevent MT5 IPC timeouts
and memory pressure, strictly enforcing DEMO-only account verification and
causal 1H -> 15m -> 5m synchronization order.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple, Union

import MetaTrader5 as mt5
import pandas as pd

from core.data_engine import TIMEFRAME_MAP, DataEngine
from core.data_store import CandleStore
from core.mt5_connector import MT5Connector


class HistoricalMTFSync:
    """Synchronizes historical candle ranges from MT5 across multiple timeframes."""

    DEFAULT_TIMEFRAMES = ("1H", "15m", "5m")

    @classmethod
    def sync_date_range(
        cls,
        symbol: str,
        start_dt: Union[datetime, str],
        end_dt: Union[datetime, str],
        timeframes: Tuple[str, ...] = DEFAULT_TIMEFRAMES,
        chunk_days: int = 30,
        store: Optional[CandleStore] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch historical candles in chunks and optionally upsert into CandleStore.

        Args:
            symbol: Target symbol (e.g. 'XAUUSD').
            start_dt: Start datetime (inclusive).
            end_dt: End datetime (inclusive).
            timeframes: Tuple of timeframes in synchronization order (default: 1H -> 15m -> 5m).
            chunk_days: Number of days per MT5 query batch (default: 30).
            store: Optional CandleStore instance to persist candles.

        Returns:
            Dict mapping timeframe string to combined chronological DataFrame.
        """
        if isinstance(start_dt, str):
            start_dt = pd.to_datetime(start_dt).to_pydatetime()
        if isinstance(end_dt, str):
            end_dt = pd.to_datetime(end_dt).to_pydatetime()

        if start_dt >= end_dt:
            raise ValueError(f"start_dt ({start_dt}) must be earlier than end_dt ({end_dt}).")

        if chunk_days < 1:
            raise ValueError("chunk_days must be at least 1.")

        # Thread-safe session management with DEMO-only check
        if not MT5Connector.initialize():
            raise RuntimeError(
                "Failed to initialize MT5 session or account is not a verified DEMO account."
            )

        try:
            resolved = MT5Connector.resolve_symbol(symbol)
            if not resolved:
                raise RuntimeError(f"Could not resolve broker symbol for: {symbol}")

            if not mt5.symbol_select(resolved, True):
                raise RuntimeError(f"Failed to select symbol in MT5 MarketWatch: {resolved}")

            results: Dict[str, pd.DataFrame] = {}

            # Execute in strict order: 1H -> 15m -> 5m
            for tf in timeframes:
                tf_id = TIMEFRAME_MAP.get(tf)
                if tf_id is None:
                    raise ValueError(f"Unsupported timeframe: {tf}")

                logging.info(f"Syncing {resolved} {tf} from {start_dt} to {end_dt} in {chunk_days}-day chunks...")
                chunk_frames: List[pd.DataFrame] = []
                current_start = start_dt

                while current_start < end_dt:
                    current_end = min(current_start + timedelta(days=chunk_days), end_dt)

                    rates = mt5.copy_rates_range(resolved, tf_id, current_start, current_end)
                    if rates is not None and len(rates) > 0:
                        df_chunk = DataEngine._frame_from_rates(rates, resolved, tf)
                        chunk_frames.append(df_chunk)

                    current_start = current_end

                if chunk_frames:
                    combined = pd.concat(chunk_frames, ignore_index=True)
                    combined = combined.drop_duplicates(subset=["time"])
                    combined = combined.sort_values("time")
                    combined = combined.reset_index(drop=True)
                else:
                    combined = pd.DataFrame(
                        columns=["time", "open", "high", "low", "close", "tick_volume", "spread"]
                    )

                if store is not None and not combined.empty:
                    written = store.upsert_candles(resolved, tf, combined)
                    logging.info(f"Persisted {written} candles for {resolved} {tf} into CandleStore.")

                results[tf] = combined

            return results
        finally:
            MT5Connector.shutdown()
