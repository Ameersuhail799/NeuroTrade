"""
Trading panel for Part 6.

Manual demo trading UI.
No real-money trading. No automated order execution.
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
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QPlainTextEdit,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from gui.trade_worker import TradeWorker
from config import ALLOWED_SYMBOLS, DEFAULT_SYMBOL


class TradingPanel(QWidget):
    """
    Manual demo trading panel.

    mt5_operation_requested can be connected by a parent window to pause
    other MT5 work, such as live chart refreshes.
    """

    mt5_operation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker = None
        self._mt5_guard = None
        self._enabled = False

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Account / contract status
        account_group = QGroupBox("Account / Contract")
        account_layout = QVBoxLayout(account_group)

        self.account_label = QLabel("Account not refreshed.")
        self.account_label.setStyleSheet("color: #9aa0a6;")
        self.account_label.setWordWrap(True)

        self.market_label = QLabel("Contract info not refreshed.")
        self.market_label.setStyleSheet("color: #9aa0a6;")
        self.market_label.setWordWrap(True)

        account_layout.addWidget(self.account_label)
        account_layout.addWidget(self.market_label)
        root_layout.addWidget(account_group)

        # New demo order controls
        order_group = QGroupBox("New Demo Order")
        order_layout = QGridLayout(order_group)

        order_layout.addWidget(QLabel("Symbol"), 0, 0)
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.symbol_combo.setCurrentText(DEFAULT_SYMBOL)
        order_layout.addWidget(self.symbol_combo, 0, 1)

        order_layout.addWidget(QLabel("Volume"), 0, 2)
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0.01, 100.0)
        self.volume_spin.setDecimals(2)
        self.volume_spin.setSingleStep(0.01)
        self.volume_spin.setValue(0.01)
        order_layout.addWidget(self.volume_spin, 0, 3)

        order_layout.addWidget(QLabel("SL points"), 1, 0)
        self.sl_spin = QSpinBox()
        self.sl_spin.setRange(0, 1_000_000)
        self.sl_spin.setValue(300)
        order_layout.addWidget(self.sl_spin, 1, 1)

        order_layout.addWidget(QLabel("TP points"), 1, 2)
        self.tp_spin = QSpinBox()
        self.tp_spin.setRange(0, 1_000_000)
        self.tp_spin.setValue(600)
        order_layout.addWidget(self.tp_spin, 1, 3)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_context)
        order_layout.addWidget(self.refresh_button, 2, 0)

        self.open_long_button = QPushButton("Open Demo Long")
        self.open_long_button.clicked.connect(lambda: self._open_position("buy"))
        order_layout.addWidget(self.open_long_button, 2, 1)

        self.open_short_button = QPushButton("Open Demo Short")
        self.open_short_button.clicked.connect(lambda: self._open_position("sell"))
        order_layout.addWidget(self.open_short_button, 2, 2)

        self.close_button = QPushButton("Close Selected Position")
        self.close_button.clicked.connect(self._close_selected_position)
        order_layout.addWidget(self.close_button, 2, 3)

        root_layout.addWidget(order_group)

        # Open positions
        positions_group = QGroupBox("Open Positions")
        positions_layout = QVBoxLayout(positions_group)

        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(9)
        self.positions_table.setHorizontalHeaderLabels(
            [
                "Ticket",
                "Symbol",
                "Type",
                "Volume",
                "Open Price",
                "SL",
                "TP",
                "Profit",
                "Open Time",
            ]
        )
        self.positions_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.positions_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.positions_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.positions_table.verticalHeader().setVisible(False)
        self.positions_table.horizontalHeader().setStretchLastSection(True)
        self.positions_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        positions_layout.addWidget(self.positions_table)
        root_layout.addWidget(positions_group, stretch=1)

        # Trade output
        output_group = QGroupBox("Trade Output")
        output_layout = QVBoxLayout(output_group)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(10000)
        self.output.setPlainText(
            "Manual demo trading only.\n"
            "Click Refresh first, then use the demo order buttons.\n"
            "No real orders can be sent from this module."
        )
        output_layout.addWidget(self.output)

        root_layout.addWidget(output_group, stretch=1)

        note = QLabel(
            "DEMO only. Manual execution only. Confidence and decision outputs "
            "from other tabs are not used here."
        )
        note.setStyleSheet("color: #9aa0a6;")
        note.setWordWrap(True)
        root_layout.addWidget(note)

        self._interactive_widgets = [
            self.symbol_combo,
            self.volume_spin,
            self.sl_spin,
            self.tp_spin,
            self.refresh_button,
            self.open_long_button,
            self.open_short_button,
            self.close_button,
        ]

        self._set_controls_enabled(False)

    def set_mt5_guard(self, callback):
        """
        Optional callback returning True when MT5 operations are allowed.
        Used to avoid concurrent MT5 operations in a larger app.
        """
        self._mt5_guard = callback

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

    def _append_output(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.output.appendPlainText(f"[{timestamp}] {message}")

    def _prepare_mt5_action(self) -> bool:
        if not self._enabled:
            self._append_output("Trading controls are not enabled yet.")
            return False

        self.mt5_operation_requested.emit()

        if self.is_worker_running():
            self._append_output("A trade operation is already running.")
            return False

        if callable(self._mt5_guard) and not self._mt5_guard():
            self._append_output(
                "Another MT5 operation is in progress. Please wait."
            )
            return False

        return True

    def _start_worker(self, action: str, payload: dict):
        if self.is_worker_running():
            self._append_output("A trade operation is already running.")
            return

        self._set_controls_enabled(False)
        self._append_output(f"Starting {action} operation...")

        self._worker = TradeWorker(action=action, payload=payload)
        self._worker.context_ready.connect(self._on_context_ready)
        self._worker.execution_ready.connect(self._on_execution_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _refresh_context(self):
        if not self._prepare_mt5_action():
            return

        symbol = self.symbol_combo.currentText().strip()
        self._start_worker("context", {"symbol": symbol})

    def _open_position(self, side: str):
        if not self._prepare_mt5_action():
            return

        payload = {
            "symbol": self.symbol_combo.currentText().strip(),
            "side": side,
            "volume": float(self.volume_spin.value()),
            "sl_points": int(self.sl_spin.value()),
            "tp_points": int(self.tp_spin.value()),
        }

        self._start_worker("open", payload)

    def _close_selected_position(self):
        if not self._prepare_mt5_action():
            return

        selected_rows = self.positions_table.selectionModel().selectedRows()
        if not selected_rows:
            self._append_output("Select a position row first.")
            return

        row = selected_rows[0].row()
        ticket_item = self.positions_table.item(row, 0)

        if ticket_item is None:
            self._append_output("Selected row has no ticket.")
            return

        ticket = ticket_item.data(Qt.ItemDataRole.UserRole)
        if ticket is None:
            self._append_output("Selected row has an invalid ticket.")
            return

        self._start_worker("close", {"ticket": int(ticket)})

    def _on_context_ready(self, context: dict):
        account = context.get("account", {})
        contract = context.get("contract", {})
        positions = context.get("positions", [])

        try:
            balance_text = f"{float(account.get('balance', 0.0)):.2f}"
            equity_text = f"{float(account.get('equity', 0.0)):.2f}"
        except Exception:
            balance_text = str(account.get("balance", "--"))
            equity_text = str(account.get("equity", "--"))

        self.account_label.setText(
            f"Demo account {account.get('login', '--')} | "
            f"Server: {account.get('server', '--')} | "
            f"Balance: {balance_text} {account.get('currency', '')} | "
            f"Equity: {equity_text} {account.get('currency', '')} | "
            f"Algo Trading: {'Yes' if account.get('trade_allowed') else 'No'}"
        )

        self.market_label.setText(
            f"{contract.get('symbol', '--')} | "
            f"Digits: {contract.get('digits', '--')} | "
            f"Point: {contract.get('point', '--')} | "
            f"Volume min: {contract.get('volume_min', '--')} | "
            f"Volume max: {contract.get('volume_max', '--')} | "
            f"Volume step: {contract.get('volume_step', '--')} | "
            f"Stops level: {contract.get('stops_level', '--')} points"
        )

        self._update_volume_spin(contract)
        self._populate_positions(positions)

        self._append_output(
            f"Refresh complete. Open positions: {len(positions)}."
        )

        self._set_controls_enabled(self._enabled)

    def _on_execution_ready(self, result):
        self._append_output(result.message)

        for note in result.notes:
            self._append_output(f"Note: {note}")

        if result.success:
            self._append_output("Refreshing positions after execution...")
            self._start_worker(
                "context",
                {"symbol": self.symbol_combo.currentText().strip()},
            )
        else:
            self._set_controls_enabled(self._enabled)

    def _on_error(self, message: str):
        self._append_output(f"ERROR: {message}")
        self._set_controls_enabled(self._enabled)

    def _update_volume_spin(self, contract: dict):
        try:
            volume_min = float(contract.get("volume_min", 0.01))
            volume_max = float(contract.get("volume_max", 100.0))
            volume_step = float(contract.get("volume_step", 0.01))

            if volume_step <= 0.0:
                volume_step = 0.01

            decimals = self._decimals_from_step(volume_step)

            self.volume_spin.blockSignals(True)
            self.volume_spin.setDecimals(decimals)
            self.volume_spin.setSingleStep(volume_step)
            self.volume_spin.setRange(volume_min, volume_max)

            if self.volume_spin.value() < volume_min:
                self.volume_spin.setValue(volume_min)

            self.volume_spin.blockSignals(False)

        except Exception as exc:
            self._append_output(f"Could not update volume rules: {exc}")

    @staticmethod
    def _decimals_from_step(step: float) -> int:
        text = f"{float(step):.10f}".rstrip("0")
        if "." in text:
            return len(text.split(".")[1])
        return 0

    def _populate_positions(self, positions: list):
        self.positions_table.setRowCount(len(positions))

        for row, position in enumerate(positions):
            ticket = int(position.get("ticket", 0))

            ticket_item = QTableWidgetItem(str(ticket))
            ticket_item.setData(Qt.ItemDataRole.UserRole, ticket)
            self.positions_table.setItem(row, 0, ticket_item)

            self.positions_table.setItem(
                row, 1, QTableWidgetItem(str(position.get("symbol", "")))
            )
            self.positions_table.setItem(
                row, 2, QTableWidgetItem(str(position.get("type", "")))
            )
            self.positions_table.setItem(
                row, 3, QTableWidgetItem(f"{float(position.get('volume', 0.0)):.2f}")
            )
            self.positions_table.setItem(
                row,
                4,
                QTableWidgetItem(f"{float(position.get('open_price', 0.0)):.5f}"),
            )
            self.positions_table.setItem(
                row, 5, QTableWidgetItem(f"{float(position.get('sl', 0.0)):.5f}")
            )
            self.positions_table.setItem(
                row, 6, QTableWidgetItem(f"{float(position.get('tp', 0.0)):.5f}")
            )
            self.positions_table.setItem(
                row, 7, QTableWidgetItem(f"{float(position.get('profit', 0.0)):.2f}")
            )
            self.positions_table.setItem(
                row, 8, QTableWidgetItem(str(position.get("time", "")))
            )

        self.positions_table.resizeColumnsToContents()