"""
Signal history panel for Part 9.

Displays session-only signal records and provides copy-to-clipboard actions.
No order execution. No SQLite persistence of signal records.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from gui.signal_worker import SignalWorker
from core.signal_history import SignalHistory
from core.signal_formatter import SignalFormatter
from config import ALLOWED_SYMBOLS, ALLOWED_TIMEFRAMES, DEFAULT_SYMBOL


class SignalHistoryPanel(QWidget):
    """
    Part 9 signal history and copy panel.
    """

    mt5_operation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker = None
        self._enabled = False
        self._history = SignalHistory(max_records=1000)
        self._selected_record = None

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Data / evaluation controls
        data_group = QGroupBox("Signal Input")
        data_layout = QGridLayout(data_group)

        data_layout.addWidget(QLabel("Symbol"), 0, 0)
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.symbol_combo.setCurrentText(DEFAULT_SYMBOL)
        data_layout.addWidget(self.symbol_combo, 0, 1)

        data_layout.addWidget(QLabel("Timeframe"), 0, 2)
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(ALLOWED_TIMEFRAMES)
        self.timeframe_combo.setCurrentText("1m")
        data_layout.addWidget(self.timeframe_combo, 0, 3)

        data_layout.addWidget(QLabel("Bars"), 1, 0)
        self.bars_spin = QSpinBox()
        self.bars_spin.setRange(50, 10000)
        self.bars_spin.setSingleStep(50)
        self.bars_spin.setValue(500)
        data_layout.addWidget(self.bars_spin, 1, 1)

        data_layout.addWidget(QLabel("Engine"), 1, 2)
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("rule")
        self.engine_combo.addItem("adaptive")
        self.engine_combo.addItem("intraday_mtf")
        data_layout.addWidget(self.engine_combo, 1, 3)

        self.exclude_latest_checkbox = QCheckBox(
            "Exclude latest candle (recommended)"
        )
        self.exclude_latest_checkbox.setChecked(True)
        data_layout.addWidget(self.exclude_latest_checkbox, 2, 0, 1, 2)

        self.sync_button = QPushButton("Sync & Evaluate")
        self.sync_button.clicked.connect(lambda: self._evaluate("sync"))
        data_layout.addWidget(self.sync_button, 2, 2)

        self.load_button = QPushButton("Load SQLite & Evaluate")
        self.load_button.clicked.connect(lambda: self._evaluate("load"))
        data_layout.addWidget(self.load_button, 2, 3)

        self.status_label = QLabel("No signal evaluated yet.")
        self.status_label.setStyleSheet("color: #9aa0a6;")
        data_layout.addWidget(self.status_label, 3, 0, 1, 4)

        root_layout.addWidget(data_group)

        # History filters / actions
        history_group = QGroupBox("Session Signal History")
        history_layout = QHBoxLayout(history_group)

        history_layout.addWidget(QLabel("Action"))
        self.action_filter_combo = QComboBox()
        self.action_filter_combo.addItem("ALL")
        self.action_filter_combo.addItems(
            ["LONG_BIAS", "SHORT_BIAS", "LONG_SETUP", "SHORT_SETUP", "NO_TRADE"]
        )
        history_layout.addWidget(self.action_filter_combo)

        history_layout.addWidget(QLabel("Engine"))
        self.engine_filter_combo = QComboBox()
        self.engine_filter_combo.addItem("ALL")
        self.engine_filter_combo.addItem("rule")
        self.engine_filter_combo.addItem("adaptive")
        self.engine_filter_combo.addItem("intraday_mtf")
        history_layout.addWidget(self.engine_filter_combo)

        self.refresh_filter_button = QPushButton("Apply Filter")
        self.refresh_filter_button.clicked.connect(self._refresh_table)
        history_layout.addWidget(self.refresh_filter_button)

        history_layout.addStretch()

        root_layout.addWidget(history_group)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Created",
                "Symbol",
                "Timeframe",
                "Engine",
                "Action",
                "Confidence",
                "Decision Candle",
            ]
        )
        self.history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.history_table.itemSelectionChanged.connect(self._on_selection_changed)

        root_layout.addWidget(self.history_table, stretch=1)

        # Copy actions
        copy_group = QGroupBox("Copy Actions")
        copy_layout = QHBoxLayout(copy_group)

        self.copy_selected_button = QPushButton("Copy Selected Report")
        self.copy_selected_button.clicked.connect(self._copy_selected_text)
        copy_layout.addWidget(self.copy_selected_button)

        self.copy_json_button = QPushButton("Copy Selected JSON")
        self.copy_json_button.clicked.connect(self._copy_selected_json)
        copy_layout.addWidget(self.copy_json_button)

        self.copy_filtered_button = QPushButton("Copy All Filtered")
        self.copy_filtered_button.clicked.connect(self._copy_filtered_text)
        copy_layout.addWidget(self.copy_filtered_button)

        self.clear_button = QPushButton("Clear Session History")
        self.clear_button.clicked.connect(self._clear_history)
        copy_layout.addWidget(self.clear_button)

        copy_layout.addStretch()
        root_layout.addWidget(copy_group)

        # Selected record detail
        detail_group = QGroupBox("Selected Signal Report")
        detail_layout = QVBoxLayout(detail_group)

        self.detail_output = QPlainTextEdit()
        self.detail_output.setReadOnly(True)
        self.detail_output.setMaximumBlockCount(20000)
        self.detail_output.setPlainText(
            "Select a signal record to view its report.\n\n"
            "Generate a signal with Sync & Evaluate or Load SQLite & Evaluate."
        )
        detail_layout.addWidget(self.detail_output)

        root_layout.addWidget(detail_group, stretch=1)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(110)
        self.log_output.setPlainText(
            "Part 9 signal history. Session-only, no persistence yet.\n"
            "No orders are sent. Confidence is heuristic.\n"
        )
        root_layout.addWidget(self.log_output)

        self._interactive_widgets = [
            self.symbol_combo,
            self.timeframe_combo,
            self.bars_spin,
            self.engine_combo,
            self.exclude_latest_checkbox,
            self.sync_button,
            self.load_button,
            self.action_filter_combo,
            self.engine_filter_combo,
            self.refresh_filter_button,
            self.copy_selected_button,
            self.copy_json_button,
            self.copy_filtered_button,
            self.clear_button,
        ]

        self._set_controls_enabled(False)

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self._set_controls_enabled(self._enabled)

    def is_worker_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def wait_for_worker(self, timeout_ms: int = 3000):
        if self.is_worker_running():
            self._worker.wait(timeout_ms)

    def _set_controls_enabled(self, enabled: bool):
        for widget in self._interactive_widgets:
            widget.setEnabled(bool(enabled))

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def _evaluate(self, mode: str):
        if not self._enabled:
            self._log("Signal controls are not enabled yet.")
            return

        if self.is_worker_running():
            self._log("A signal evaluation is already running.")
            return

        payload = {
            "symbol": self.symbol_combo.currentText().strip(),
            "timeframe": self.timeframe_combo.currentText().strip(),
            "bars": int(self.bars_spin.value()),
            "mode": mode,
            "engine": self.engine_combo.currentText().strip(),
            "include_latest": not self.exclude_latest_checkbox.isChecked(),
        }

        self._set_controls_enabled(False)
        self.status_label.setText("Evaluating signal...")
        self.status_label.setStyleSheet("color: #f1c40f;")
        self._log(f"Starting {mode} signal evaluation...")

        self._worker = SignalWorker(payload=payload)
        self._worker.signal_ready.connect(self._on_signal_ready)
        self._worker.error.connect(self._on_error)
        self.mt5_operation_requested.emit()
        self._worker.start()

    def _on_signal_ready(self, record):
        stored = self._history.add(record)

        if stored is None:
            self._log(
                "This candle/engine combination is already recorded. "
                "No duplicate was added."
            )
            self.status_label.setText("Signal already recorded.")
            self.status_label.setStyleSheet("color: #9aa0a6;")
        else:
            self._log(
                f"Recorded signal #{stored.record_id}: "
                f"{stored.symbol} {stored.timeframe} {stored.action}"
            )
            self.status_label.setText(
                f"Recorded #{stored.record_id}: {stored.action}"
            )
            self.status_label.setStyleSheet("color: #2ecc71;")

        self._refresh_table()
        self._set_controls_enabled(self._enabled)

    def _on_error(self, message: str):
        self._log(f"ERROR: {message}")
        self.status_label.setText("Signal evaluation failed.")
        self.status_label.setStyleSheet("color: #e74c3c;")
        self._set_controls_enabled(self._enabled)

    def _refresh_table(self):
        records = self._history.filtered(
            action=self.action_filter_combo.currentText().strip(),
            engine=self.engine_filter_combo.currentText().strip(),
        )

        display = list(records)[-200:][::-1]

        self.history_table.setRowCount(len(display))

        for row, record in enumerate(display):
            id_item = QTableWidgetItem(str(record.record_id))
            id_item.setData(Qt.ItemDataRole.UserRole, record.record_id)
            self.history_table.setItem(row, 0, id_item)

            self.history_table.setItem(
                row, 1, QTableWidgetItem(record.created_at)
            )
            self.history_table.setItem(
                row, 2, QTableWidgetItem(record.symbol)
            )
            self.history_table.setItem(
                row, 3, QTableWidgetItem(record.timeframe)
            )
            self.history_table.setItem(
                row, 4, QTableWidgetItem(record.engine)
            )
            self.history_table.setItem(
                row, 5, QTableWidgetItem(record.action)
            )
            self.history_table.setItem(
                row, 6, QTableWidgetItem(f"{record.confidence:.1f}")
            )
            self.history_table.setItem(
                row, 7, QTableWidgetItem(record.decision_time)
            )

        self.history_table.resizeColumnsToContents()

    def _current_selected_record(self):
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return None

        row = rows[0].row()
        item = self.history_table.item(row, 0)
        if item is None:
            return None

        record_id = item.data(Qt.ItemDataRole.UserRole)

        for record in self._history.all_records():
            if record.record_id == record_id:
                return record

        return None

    def _on_selection_changed(self):
        record = self._current_selected_record()

        if record is None:
            self._selected_record = None
            return

        self._selected_record = record
        self.detail_output.setPlainText(SignalFormatter.to_text(record))

    def _copy_to_clipboard(self, text: str, description: str):
        clipboard = self._clipboard()

        if clipboard is None:
            self._log("Clipboard is unavailable on this system.")
            return

        clipboard.setText(text)
        self._log(f"Copied {description} to clipboard.")

    def _clipboard(self):
        from PyQt6.QtWidgets import QApplication
        return QApplication.clipboard()

    def _copy_selected_text(self):
        record = self._current_selected_record()

        if record is None:
            self._log("Select a signal record first.")
            return

        self._copy_to_clipboard(
            SignalFormatter.to_text(record),
            f"signal #{record.record_id} report",
        )

    def _copy_selected_json(self):
        record = self._current_selected_record()

        if record is None:
            self._log("Select a signal record first.")
            return

        self._copy_to_clipboard(
            SignalFormatter.to_json(record),
            f"signal #{record.record_id} JSON",
        )

    def _copy_filtered_text(self):
        records = self._history.filtered(
            action=self.action_filter_combo.currentText().strip(),
            engine=self.engine_filter_combo.currentText().strip(),
        )

        if not records:
            self._log("No filtered signal records to copy.")
            return

        reports = [SignalFormatter.to_text(record) for record in records]
        self._copy_to_clipboard(
            "\n\n" + "\n\n--------------------------------\n\n".join(reports),
            f"{len(records)} filtered signal reports",
        )

    def _clear_history(self):
        if self.is_worker_running():
            self._log("Wait for the running evaluation to finish.")
            return

        self._history.clear()
        self._selected_record = None
        self._refresh_table()

        self.detail_output.setPlainText(
            "Session history cleared.\n"
            "No database data was deleted."
        )
        self._log("Session history cleared.")
        self.status_label.setText("No signal evaluated yet.")
        self.status_label.setStyleSheet("color: #9aa0a6;")