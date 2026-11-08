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
from typing import Any, Dict, List, Optional

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

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS intraday_signal_outcomes (
                signal_id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                decision_time TEXT NOT NULL,
                action TEXT NOT NULL,
                confluence_score REAL NOT NULL,
                outcome TEXT NOT NULL,
                outcome_r REAL NOT NULL,
                resolved_at TEXT NOT NULL,
                holding_bars INTEGER DEFAULT 0,
                entry_price REAL,
                exit_price REAL,
                notes TEXT,
                FOREIGN KEY (signal_id) REFERENCES signal_records(id)
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

    def save_outcome(self, outcome: Any) -> bool:
        """
        Persist or update an intraday signal forward tracking outcome.
        Accepts a SignalOutcomeRecord or a dictionary.
        """
        if self.conn is None:
            raise RuntimeError("SignalStore is not connected.")

        if hasattr(outcome, "to_dict"):
            d = outcome.to_dict()
        elif isinstance(outcome, dict):
            d = outcome
        else:
            d = {
                "signal_id": getattr(outcome, "signal_id", 0),
                "symbol": getattr(outcome, "symbol", ""),
                "decision_time": getattr(outcome, "decision_time", ""),
                "action": getattr(outcome, "action", ""),
                "confluence_score": getattr(outcome, "confluence_score", 0.0),
                "outcome": getattr(outcome, "outcome", ""),
                "outcome_r": getattr(outcome, "outcome_r", 0.0),
                "resolved_at": getattr(outcome, "resolved_at", ""),
                "holding_bars": getattr(outcome, "holding_bars", 0),
                "entry_price": getattr(outcome, "entry_price", 0.0),
                "exit_price": getattr(outcome, "exit_price", 0.0),
                "notes": getattr(outcome, "notes", ""),
            }

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO intraday_signal_outcomes (
                signal_id,
                symbol,
                decision_time,
                action,
                confluence_score,
                outcome,
                outcome_r,
                resolved_at,
                holding_bars,
                entry_price,
                exit_price,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(d.get("signal_id", 0)),
                str(d.get("symbol", "")),
                str(d.get("decision_time", "")),
                str(d.get("action", "")),
                float(d.get("confluence_score", 0.0)),
                str(d.get("outcome", "")),
                float(d.get("outcome_r", 0.0)),
                str(d.get("resolved_at", "")),
                int(d.get("holding_bars", 0)),
                float(d.get("entry_price", 0.0)),
                float(d.get("exit_price", 0.0)),
                str(d.get("notes", "")),
            ),
        )
        self.conn.commit()
        return True

    def load_outcomes(self) -> Dict[int, Dict[str, Any]]:
        """
        Load all persisted outcomes mapped by signal_id.
        """
        if self.conn is None:
            raise RuntimeError("SignalStore is not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                signal_id,
                symbol,
                decision_time,
                action,
                confluence_score,
                outcome,
                outcome_r,
                resolved_at,
                holding_bars,
                entry_price,
                exit_price,
                notes
            FROM intraday_signal_outcomes
            """
        )
        outcomes = {}
        for row in cursor.fetchall():
            outcomes[int(row[0])] = {
                "signal_id": int(row[0]),
                "symbol": str(row[1]),
                "decision_time": str(row[2]),
                "action": str(row[3]),
                "confluence_score": float(row[4]),
                "outcome": str(row[5]),
                "outcome_r": float(row[6]),
                "resolved_at": str(row[7]),
                "holding_bars": int(row[8]),
                "entry_price": float(row[9]),
                "exit_price": float(row[10]),
                "notes": str(row[11] or ""),
            }
        return outcomes

    def load_all_with_outcomes(self) -> List[SignalRecord]:
        """
        Load all signal records with their tracked forward outcomes injected into inputs.
        """
        records = self.load_all()
        outcomes = self.load_outcomes()
        for rec in records:
            if rec.record_id in outcomes:
                if not isinstance(rec.inputs, dict):
                    rec.inputs = {}
                rec.inputs["outcome"] = outcomes[rec.record_id]
        return records

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None