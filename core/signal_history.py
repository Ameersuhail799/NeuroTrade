"""
Session-only signal history for Part 9.

No SQLite persistence is implemented here.
Persistence belongs to Part 10.

All records are produced from real decisions made by the existing engines.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


@dataclass
class SignalRecord:
    record_id: int
    created_at: str
    engine: str
    engine_version: str
    symbol: str
    timeframe: str
    decision_time: str
    action: str
    score: float
    confidence: float
    rows_used: int
    exclude_latest: bool
    inputs: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)

    def unique_key(self) -> tuple:
        """
        Prevent duplicate records for the same candle/engine combination.
        """
        return (
            str(self.engine),
            str(self.symbol),
            str(self.timeframe),
            str(self.decision_time),
        )


class SignalHistory:
    """
    In-memory signal history for the current application session.
    """

    def __init__(self, max_records: int = 1000):
        self.max_records = max(1, int(max_records))
        self._records: List[SignalRecord] = []
        self._seen: set = set()
        self._next_id = 1

    def add(self, record: SignalRecord) -> Optional[SignalRecord]:
        """
        Add a record if it is not a duplicate.

        Returns the stored record, or None if it was already recorded.
        """
        key = record.unique_key()

        if key in self._seen:
            return None

        stored = SignalRecord(
            record_id=self._next_id,
            created_at=str(record.created_at),
            engine=str(record.engine),
            engine_version=str(record.engine_version),
            symbol=str(record.symbol),
            timeframe=str(record.timeframe),
            decision_time=str(record.decision_time),
            action=str(record.action),
            score=float(record.score),
            confidence=float(record.confidence),
            rows_used=int(record.rows_used),
            exclude_latest=bool(record.exclude_latest),
            inputs=dict(record.inputs),
            reasons=list(record.reasons),
            warnings=list(record.warnings),
            weights=dict(record.weights),
        )

        self._next_id += 1
        self._records.append(stored)
        self._seen.add(key)

        if len(self._records) > self.max_records:
            removed = self._records.pop(0)
            self._seen.discard(removed.unique_key())

        return stored

    def all_records(self) -> List[SignalRecord]:
        return list(self._records)

    def filtered(
        self,
        action: str = "ALL",
        engine: str = "ALL",
    ) -> List[SignalRecord]:
        result = []

        for record in self._records:
            if action != "ALL" and record.action != action:
                continue

            if engine != "ALL" and record.engine != engine:
                continue

            result.append(record)

        return result

    def clear(self):
        """
        Clear the in-memory session history.
        Does not delete any database data.
        """
        self._records.clear()
        self._seen.clear()

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [asdict(record) for record in self._records]