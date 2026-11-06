"""
Persistent Signal panel for Part 10.

Reuses the Part 9 SignalHistoryPanel and adds SQLite persistence.
"""

from core.signal_history import SignalHistory, SignalRecord
from core.signal_store import SignalStore
from gui.widgets.signal_history_panel import SignalHistoryPanel


class PersistentSignalHistory(SignalHistory):
    """
    Signal history that can insert persisted records with stable DB ids.
    """

    def add_existing(self, record: SignalRecord):
        key = record.unique_key()

        if key in self._seen:
            return None

        self._records.append(record)
        self._seen.add(key)

        if int(record.record_id) >= int(self._next_id):
            self._next_id = int(record.record_id) + 1

        if len(self._records) > self.max_records:
            removed = self._records.pop(0)
            self._seen.discard(removed.unique_key())

        return record

    def add_with_id(self, record: SignalRecord, record_id: int):
        record.record_id = int(record_id)
        return self.add_existing(record)


class PersistentSignalHistoryPanel(SignalHistoryPanel):
    """
    Part 9 signal panel with Part 10 SQLite persistence.
    """

    def __init__(self, parent=None):
        self._signal_store = SignalStore()
        self._store_ok = self._signal_store.connect()

        super().__init__(parent)

        # Replace the in-memory history with the persistent-aware history.
        self._history = PersistentSignalHistory(max_records=1000)

        self._load_persisted_signals()

    def _load_persisted_signals(self):
        if not self._store_ok:
            self._log(
                "Signal store unavailable. "
                "Starting with an empty session history."
            )
            return

        try:
            records = self._signal_store.load_all()
        except Exception as exc:
            self._log(f"Could not load persisted signals: {exc}")
            return

        loaded = 0

        for record in records:
            stored = self._history.add_existing(record)
            if stored is not None:
                loaded += 1

        self._refresh_table()

        self._log(
            f"Loaded {loaded} persisted signal record(s) from SQLite."
        )

    def _on_signal_ready(self, record):
        """
        Persist the signal first, then add it to the visible session history.
        """
        if not self._store_ok:
            # Fall back to session-only behavior if persistence is unavailable.
            super()._on_signal_ready(record)
            return

        try:
            db_id = self._signal_store.save(record)
        except Exception as exc:
            self._log(f"Signal persistence error: {exc}")
            self._store_ok = False
            super()._on_signal_ready(record)
            return

        if db_id is None:
            self._log(
                "Signal already persisted for this candle/engine combination. "
                "No duplicate was added."
            )
            self.status_label.setText("Signal already persisted.")
            self.status_label.setStyleSheet("color: #9aa0a6;")
            self._set_controls_enabled(self._enabled)
            return

        stored = self._history.add_with_id(record, db_id)

        if stored is None:
            self._log("Signal already exists in the session history.")
            self.status_label.setText("Signal already recorded.")
            self.status_label.setStyleSheet("color: #9aa0a6;")
        else:
            self._log(
                f"Recorded and persisted signal #{stored.record_id}: "
                f"{stored.symbol} {stored.timeframe} {stored.action}"
            )
            self.status_label.setText(
                f"Persisted #{stored.record_id}: {stored.action}"
            )
            self.status_label.setStyleSheet("color: #2ecc71;")

        self._refresh_table()
        self._set_controls_enabled(self._enabled)

    def close_store(self):
        if self._store_ok:
            self._signal_store.close()
            self._store_ok = False