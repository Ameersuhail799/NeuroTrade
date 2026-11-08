"""Backtest, Walk-Forward Validation, and Strategy Ablation Tab for NeuroTrade AI."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import ALLOWED_SYMBOLS, DEFAULT_SYMBOL
from core.intraday_backtester import BacktestResult
from core.market_regimes import IntradayStrategyConfig
from gui.backtest_worker import BacktestWorker
from gui.widgets.equity_curve import EquityCurve


class BacktestPanel(QWidget):
    """PyQt6 tab providing event-driven backtesting, walk-forward, and ablation controls."""

    mt5_operation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: BacktestWorker | None = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # LEFT COLUMN: Parameters & Execution Controls
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_widget.setMaximumWidth(320)

        # 1. Dataset Box
        data_box = QGroupBox("Dataset & Instrument")
        data_layout = QVBoxLayout(data_box)

        lbl_sym = QLabel("Symbol:")
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        if DEFAULT_SYMBOL in ALLOWED_SYMBOLS:
            self.symbol_combo.setCurrentText(DEFAULT_SYMBOL)

        lbl_bars = QLabel("M5 Bars (History Span):")
        self.bars_spin = QSpinBox()
        self.bars_spin.setRange(200, 50000)
        self.bars_spin.setValue(2000)
        self.bars_spin.setSingleStep(500)

        data_layout.addWidget(lbl_sym)
        data_layout.addWidget(self.symbol_combo)
        data_layout.addWidget(lbl_bars)
        data_layout.addWidget(self.bars_spin)
        left_layout.addWidget(data_box)

        # 2. Risk & Execution Costs Box
        risk_box = QGroupBox("Risk & Microstructure Costs")
        risk_layout = QVBoxLayout(risk_box)

        lbl_risk = QLabel("Risk % per Trade:")
        self.risk_spin = QDoubleSpinBox()
        self.risk_spin.setRange(0.1, 5.0)
        self.risk_spin.setValue(0.5)
        self.risk_spin.setSingleStep(0.1)
        self.risk_spin.setSuffix("%")

        lbl_spread = QLabel("Default Spread (pts):")
        self.spread_spin = QDoubleSpinBox()
        self.spread_spin.setRange(0.0, 200.0)
        self.spread_spin.setValue(20.0)
        self.spread_spin.setSingleStep(5.0)

        lbl_slip = QLabel("Slippage (pts):")
        self.slippage_spin = QDoubleSpinBox()
        self.slippage_spin.setRange(0.0, 100.0)
        self.slippage_spin.setValue(5.0)
        self.slippage_spin.setSingleStep(1.0)

        risk_layout.addWidget(lbl_risk)
        risk_layout.addWidget(self.risk_spin)
        risk_layout.addWidget(lbl_spread)
        risk_layout.addWidget(self.spread_spin)
        risk_layout.addWidget(lbl_slip)
        risk_layout.addWidget(self.slippage_spin)
        left_layout.addWidget(risk_box)

        # 3. Strategy Filters Box
        strat_box = QGroupBox("Level 4 High-Precision Filters")
        strat_layout = QVBoxLayout(strat_box)

        self.rollover_check = QCheckBox("Rollover Block (21-23 UTC)")
        self.rollover_check.setChecked(True)

        self.asian_breakout_check = QCheckBox("Block Asian Breakouts")
        self.asian_breakout_check.setChecked(False)

        self.spread_filter_check = QCheckBox("Spread-to-Risk Gate")
        self.spread_filter_check.setChecked(True)

        self.regime_filter_check = QCheckBox("Regime Filter (ER + ATR%)")
        self.regime_filter_check.setChecked(False)

        self.scale_out_check = QCheckBox("50/50 Scale-Out at TP1 + BE")
        self.scale_out_check.setChecked(True)

        strat_layout.addWidget(self.rollover_check)
        strat_layout.addWidget(self.asian_breakout_check)
        strat_layout.addWidget(self.spread_filter_check)
        strat_layout.addWidget(self.regime_filter_check)
        strat_layout.addWidget(self.scale_out_check)
        left_layout.addWidget(strat_box)

        # 4. Action Buttons Box
        action_box = QGroupBox("Analysis Actions")
        action_layout = QVBoxLayout(action_box)

        self.sync_backtest_btn = QPushButton("Sync MT5 & Backtest")
        self.sync_backtest_btn.setStyleSheet("background-color: #1a5276; font-weight: bold;")
        self.sync_backtest_btn.clicked.connect(self._on_sync_backtest_clicked)

        self.load_backtest_btn = QPushButton("Load SQLite & Backtest")
        self.load_backtest_btn.clicked.connect(self._on_load_backtest_clicked)

        self.ablation_btn = QPushButton("Run 5-Stage Ablation")
        self.ablation_btn.clicked.connect(self._on_ablation_clicked)

        self.walk_forward_btn = QPushButton("Run Walk-Forward (4-Fold)")
        self.walk_forward_btn.clicked.connect(self._on_walk_forward_clicked)

        self.status_label = QLabel("Ready for backtest analysis.")
        self.status_label.setStyleSheet("color: #9aa0a6;")
        self.status_label.setWordWrap(True)

        action_layout.addWidget(self.sync_backtest_btn)
        action_layout.addWidget(self.load_backtest_btn)
        action_layout.addWidget(self.ablation_btn)
        action_layout.addWidget(self.walk_forward_btn)
        action_layout.addWidget(self.status_label)
        left_layout.addWidget(action_box)

        left_layout.addStretch()
        main_layout.addWidget(left_widget)

        # -------------------------------------------------------------
        # RIGHT COLUMN: Equity Curve Visualization & Detailed Scorecard
        # -------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        curve_group = QGroupBox("Cumulative Closed-Trade PnL Curve ($)")
        curve_layout = QVBoxLayout(curve_group)
        self.equity_curve = EquityCurve()
        curve_layout.addWidget(self.equity_curve)
        right_layout.addWidget(curve_group)

        report_group = QGroupBox("Performance & Scorecard Output")
        report_layout = QVBoxLayout(report_group)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Consolas", 9))
        self.report_view.setPlainText(
            "Select an instrument, set execution costs, and click 'Load SQLite & Backtest' "
            "or 'Sync MT5 & Backtest' to generate an institutional performance report."
        )
        report_layout.addWidget(self.report_view)
        right_layout.addWidget(report_group)

        main_layout.addWidget(right_widget, stretch=1)

    def _get_strategy_config(self) -> IntradayStrategyConfig:
        return IntradayStrategyConfig(
            enable_rollover_block=self.rollover_check.isChecked(),
            block_asian_breakouts=self.asian_breakout_check.isChecked(),
            enable_spread_filter=self.spread_filter_check.isChecked(),
            enable_regime_filter=self.regime_filter_check.isChecked(),
        )

    def _start_worker(self, mode: str, run_type: str):
        if self._worker is not None and self._worker.isRunning():
            return

        self._set_controls_enabled(False)
        self.status_label.setStyleSheet("color: #f39c12;")
        self.status_label.setText(f"Running {run_type} ({mode.upper()})...")

        symbol = self.symbol_combo.currentText()
        bars = self.bars_spin.value()
        risk_pct = self.risk_spin.value() / 100.0
        spread_pts = self.spread_spin.value()
        slip_pts = self.slippage_spin.value()
        scale_out = self.scale_out_check.isChecked()
        strat_cfg = self._get_strategy_config()

        self._worker = BacktestWorker(
            symbol=symbol,
            mode=mode,
            run_type=run_type,
            bars=bars,
            capital=10000.0,
            risk=risk_pct,
            spread=spread_pts,
            slippage=slip_pts,
            scale_out_tp1=scale_out,
            strategy_config=strat_cfg,
            parent=self,
        )
        self._worker.backtest_ready.connect(self._on_backtest_ready)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_sync_backtest_clicked(self):
        self.mt5_operation_requested.emit()
        self._start_worker(mode="sync", run_type="backtest")

    def _on_load_backtest_clicked(self):
        self._start_worker(mode="load", run_type="backtest")

    def _on_ablation_clicked(self):
        self._start_worker(mode="load", run_type="ablation")

    def _on_walk_forward_clicked(self):
        self._start_worker(mode="load", run_type="walk_forward")

    def _on_backtest_ready(self, result_obj: object, report_text: str):
        self._set_controls_enabled(True)
        self.status_label.setStyleSheet("color: #2ecc71;")
        self.status_label.setText("Analysis completed successfully.")
        self.report_view.setPlainText(report_text)

        if isinstance(result_obj, BacktestResult):
            # Pass cumulative PnL to EquityCurve
            init_cap = result_obj.initial_capital
            pnl_values = [pt["equity"] - init_cap for pt in result_obj.equity_curve]
            self.equity_curve.set_data(pnl_values)
        else:
            self.equity_curve.clear()

    def _on_worker_error(self, message: str):
        self._set_controls_enabled(True)
        self.status_label.setStyleSheet("color: #e74c3c;")
        self.status_label.setText("Analysis failed. See report view.")
        self.report_view.setPlainText(f"ERROR: {message}")

    def _set_controls_enabled(self, enabled: bool):
        self.symbol_combo.setEnabled(enabled)
        self.bars_spin.setEnabled(enabled)
        self.risk_spin.setEnabled(enabled)
        self.spread_spin.setEnabled(enabled)
        self.slippage_spin.setEnabled(enabled)
        self.rollover_check.setEnabled(enabled)
        self.asian_breakout_check.setEnabled(enabled)
        self.spread_filter_check.setEnabled(enabled)
        self.regime_filter_check.setEnabled(enabled)
        self.scale_out_check.setEnabled(enabled)
        self.sync_backtest_btn.setEnabled(enabled)
        self.load_backtest_btn.setEnabled(enabled)
        self.ablation_btn.setEnabled(enabled)
        self.walk_forward_btn.setEnabled(enabled)

    def is_worker_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def wait_for_worker(self, timeout_ms: int = 3000):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(timeout_ms)

    def set_enabled(self, enabled: bool):
        self._set_controls_enabled(enabled)
