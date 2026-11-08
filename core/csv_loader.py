"""CSV Data Loader and Exporter for NeuroTrade AI.

Supports standard OHLCV CSVs and MetaTrader 5 exported CSV/tab files,
enforcing strict OHLCV validation, causal ordering, and optional persistence
to CandleStore.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from typing import Optional, Union

import numpy as np
import pandas as pd

from core.data_store import CandleStore


class CSVDataLoader:
    """Imports, validates, and exports historical candles in CSV format."""

    REQUIRED_PRICE_COLS = ["open", "high", "low", "close"]

    @classmethod
    def detect_format_and_read(cls, file_path_or_buffer: Union[str, io.StringIO]) -> pd.DataFrame:
        """Read CSV or TSV buffer/file, auto-detecting delimiters and MT5/standard columns."""
        # Detect delimiter if it's a file path
        delimiter = ","
        if isinstance(file_path_or_buffer, str):
            if not os.path.isfile(file_path_or_buffer):
                raise FileNotFoundError(f"CSV file not found: {file_path_or_buffer}")
            with open(file_path_or_buffer, "r", encoding="utf-8-sig", errors="replace") as f:
                first_line = f.readline()
                if "\t" in first_line:
                    delimiter = "\t"
                elif ";" in first_line:
                    delimiter = ";"
            df = pd.read_csv(file_path_or_buffer, sep=delimiter, encoding="utf-8-sig")
        else:
            # Buffer
            content = file_path_or_buffer.getvalue()
            first_line = content.split("\n")[0] if "\n" in content else content
            if "\t" in first_line:
                delimiter = "\t"
            elif ";" in first_line:
                delimiter = ";"
            file_path_or_buffer.seek(0)
            df = pd.read_csv(file_path_or_buffer, sep=delimiter)

        # Normalize column headers: strip whitespace and <> brackets
        cleaned_columns = {}
        for col in df.columns:
            clean = str(col).strip().strip("<>").lower()
            cleaned_columns[col] = clean
        df = df.rename(columns=cleaned_columns)

        # Handle MT5 date + time separate columns
        if "date" in df.columns and "time" in df.columns:
            # Combine Date and Time
            df["time"] = pd.to_datetime(
                df["date"].astype(str).str.strip().str.replace(".", "-", regex=False)
                + " "
                + df["time"].astype(str).str.strip()
            )
            df = df.drop(columns=["date"])
        elif "datetime" in df.columns:
            df["time"] = pd.to_datetime(df["datetime"])
        elif "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
        elif "open_time" in df.columns:
            # Could be numeric epoch or datetime string
            if pd.api.types.is_numeric_dtype(df["open_time"]):
                df["time"] = pd.to_datetime(df["open_time"], unit="s")
            else:
                df["time"] = pd.to_datetime(df["open_time"])
            df = df.drop(columns=["open_time"])
        else:
            raise ValueError("CSV missing required timestamp column ('time', 'date'+'time', or 'datetime').")

        # Normalize column aliases
        aliases = {
            "tickvol": "tick_volume",
            "tick_vol": "tick_volume",
            "vol": "volume",
        }
        df = df.rename(columns=aliases)

        if "tick_volume" not in df.columns:
            df["tick_volume"] = df["volume"] if "volume" in df.columns else 0
        if "spread" not in df.columns:
            df["spread"] = 0

        keep_cols = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
        existing = [c for c in keep_cols if c in df.columns]
        df = df[existing].copy()

        return df

    @classmethod
    def validate_candles(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Enforce strict OHLCV validation.

        - Required columns: time, open, high, low, close
        - Finite numeric positive prices
        - high >= max(open, close) and low <= min(open, close)
        - Monotonic strictly increasing unique timestamps
        """
        if df is None or df.empty:
            raise ValueError("Candle DataFrame is empty.")

        for col in cls.REQUIRED_PRICE_COLS:
            if col not in df.columns:
                raise ValueError(f"Missing required price column: {col}")
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if "time" not in df.columns:
            raise ValueError("Missing 'time' column.")

        # Ensure datetime type
        if not pd.api.types.is_datetime64_any_dtype(df["time"]):
            df["time"] = pd.to_datetime(df["time"])

        # Check for non-finite values (NaN, Inf, -Inf)
        price_vals = df[cls.REQUIRED_PRICE_COLS].values
        if not np.isfinite(price_vals).all():
            raise ValueError("Candle prices contain NaN or non-finite values.")

        # Check positivity
        if (price_vals <= 0).any():
            raise ValueError("Candle prices must be strictly positive.")

        # Check High and Low validity
        max_oc = np.maximum(df["open"].values, df["close"].values)
        min_oc = np.minimum(df["open"].values, df["close"].values)

        invalid_high = df["high"].values < max_oc
        if invalid_high.any():
            bad_idx = np.where(invalid_high)[0][0]
            raise ValueError(
                f"Invalid candle at index {bad_idx} ({df.iloc[bad_idx]['time']}): "
                f"high ({df.iloc[bad_idx]['high']}) < max(open, close) ({max_oc[bad_idx]})."
            )

        invalid_low = df["low"].values > min_oc
        if invalid_low.any():
            bad_idx = np.where(invalid_low)[0][0]
            raise ValueError(
                f"Invalid candle at index {bad_idx} ({df.iloc[bad_idx]['time']}): "
                f"low ({df.iloc[bad_idx]['low']}) > min(open, close) ({min_oc[bad_idx]})."
            )

        if (df["high"].values < df["low"].values).any():
            raise ValueError("Invalid candle: high < low.")

        # Check timestamps uniqueness and monotonicity
        if df["time"].duplicated().any():
            dups = df["time"][df["time"].duplicated()].iloc[0]
            raise ValueError(f"CSV data contains duplicate timestamp: {dups}")

        if not df["time"].is_monotonic_increasing:
            raise ValueError("CSV timestamps must be strictly monotonic increasing.")

        # Ensure tick_volume and spread exist
        if "tick_volume" not in df.columns:
            df["tick_volume"] = 0
        else:
            df["tick_volume"] = pd.to_numeric(df["tick_volume"], errors="coerce").fillna(0).astype(int)

        if "spread" not in df.columns:
            df["spread"] = 0
        else:
            df["spread"] = pd.to_numeric(df["spread"], errors="coerce").fillna(0).astype(int)

        df = df[["time", "open", "high", "low", "close", "tick_volume", "spread"]].copy()
        df = df.reset_index(drop=True)
        return df

    @classmethod
    def load_csv(
        cls,
        file_path: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        store: Optional[CandleStore] = None,
    ) -> pd.DataFrame:
        """Load, validate, and optionally persist candles from a CSV file."""
        raw_df = cls.detect_format_and_read(file_path)
        valid_df = cls.validate_candles(raw_df)

        if store is not None and symbol and timeframe:
            store.upsert_candles(symbol, timeframe, valid_df)
            logging.info(
                f"Persisted {len(valid_df)} candles for {symbol} {timeframe} from {file_path}"
            )

        return valid_df

    @classmethod
    def export_csv(
        cls,
        store: CandleStore,
        symbol: str,
        timeframe: str,
        file_path: str,
        limit: Optional[int] = None,
    ) -> int:
        """Export candles from CandleStore to a standardized CSV file."""
        if store is None or store.conn is None:
            raise RuntimeError("CandleStore is not connected.")

        df = store.load_candles(symbol, timeframe, limit=limit)
        if df.empty:
            raise ValueError(f"No candles found in store for {symbol} {timeframe}.")

        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        # Format time as ISO string for maximum compatibility
        df_export = df.copy()
        df_export["time"] = df_export["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_export.to_csv(file_path, index=False)
        return len(df_export)
