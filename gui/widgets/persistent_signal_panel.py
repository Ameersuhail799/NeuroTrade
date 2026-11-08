"""
Persistent Signal panel for Part 10.

Reuses the Part 9 SignalHistoryPanel and adds SQLite persistence.
"""

from PyQt6.QtWidgets import QPushButton

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

        # Add Track Signal Outcomes button to copy_group
        self.track_outcomes_button = QPushButton("Track Signal Outcomes")
        self.track_outcomes_button.setStyleSheet(
            "background-color: #1565c0; color: #ffffff; font-weight: bold;"
        )
        self.track_outcomes_button.clicked.connect(self._track_signal_outcomes)

        if hasattr(self, "prefill_trade_button") and self.prefill_trade_button.parentWidget():
            parent_layout = self.prefill_trade_button.parentWidget().layout()
            if parent_layout:
                parent_layout.insertWidget(0, self.track_outcomes_button)

        self._interactive_widgets.append(self.track_outcomes_button)

        self._load_persisted_signals()

    def _load_persisted_signals(self):
        if not self._store_ok:
            self._log(
                "Signal store unavailable. "
                "Starting with an empty session history."
            )
            return

        try:
            records = self._signal_store.load_all_with_outcomes()
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

    def _track_signal_outcomes(self):
        if not self._store_ok:
            self._log("SignalStore unavailable.")
            return

        all_records = self._history.all_records()
        setups = [r for r in all_records if r.action in ("LONG_SETUP", "SHORT_SETUP")]
        if not setups:
            self._log("No actionable setups (LONG_SETUP / SHORT_SETUP) in history to track.")
            return

        from core.candle_store import CandleStore
        from core.signal_outcome_tracker import SignalOutcomeTracker

        candle_store = CandleStore()
        if not candle_store.connect():
            self._log("CandleStore connection failed. Cannot load M5 candles.")
            return

        try:
            symbols = list(set(r.symbol for r in setups))
            all_resolved = []

            for sym in symbols:
                sym_setups = [r for r in setups if r.symbol == sym]
                m5_df = candle_store.load(symbol=sym, timeframe="5m", limit=10000)
                if m5_df.empty:
                    self._log(f"No M5 candles found in SQLite for {sym}.")
                    continue

                resolved = SignalOutcomeTracker.evaluate_outcomes(
                    signals=sym_setups,
                    m5_candles_df=m5_df,
                )

                for res in resolved:
                    self._signal_store.save_outcome(res)
                    for rec in sym_setups:
                        if rec.record_id == res.signal_id:
                            if not isinstance(rec.inputs, dict):
                                rec.inputs = {}
                            rec.inputs["outcome"] = res.to_dict()

                all_resolved.extend(resolved)

            self._refresh_table()

            if all_resolved:
                report = SignalOutcomeTracker.compute_calibration_report(all_resolved)
                self.detail_output.setPlainText(report)
                self._log(
                    f"Successfully evaluated forward outcomes for {len(all_resolved)} setups across {len(symbols)} symbol(s)."
                )
            else:
                self._log("No forward candles were available after signal decision times.")
        except Exception as exc:
            self._log(f"Error tracking signal outcomes: {exc}")
        finally:
            candle_store.close()

    def close_store(self):
        if self._store_ok:
            self._signal_store.close()
            self._store_ok = False