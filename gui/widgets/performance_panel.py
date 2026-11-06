"""
Performance panel for Part 8.

Standalone dashboard panel for real demo account performance metrics.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from gui.performance_worker import PerformanceWorker
from gui.widgets.equity_curve import EquityCurve
from core.performance_engine import format_report
from config import ALLOWED_SYMBOLS, DEFAULT_SYMBOL


class PerformancePanel(QWidget):
    """
    Part 8 performance dashboard panel.
    """

    mt5_operation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker = None
        self._enabled = False

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Controls
        controls_group = QGroupBox("Performance Filter")
        controls_layout = QHBoxLayout(controls_group)

        controls_layout.addWidget(QLabel("Symbol"))

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItem("ALL")
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.symbol_combo.setCurrentText("ALL")
        controls_layout.addWidget(self.symbol_combo)

        controls_layout.addWidget(QLabel("Days"))

        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 3650)
        self.days_spin.setValue(30)
        controls_layout.addWidget(self.days_spin)

        self.refresh_button = QPushButton("Refresh Performance")
        self.refresh_button.clicked.connect(self._refresh)
        controls_layout.addWidget(self.refresh_button)

        controls_layout.addStretch()

        self.status_label = QLabel("No performance data loaded.")
        self.status_label.setStyleSheet("color: #9aa0a6;")
        controls_layout.addWidget(self.status_label)

        root_layout.addWidget(controls_group)

        # Equity curve
        equity_group = QGroupBox("Closed-Trade Equity Curve")
        equity_layout = QVBoxLayout(equity_group)

        self.equity_curve = EquityCurve()
        equity_layout.addWidget(self.equity_curve)

        root_layout.addWidget(equity_group)

        # Metrics report
        report_group = QGroupBox("Metrics")
        report_layout = QVBoxLayout(report_group)

        self.report_output = QPlainTextEdit()
        self.report_output.setReadOnly(True)
        self.report_output.setMaximumBlockCount(20000)
        self.report_output.setPlainText(
            "Click Refresh Performance to load real demo account history.\n\n"
            "No backtest results are shown."
        )
        report_layout.addWidget(self.report_output)

        root_layout.addWidget(report_group, stretch=1)

        # Trades table
        trades_group = QGroupBox("Closed Trades")
        trades_layout = QVBoxLayout(trades_group)

        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(7)
        self.trades_table.setHorizontalHeaderLabels(
            [
                "Position",
                "Symbol",
                "Direction",
                "Volume",
                "Open Time",
                "Close Time",
                "Net PnL",
            ]
        )
        self.trades_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.trades_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.trades_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.trades_table.verticalHeader().setVisible(False)
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        trades_layout.addWidget(self.trades_table)
        root_layout.addWidget(trades_group, stretch=1)

        note = QLabel(
            "Real MT5 demo history only. Win rate alone is not success. "
            "Profit factor, expectancy and drawdown must be reviewed together."
        )
        note.setStyleSheet("color: #9aa0a6;")
        note.setWordWrap(True)
        root_layout.addWidget(note)

        self._interactive_widgets = [
            self.symbol_combo,
            self.days_spin,
            self.refresh_button,
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

    def _append_report(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.report_output.appendPlainText(f"[{timestamp}] {message}")

    def _refresh(self):
        if not self._enabled:
            self._append_report("Performance controls are not enabled yet.")
            return

        if self.is_worker_running():
            self._append_report("Performance refresh already running.")
            return

        self._set_controls_enabled(False)
        self.status_label.setText("Refreshing performance...")
        self.status_label.setStyleSheet("color: #f1c40f;")

        symbol_filter = self.symbol_combo.currentText().strip()
        days = int(self.days_spin.value())

        self._worker = PerformanceWorker(
            symbol_filter=symbol_filter,
            days=days,
        )
        self._worker.report_ready.connect(self._on_report_ready)
        self._worker.error.connect(self._on_error)
        self.mt5_operation_requested.emit()
        self._worker.start()

    def _on_report_ready(self, metrics):
        self.report_output.setPlainText(format_report(metrics))
        self.equity_curve.set_data(metrics.equity_curve)
        self._populate_trades(metrics.trades)

        self.status_label.setText(
            f"Closed trades: {metrics.total_trades} | "
            f"Net: {metrics.total_net:.2f} {metrics.account_currency}"
        )
        self.status_label.setStyleSheet("color: #2ecc71;")

        self._set_controls_enabled(self._enabled)

    def _on_error(self, message: str):
        self._append_report(f"ERROR: {message}")
        self.status_label.setText("Performance refresh failed.")
        self.status_label.setStyleSheet("color: #e74c3c;")
        self._set_controls_enabled(self._enabled)

    def _populate_trades(self, trades):
        # Show latest closed trades first, capped to avoid huge tables.
        display_trades = list(trades)[-200:][::-1]

        self.trades_table.setRowCount(len(display_trades))

        for row, trade in enumerate(display_trades):
            self.trades_table.setItem(
                row, 0, QTableWidgetItem(str(trade.position_id))
            )
            self.trades_table.setItem(
                row, 1, QTableWidgetItem(str(trade.symbol))
            )
            self.trades_table.setItem(
                row, 2, QTableWidgetItem(str(trade.direction))
            )
            self.trades_table.setItem(
                row, 3, QTableWidgetItem(f"{float(trade.volume):.2f}")
            )

            open_time = (
                trade.open_time.strftime("%Y-%m-%d %H:%M:%S")
                if trade.open_time
                else ""
            )
            close_time = (
                trade.close_time.strftime("%Y-%m-%d %H:%M:%S")
                if trade.close_time
                else ""
            )

            self.trades_table.setItem(row, 4, QTableWidgetItem(open_time))
            self.trades_table.setItem(row, 5, QTableWidgetItem(close_time))
            self.trades_table.setItem(
                row, 6, QTableWidgetItem(f"{float(trade.net_profit):.2f}")
            )

        self.trades_table.resizeColumnsToContents()