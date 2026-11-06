"""
SQLite storage for real MT5 candle history.

Time is stored as the Unix epoch seconds returned by MT5 (broker server time).
No timezone conversion is applied, so chart and storage stay consistent.
"""

import os
import sqlite3
import logging
from typing import Optional

import pandas as pd

from config import DB_PATH


class CandleStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> bool:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._create_tables()
            return True
        except sqlite3.Error as exc:
            logging.error(f"CandleStore connection error: {exc}")
            return False

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                tick_volume INTEGER,
                spread INTEGER,
                PRIMARY KEY (symbol, timeframe, open_time)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles (symbol, timeframe, open_time)
            """
        )
        self.conn.commit()

    @staticmethod
    def _to_unix(value) -> int:
        """Convert a pandas timestamp or numeric epoch to integer seconds."""
        if isinstance(value, (int, float)):
            return int(value)
        timestamp = pd.Timestamp(value)
        return int(timestamp.value // 1_000_000_000)

    def upsert_candles(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> int:
        """Insert or replace candles. Returns number of rows written."""
        if self.conn is None:
            raise RuntimeError("CandleStore is not connected.")

        if df is None or len(df) == 0:
            return 0

        required = ["time", "open", "high", "low", "close"]
        missing = [column for column in required if column not in df.columns]
        if missing:
            raise ValueError(f"Missing candle columns: {', '.join(missing)}")

        rows = []
        for row in df.itertuples(index=False):
            rows.append(
                (
                    symbol,
                    timeframe,
                    self._to_unix(row.time),
                    float(row.open),
                    float(row.high),
                    float(row.low),
                    float(row.close),
                    int(getattr(row, "tick_volume", 0) or 0),
                    int(getattr(row, "spread", 0) or 0),
                )
            )

        cursor = self.conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO candles
            (symbol, timeframe, open_time, open, high, low, close, tick_volume, spread)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def load_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Load the newest candles, returned oldest first."""
        if self.conn is None:
            raise RuntimeError("CandleStore is not connected.")

        if limit < 1:
            raise ValueError("limit must be >= 1.")

        query = """
            SELECT open_time, open, high, low, close, tick_volume, spread
            FROM (
                SELECT * FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY open_time DESC
                LIMIT ?
            )
            ORDER BY open_time ASC
        """

        df = pd.read_sql_query(
            query,
            self.conn,
            params=(symbol, timeframe, int(limit)),
        )

        if df.empty:
            return pd.DataFrame(
                columns=[
                    "time", "open", "high", "low", "close", "tick_volume", "spread"
                ]
            )

        df["time"] = pd.to_datetime(df.pop("open_time"), unit="s")
        return df

    def count_candles(self, symbol: str, timeframe: str) -> int:
        if self.conn is None:
            raise RuntimeError("CandleStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        )
        return int(cursor.fetchone()[0])

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None