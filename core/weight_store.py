"""
SQLite persistence for adaptive rule weights, feedback run reports,
and cached symbol contract info.
"""

import os
import sqlite3
from datetime import datetime

from config import DB_PATH
from core.rule_features import DEFAULT_WEIGHTS


class WeightStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = None

    def connect(self) -> bool:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._create_tables()
            return True
        except sqlite3.Error:
            return False

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_weights (
                rule_name TEXT PRIMARY KEY,
                weight REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT,
                timeframe TEXT,
                report TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_contracts (
                symbol TEXT PRIMARY KEY,
                resolved_symbol TEXT NOT NULL,
                point REAL NOT NULL,
                digits INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        self.conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_weights(self) -> dict:
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        weights = dict(DEFAULT_WEIGHTS)

        cursor = self.conn.cursor()
        cursor.execute("SELECT rule_name, weight FROM rule_weights")

        for rule_name, weight in cursor.fetchall():
            weights[str(rule_name)] = float(weight)

        return weights

    def save_weights(self, weights: dict):
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        cursor = self.conn.cursor()
        now = self._now()

        for rule_name, weight in weights.items():
            cursor.execute(
                """
                INSERT OR REPLACE INTO rule_weights
                (rule_name, weight, updated_at)
                VALUES (?, ?, ?)
                """,
                (str(rule_name), float(weight), now),
            )

        self.conn.commit()

    def reset_weights(self):
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM rule_weights")
        self.conn.commit()

    def save_run(self, symbol: str, timeframe: str, report: str):
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO feedback_runs
            (created_at, symbol, timeframe, report)
            VALUES (?, ?, ?, ?)
            """,
            (self._now(), str(symbol), str(timeframe), str(report)),
        )

        self.conn.commit()

    def save_contract(
        self,
        symbol: str,
        resolved_symbol: str,
        point: float,
        digits: int,
    ):
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO symbol_contracts
            (symbol, resolved_symbol, point, digits, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(symbol),
                str(resolved_symbol),
                float(point),
                int(digits),
                self._now(),
            ),
        )

        self.conn.commit()

    def load_contract(self, symbol: str):
        if self.conn is None:
            raise RuntimeError("WeightStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT symbol, resolved_symbol, point, digits
            FROM symbol_contracts
            WHERE symbol = ?
            """,
            (str(symbol),),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "symbol": str(row[0]),
            "resolved_symbol": str(row[1]),
            "point": float(row[2]),
            "digits": int(row[3]),
        }

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None