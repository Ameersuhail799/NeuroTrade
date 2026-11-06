"""
SQLite persistence for Part 9 signal records.

Part 10 scope:
- Persist signal records.
- Load persisted signal records on startup.
- Prevent duplicate persisted signals by unique decision key.

This store does not send orders and does not modify decision logic.
"""

import json
import sqlite3
from typing import List, Optional

from config import DB_PATH
from core.signal_history import SignalRecord


class SignalStore:
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
            CREATE TABLE IF NOT EXISTS signal_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                engine TEXT NOT NULL,
                engine_version TEXT,
                symbol TEXT,
                timeframe TEXT,
                decision_time TEXT,
                action TEXT,
                score REAL,
                confidence REAL,
                rows_used INTEGER,
                exclude_latest INTEGER,
                inputs TEXT,
                reasons TEXT,
                warnings TEXT,
                weights TEXT
            )
            """
        )

        self.conn.commit()

    @staticmethod
    def _unique_key(record: SignalRecord) -> str:
        return "|".join(str(part) for part in record.unique_key())

    def save(self, record: SignalRecord) -> Optional[int]:
        """
        Persist a signal record.

        Returns:
        - new row id if inserted
        - None if the signal was already persisted
        """
        if self.conn is None:
            raise RuntimeError("SignalStore is not connected.")

        key = self._unique_key(record)

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO signal_records (
                unique_key,
                created_at,
                engine,
                engine_version,
                symbol,
                timeframe,
                decision_time,
                action,
                score,
                confidence,
                rows_used,
                exclude_latest,
                inputs,
                reasons,
                warnings,
                weights
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                str(record.created_at),
                str(record.engine),
                str(record.engine_version),
                str(record.symbol),
                str(record.timeframe),
                str(record.decision_time),
                str(record.action),
                float(record.score),
                float(record.confidence),
                int(record.rows_used),
                1 if record.exclude_latest else 0,
                json.dumps(record.inputs, ensure_ascii=True),
                json.dumps(record.reasons, ensure_ascii=True),
                json.dumps(record.warnings, ensure_ascii=True),
                json.dumps(record.weights, ensure_ascii=True),
            ),
        )

        self.conn.commit()

        if cursor.rowcount == 0:
            return None

        return int(cursor.lastrowid)

    def load_all(self) -> List[SignalRecord]:
        if self.conn is None:
            raise RuntimeError("SignalStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                created_at,
                engine,
                engine_version,
                symbol,
                timeframe,
                decision_time,
                action,
                score,
                confidence,
                rows_used,
                exclude_latest,
                inputs,
                reasons,
                warnings,
                weights
            FROM signal_records
            ORDER BY id ASC
            """
        )

        records: List[SignalRecord] = []

        for row in cursor.fetchall():
            record = SignalRecord(
                record_id=int(row[0]),
                created_at=str(row[1]),
                engine=str(row[2]),
                engine_version=str(row[3] or ""),
                symbol=str(row[4] or ""),
                timeframe=str(row[5] or ""),
                decision_time=str(row[6] or ""),
                action=str(row[7] or ""),
                score=float(row[8] or 0.0),
                confidence=float(row[9] or 0.0),
                rows_used=int(row[10] or 0),
                exclude_latest=bool(row[11]),
                inputs=json.loads(row[12] or "{}"),
                reasons=json.loads(row[13] or "[]"),
                warnings=json.loads(row[14] or "[]"),
                weights=json.loads(row[15] or "{}"),
            )
            records.append(record)

        return records

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None