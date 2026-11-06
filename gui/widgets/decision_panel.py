"""
Decision panel widget for Part 5.

This panel displays the current rule-based decision output.
It does not send orders and does not persist decisions yet.
Persistence belongs to Part 10.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QGroupBox,
)

from core.decision_engine import RuleBasedDecisionEngine
from gui.decision_worker import DecisionWorker


class DecisionPanel(QWidget):
    """
    UI panel for running and displaying rule-based decisions.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._df = None
        self._meta = None
        self._worker = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        input_group = QGroupBox("Decision Input")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)

        self.data_status_label = QLabel(
            "No indicator data loaded. "
            "Use the Data tab and run Sync MT5 History or Load From SQLite first."
        )
        self.data_status_label.setWordWrap(True)
        self.data_status_label.setStyleSheet("color: #9aa0a6;")
        input_layout.addWidget(self.data_status_label)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.exclude_latest_checkbox = QCheckBox(
            "Exclude latest candle (recommended)"
        )
        self.exclude_latest_checkbox.setChecked(True)
        self.exclude_latest_checkbox.setEnabled(False)
        controls_layout.addWidget(self.exclude_latest_checkbox)

        self.run_button = QPushButton("Evaluate Decision")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._run_decision)
        controls_layout.addWidget(self.run_button)

        controls_layout.addStretch()
        input_layout.addLayout(controls_layout)

        self.decision_status_label = QLabel("No decision computed yet.")
        self.decision_status_label.setStyleSheet("color: #9aa0a6;")
        input_layout.addWidget(self.decision_status_label)

        output_group = QGroupBox("Decision Output")
        output_layout = QVBoxLayout(output_group)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlainText(
            "No decision computed yet.\n\n"
            "1. Load candle history in the Data tab.\n"
            "2. Return to this tab.\n"
            "3. Click Evaluate Decision."
        )
        output_layout.addWidget(self.output)

        note = QLabel(
            "Rule-based heuristic only. No orders are sent. "
            "Confidence is not win probability."
        )
        note.setStyleSheet("color: #9aa0a6;")
        note.setWordWrap(True)

        layout.addWidget(input_group)
        layout.addWidget(output_group, stretch=1)
        layout.addWidget(note)

    def set_data(self, df, meta):
        """
        Provide indicator-enriched candle data from Part 4.
        """
        if df is None or len(df) == 0:
            self.clear_data()
            return

        self._df = df
        self._meta = dict(meta or {})

        symbol = self._meta.get("symbol", "UNKNOWN")
        timeframe = self._meta.get("timeframe", "UNKNOWN")
        rows = self._meta.get("rows", len(df))
        source = self._meta.get("source", "UNKNOWN")

        self.data_status_label.setText(
            f"Loaded {symbol} {timeframe} | {rows} candles | source: {source}"
        )
        self.data_status_label.setStyleSheet("color: #2ecc71;")

        self.exclude_latest_checkbox.setEnabled(True)
        self.run_button.setEnabled(True)
        self.decision_status_label.setText("Ready to evaluate.")
        self.decision_status_label.setStyleSheet("color: #9aa0a6;")

    def clear_data(self):
        self._df = None
        self._meta = None

        self.data_status_label.setText(
            "No indicator data loaded. "
            "Use the Data tab and run Sync MT5 History or Load From SQLite first."
        )
        self.data_status_label.setStyleSheet("color: #9aa0a6;")

        self.exclude_latest_checkbox.setEnabled(False)
        self.run_button.setEnabled(False)
        self.decision_status_label.setText("No decision computed yet.")
        self.decision_status_label.setStyleSheet("color: #9aa0a6;")

    def _run_decision(self):
        if self._df is None or len(self._df) == 0:
            self.output.setPlainText(
                "No indicator data loaded.\n\n"
                "Use the Data tab and run Sync MT5 History or Load From SQLite first."
            )
            return

        if self._worker is not None and self._worker.isRunning():
            self.decision_status_label.setText("Decision evaluation already running.")
            return

        self.run_button.setEnabled(False)
        self.decision_status_label.setText("Evaluating decision...")
        self.decision_status_label.setStyleSheet("color: #f1c40f;")
        self.output.setPlainText("Evaluating rule-based decision...")

        self._worker = DecisionWorker(
            df=self._df,
            meta=self._meta,
            exclude_latest=self.exclude_latest_checkbox.isChecked(),
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result):
        self.run_button.setEnabled(True)
        self.decision_status_label.setText(
            f"Decision: {result.action} | "
            f"heuristic confidence {result.confidence:.0f}/100"
        )
        self.decision_status_label.setStyleSheet("color: #2ecc71;")
        self.output.setPlainText(RuleBasedDecisionEngine.format_report(result))

    def _on_error(self, message: str):
        self.run_button.setEnabled(True)
        self.decision_status_label.setText("Decision evaluation failed.")
        self.decision_status_label.setStyleSheet("color: #e74c3c;")
        self.output.setPlainText(f"Decision error:\n\n{message}")

    def wait_for_worker(self, timeout_ms: int = 3000):
        """
        Used by the main window close event to avoid destroying the widget
        while the decision worker is still running.
        """
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(timeout_ms)