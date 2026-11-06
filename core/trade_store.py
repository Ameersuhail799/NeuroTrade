"""
SQLite persistence for Part 6 demo trade executions.

Part 10 scope:
- Local audit persistence only.
- Does not modify MT5.
- Does not send orders.
- Does not reconcile with broker history.
"""

import json
import sqlite3
from datetime import datetime

from config import DB_PATH


class TradeStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = None

    def connect(self) -> bool:
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._create_tables()
            return True
        except sqlite3.Error:
            return False

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                worker_action TEXT NOT NULL,
                success INTEGER NOT NULL,
                symbol TEXT,
                ticket INTEGER,
                retcode INTEGER,
                message TEXT,
                price REAL,
                volume REAL,
                sl REAL,
                tp REAL,
                notes TEXT,
                payload TEXT
            )
            """
        )

        self.conn.commit()

    def save_execution(self, result, worker_action: str, payload: dict) -> int:
        """
        Persist a TradeExecutionResult.

        Returns the local SQLite row id.
        """
        if self.conn is None:
            raise RuntimeError("TradeStore is not connected.")

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO trade_executions (
                created_at,
                worker_action,
                success,
                symbol,
                ticket,
                retcode,
                message,
                price,
                volume,
                sl,
                tp,
                notes,
                payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(worker_action),
                1 if result.success else 0,
                str(result.symbol),
                int(result.ticket),
                int(result.retcode),
                str(result.message),
                float(result.price),
                float(result.volume),
                float(result.sl),
                float(result.tp),
                json.dumps(list(result.notes), ensure_ascii=True),
                json.dumps(dict(payload or {}), ensure_ascii=True),
            ),
        )

        self.conn.commit()
        return int(cursor.lastrowid)

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None