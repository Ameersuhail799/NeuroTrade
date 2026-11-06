"""
Feedback panel for Part 7.

Standalone UI for:
- loading indicator-enriched candle history
- training adaptive rule weights
- validating adapted weights out-of-sample
- resetting persisted weights
- evaluating the latest candle with adapted weights
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
)
from PyQt6.QtCore import pyqtSignal

from gui.feedback_worker import FeedbackWorker
from core.adaptive_decision_engine import AdaptiveDecisionEngine
from core.decision_engine import RuleBasedDecisionEngine
from core.rule_features import DEFAULT_WEIGHTS, format_weights
from config import ALLOWED_SYMBOLS, ALLOWED_TIMEFRAMES, DEFAULT_SYMBOL


class FeedbackPanel(QWidget):
    """
    Part 7 feedback training panel.
    """

    mt5_operation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker = None
        self._enabled = False

        self._df = None
        self._meta = None
        self._weights = dict(DEFAULT_WEIGHTS)

        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Data group
        data_group = QGroupBox("Candle Data")
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
        self.bars_spin.setRange(100, 20000)
        self.bars_spin.setSingleStep(100)
        self.bars_spin.setValue(1000)
        data_layout.addWidget(self.bars_spin, 1, 1)

        self.sync_button = QPushButton("Sync MT5 Data")
        self.sync_button.clicked.connect(lambda: self._load_data("sync"))
        data_layout.addWidget(self.sync_button, 1, 2)

        self.load_db_button = QPushButton("Load SQLite Data")
        self.load_db_button.clicked.connect(lambda: self._load_data("load"))
        data_layout.addWidget(self.load_db_button, 1, 3)

        self.data_status_label = QLabel("No data loaded.")
        self.data_status_label.setStyleSheet("color: #9aa0a6;")
        data_layout.addWidget(self.data_status_label, 2, 0, 1, 4)

        root_layout.addWidget(data_group)

        # Training group
        training_group = QGroupBox("Feedback Training")
        training_layout = QGridLayout(training_group)

        training_layout.addWidget(QLabel("Outcome candles"), 0, 0)
        self.horizon_spin = QSpinBox()
        self.horizon_spin.setRange(1, 500)
        self.horizon_spin.setValue(30)
        training_layout.addWidget(self.horizon_spin, 0, 1)

        training_layout.addWidget(QLabel("Min outcome points"), 0, 2)
        self.min_points_spin = QDoubleSpinBox()
        self.min_points_spin.setRange(0.0, 10000.0)
        self.min_points_spin.setDecimals(1)
        self.min_points_spin.setSingleStep(10.0)
        self.min_points_spin.setValue(50.0)
        training_layout.addWidget(self.min_points_spin, 0, 3)

        training_layout.addWidget(QLabel("Learning rate"), 1, 0)
        self.learning_rate_spin = QDoubleSpinBox()
        self.learning_rate_spin.setRange(0.0001, 1.0)
        self.learning_rate_spin.setDecimals(4)
        self.learning_rate_spin.setSingleStep(0.005)
        self.learning_rate_spin.setValue(0.0100)
        training_layout.addWidget(self.learning_rate_spin, 1, 1)

        training_layout.addWidget(QLabel("Train fraction %"), 1, 2)
        self.train_fraction_spin = QSpinBox()
        self.train_fraction_spin.setRange(50, 90)
        self.train_fraction_spin.setValue(70)
        training_layout.addWidget(self.train_fraction_spin, 1, 3)

        self.start_default_checkbox = QCheckBox("Start from default weights")
        self.start_default_checkbox.setChecked(True)
        training_layout.addWidget(self.start_default_checkbox, 2, 0, 1, 2)

        self.train_button = QPushButton("Train && Validate")
        self.train_button.clicked.connect(self._train)
        training_layout.addWidget(self.train_button, 2, 2)

        self.evaluate_button = QPushButton("Evaluate Latest (Adapted)")
        self.evaluate_button.clicked.connect(self._evaluate_latest)
        training_layout.addWidget(self.evaluate_button, 2, 3)

        self.refresh_weights_button = QPushButton("Refresh Weights")
        self.refresh_weights_button.clicked.connect(self._refresh_weights)
        training_layout.addWidget(self.refresh_weights_button, 3, 0)

        self.reset_weights_button = QPushButton("Reset Weights")
        self.reset_weights_button.clicked.connect(self._reset_weights)
        training_layout.addWidget(self.reset_weights_button, 3, 1)

        self.weights_status_label = QLabel("Weights not loaded.")
        self.weights_status_label.setStyleSheet("color: #9aa0a6;")
        training_layout.addWidget(self.weights_status_label, 3, 2, 1, 2)

        root_layout.addWidget(training_group)

        # Output
        output_group = QGroupBox("Feedback Output")
        output_layout = QVBoxLayout(output_group)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(20000)
        self.output.setPlainText(
            "Part 7 feedback loop.\n\n"
            "1. Sync MT5 Data or Load SQLite Data.\n"
            "2. Train & Validate.\n"
            "3. Review out-of-sample validation results.\n\n"
            "This module does not send orders."
        )
        output_layout.addWidget(self.output)

        root_layout.addWidget(output_group, stretch=1)

        note = QLabel(
            "Adaptive weighted scoring only. Confidence is heuristic. "
            "Results exclude spread, commission and slippage. "
            "No profitability is promised."
        )
        note.setStyleSheet("color: #9aa0a6;")
        note.setWordWrap(True)
        root_layout.addWidget(note)

        self._interactive_widgets = [
            self.symbol_combo,
            self.timeframe_combo,
            self.bars_spin,
            self.sync_button,
            self.load_db_button,
            self.horizon_spin,
            self.min_points_spin,
            self.learning_rate_spin,
            self.train_fraction_spin,
            self.start_default_checkbox,
            self.train_button,
            self.evaluate_button,
            self.refresh_weights_button,
            self.reset_weights_button,
        ]

        self._set_controls_enabled(False)

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self._set_controls_enabled(self._enabled)

        if self._enabled and not self.is_worker_running():
            self._start_worker("weights", {})

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

    def _prepare_action(self) -> bool:
        if not self._enabled:
            self._append_output("Feedback controls are not enabled yet.")
            return False

        self.mt5_operation_requested.emit()

        if self.is_worker_running():
            self._append_output("A feedback operation is already running.")
            return False

        return True

    def _start_worker(self, action: str, payload: dict):
        if self.is_worker_running():
            self._append_output("A feedback operation is already running.")
            return

        self._set_controls_enabled(False)
        self._append_output(f"Starting {action} operation...")

        self._worker = FeedbackWorker(action=action, payload=payload)
        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.train_ready.connect(self._on_train_ready)
        self._worker.weights_ready.connect(self._on_weights_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _load_data(self, mode: str):
        if not self._prepare_action():
            return

        payload = {
            "symbol": self.symbol_combo.currentText().strip(),
            "timeframe": self.timeframe_combo.currentText().strip(),
            "bars": int(self.bars_spin.value()),
            "mode": mode,
        }

        self._start_worker("load", payload)

    def _train(self):
        if not self._prepare_action():
            return

        if self._df is None or self._meta is None:
            self._append_output("Load candle data first.")
            return

        payload = {
            "df": self._df,
            "meta": self._meta,
            "horizon": int(self.horizon_spin.value()),
            "min_outcome_points": float(self.min_points_spin.value()),
            "learning_rate": float(self.learning_rate_spin.value()),
            "train_fraction": float(self.train_fraction_spin.value()) / 100.0,
            "start_from_default": bool(self.start_default_checkbox.isChecked()),
        }

        self._start_worker("train", payload)

    def _refresh_weights(self):
        if not self._prepare_action():
            return

        self._start_worker("weights", {})

    def _reset_weights(self):
        if not self._prepare_action():
            return

        self._start_worker("reset_weights", {})

    def _evaluate_latest(self):
        if self._df is None or self._meta is None:
            self._append_output("Load candle data first.")
            return

        weights = self._weights or DEFAULT_WEIGHTS

        try:
            engine = AdaptiveDecisionEngine(weights=weights)
            result = engine.evaluate(
                df=self._df,
                meta=self._meta,
                exclude_latest=True,
            )

            report = RuleBasedDecisionEngine.format_report(result)

            self._append_output("Latest-candle adaptive evaluation complete.")
            self.output.setPlainText(report)

        except Exception as exc:
            self._append_output(f"Adaptive evaluation error: {exc}")

    def _on_data_ready(self, df, meta):
        self._df = df
        self._meta = meta

        self.data_status_label.setText(
            f"{meta.get('symbol', '')} {meta.get('timeframe', '')} | "
            f"{meta.get('rows', 0)} candles | source: {meta.get('source', '')} | "
            f"point: {meta.get('point', '')}"
        )
        self.data_status_label.setStyleSheet("color: #2ecc71;")

        self._append_output(
            f"Data loaded: {meta.get('symbol', '')} {meta.get('timeframe', '')} "
            f"{meta.get('rows', 0)} candles from {meta.get('source', '')}."
        )

        self._set_controls_enabled(self._enabled)

    def _on_train_ready(self, report: str, weights: dict):
        self._weights = weights

        self.weights_status_label.setText("Adapted weights saved to SQLite.")
        self.weights_status_label.setStyleSheet("color: #2ecc71;")

        self.output.setPlainText(report)
        self._append_output("Training and validation complete.")

        self._set_controls_enabled(self._enabled)

    def _on_weights_ready(self, weights: dict, message: str):
        self._weights = weights

        self.weights_status_label.setText(message)
        self.weights_status_label.setStyleSheet("color: #9aa0a6;")

        self._append_output(message)
        self._append_output("Current weights:")
        self._append_output(format_weights(weights))

        self._set_controls_enabled(self._enabled)

    def _on_error(self, message: str):
        self._append_output(f"ERROR: {message}")
        self._set_controls_enabled(self._enabled)