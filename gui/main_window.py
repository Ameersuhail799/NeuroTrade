from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QLabel,
    QPlainTextEdit,
    QGroupBox,
    QGridLayout,
    QTextBrowser,
    QMessageBox,
    QComboBox,
    QPushButton,
    QCheckBox,
    QHBoxLayout,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime

from gui.workers import StartupCheckWorker
from gui.widgets.candlestick_chart import CandlestickChart
from gui.widgets.decision_panel import DecisionPanel
from gui.chart_data_worker import ChartDataWorker
from gui.data_worker import DataWorker
from core.indicators import IndicatorEngine
from config import DEFAULT_SYMBOL, ALLOWED_SYMBOLS, ALLOWED_TIMEFRAMES


class MainWindow(QMainWindow):
    """Main application window for NeuroTrade AI."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI")
        self.resize(1150, 720)

        self._worker = None
        self._chart_worker = None
        self._data_worker = None
        self._initial_chart_requested = False
        self._chart_request_source = "manual"
        self._indicator_df = None
        self._indicator_meta = None

        self.decision_panel = DecisionPanel()

        self._chart_timer = QTimer(self)
        self._chart_timer.setInterval(10000)
        self._chart_timer.timeout.connect(self._on_chart_timer)

        self._build_ui()
        self._build_menu()
        self._build_status_bar()

        self.append_log("GUI initialized.")
        self.start_system_checks()

    def _build_ui(self):
        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_dashboard_tab(), "Dashboard")
        self.tabs.addTab(self._create_chart_tab(), "Chart")
        self.tabs.addTab(self._create_data_tab(), "Data")
        self.tabs.addTab(self._create_decision_tab(), "Decision")
        self.tabs.addTab(self._create_logs_tab(), "Logs")
        self.tabs.addTab(self._create_about_tab(), "About")

        root_layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)

    def _create_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        status_group = QGroupBox("System Status")
        status_grid = QGridLayout(status_group)
        status_grid.setHorizontalSpacing(18)
        status_grid.setVerticalSpacing(8)

        self.db_value = self._make_value_label("Checking...")
        self.mt5_value = self._make_value_label("Checking...")
        self.account_value = self._make_value_label("--")
        self.server_value = self._make_value_label("--")
        self.mode_value = self._make_value_label("--")
        self.symbol_value = self._make_value_label("Checking...")
        self.digits_value = self._make_value_label("--")
        self.volume_min_value = self._make_value_label("--")
        self.volume_max_value = self._make_value_label("--")

        rows = [
            ("SQLite Database:", self.db_value),
            ("MT5 Connection:", self.mt5_value),
            ("Account:", self.account_value),
            ("Server:", self.server_value),
            ("Account Mode:", self.mode_value),
            ("Symbol:", self.symbol_value),
            ("Digits:", self.digits_value),
            ("Volume Min:", self.volume_min_value),
            ("Volume Max:", self.volume_max_value),
        ]

        for row, (title, value_label) in enumerate(rows):
            title_label = QLabel(title)
            title_label.setStyleSheet("color: #9aa0a6;")
            status_grid.addWidget(title_label, row, 0)
            status_grid.addWidget(value_label, row, 1)

        status_grid.setColumnStretch(1, 1)
        layout.addWidget(status_group)

        trading_group = QGroupBox("Trading")
        trading_layout = QVBoxLayout(trading_group)
        trading_label = QLabel("Trading controls will be added in a future part.")
        trading_label.setStyleSheet("color: #9aa0a6;")
        trading_layout.addWidget(trading_label)
        layout.addWidget(trading_group)

        chart_group = QGroupBox("Chart")
        chart_layout = QVBoxLayout(chart_group)
        chart_label = QLabel("The live candlestick chart is available in the Chart tab.")
        chart_label.setStyleSheet("color: #9aa0a6;")
        chart_layout.addWidget(chart_label)
        layout.addWidget(chart_group)

        layout.addStretch()
        return tab

    def _create_chart_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        controls_layout.addWidget(QLabel("Symbol"))
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.symbol_combo.setCurrentText(DEFAULT_SYMBOL)
        self.symbol_combo.setEnabled(False)
        controls_layout.addWidget(self.symbol_combo)

        controls_layout.addWidget(QLabel("Timeframe"))
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(ALLOWED_TIMEFRAMES)
        self.timeframe_combo.setCurrentText("1m")
        self.timeframe_combo.setEnabled(False)
        controls_layout.addWidget(self.timeframe_combo)

        self.load_chart_button = QPushButton("Load Chart")
        self.load_chart_button.setEnabled(False)
        self.load_chart_button.clicked.connect(
            lambda: self.request_chart_data("manual")
        )
        controls_layout.addWidget(self.load_chart_button)

        self.live_chart_checkbox = QCheckBox("Live")
        self.live_chart_checkbox.setChecked(True)
        self.live_chart_checkbox.setEnabled(False)
        self.live_chart_checkbox.toggled.connect(self._on_live_chart_toggled)
        controls_layout.addWidget(self.live_chart_checkbox)

        controls_layout.addStretch()

        self.chart_status_label = QLabel("Chart not loaded.")
        self.chart_status_label.setStyleSheet("color: #9aa0a6;")
        controls_layout.addWidget(self.chart_status_label)

        self.chart_widget = CandlestickChart()

        layout.addLayout(controls_layout)
        layout.addWidget(self.chart_widget, stretch=1)

        return tab

    def _create_data_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        history_group = QGroupBox("Candle History")
        history_layout = QGridLayout(history_group)

        history_layout.addWidget(QLabel("Symbol"), 0, 0)
        self.data_symbol_combo = QComboBox()
        self.data_symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.data_symbol_combo.setCurrentText(DEFAULT_SYMBOL)
        self.data_symbol_combo.setEnabled(False)
        history_layout.addWidget(self.data_symbol_combo, 0, 1)

        history_layout.addWidget(QLabel("Timeframe"), 0, 2)
        self.data_timeframe_combo = QComboBox()
        self.data_timeframe_combo.addItems(ALLOWED_TIMEFRAMES)
        self.data_timeframe_combo.setCurrentText("1m")
        self.data_timeframe_combo.setEnabled(False)
        history_layout.addWidget(self.data_timeframe_combo, 0, 3)

        history_layout.addWidget(QLabel("Bars"), 1, 0)
        self.bars_spin = QSpinBox()
        self.bars_spin.setRange(50, 5000)
        self.bars_spin.setSingleStep(50)
        self.bars_spin.setValue(500)
        self.bars_spin.setEnabled(False)
        history_layout.addWidget(self.bars_spin, 1, 1)

        self.sync_button = QPushButton("Sync MT5 History")
        self.sync_button.setEnabled(False)
        self.sync_button.clicked.connect(lambda: self.request_data_work("sync"))
        history_layout.addWidget(self.sync_button, 1, 2)

        self.load_db_button = QPushButton("Load From SQLite")
        self.load_db_button.setEnabled(False)
        self.load_db_button.clicked.connect(lambda: self.request_data_work("load"))
        history_layout.addWidget(self.load_db_button, 1, 3)

        self.data_status_label = QLabel("No history loaded yet.")
        self.data_status_label.setStyleSheet("color: #9aa0a6;")
        history_layout.addWidget(self.data_status_label, 2, 0, 1, 4)

        layout.addWidget(history_group)

        overlay_group = QGroupBox("Chart Overlays")
        overlay_layout = QHBoxLayout(overlay_group)

        self.sma_checkbox = QCheckBox("SMA 20")
        self.sma_checkbox.setChecked(True)
        self.ema_checkbox = QCheckBox("EMA 50")
        self.ema_checkbox.setChecked(True)
        self.bb_checkbox = QCheckBox("Bollinger 20 / 2")
        self.bb_checkbox.setChecked(False)

        for checkbox in (self.sma_checkbox, self.ema_checkbox, self.bb_checkbox):
            checkbox.setEnabled(False)
            checkbox.toggled.connect(self._apply_chart_overlays)
            overlay_layout.addWidget(checkbox)

        overlay_layout.addStretch()
        layout.addWidget(overlay_group)

        readout_group = QGroupBox("Latest Candle Indicators")
        readout_layout = QVBoxLayout(readout_group)

        self.indicator_output = QPlainTextEdit()
        self.indicator_output.setReadOnly(True)
        self.indicator_output.setMaximumBlockCount(20)
        self.indicator_output.setPlainText("No indicator data loaded.")
        readout_layout.addWidget(self.indicator_output)

        layout.addWidget(readout_group, stretch=1)

        note = QLabel(
            "Sync pauses live chart updates so overlays stay visible. "
            "Re-enable Live on the Chart tab to resume plain candle refresh."
        )
        note.setStyleSheet("color: #9aa0a6;")
        note.setWordWrap(True)
        layout.addWidget(note)

        return tab

    def _create_decision_tab(self):
        return self.decision_panel

    def _create_logs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(10000)

        layout.addWidget(self.log_text)
        return tab

    def _create_about_tab(self):
        tab = QTextBrowser()
        tab.setOpenExternalLinks(False)
        tab.setHtml(
            "<h2>NeuroTrade AI</h2>"
            "<p>Personal-use self-learning trading system.</p>"
            "<p>Part 5 adds a rule-based decision engine. "
            "No trading operations are executed and no orders are sent.</p>"
            "<p>DEMO only.</p>"
        )
        return tab

    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Exit", self.close)

        help_menu = menu_bar.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _build_status_bar(self):
        status_bar = self.statusBar()
        status_bar.showMessage("Starting...")

        self.db_status_label = QLabel("DB: Checking")
        self.mt5_status_label = QLabel("MT5: Checking")
        self.symbol_status_label = QLabel(f"Symbol: {DEFAULT_SYMBOL}")

        for widget in (
            self.db_status_label,
            self.mt5_status_label,
            self.symbol_status_label,
        ):
            widget.setContentsMargins(8, 0, 8, 0)
            status_bar.addPermanentWidget(widget)

    def _make_value_label(self, text: str):
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("color: #d5d8dc; font-weight: bold;")
        return label

    def _set_label_state(self, label, text: str, state: str):
        colors = {
            "ok": "#2ecc71",
            "fail": "#e74c3c",
            "checking": "#f1c40f",
            "neutral": "#d5d8dc",
        }
        color = colors.get(state, colors["neutral"])
        label.setText(text)
        label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def start_system_checks(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self._set_checking_state()
        self.append_log("Starting background system checks...")

        self._worker = StartupCheckWorker()
        self._worker.log.connect(self.append_log)
        self._worker.status.connect(self._on_system_status)
        self._worker.finished_check.connect(self._on_checks_finished)
        self._worker.start()

    def _set_checking_state(self):
        self._set_label_state(self.db_value, "Checking...", "checking")
        self._set_label_state(self.mt5_value, "Checking...", "checking")
        self._set_label_state(self.account_value, "--", "neutral")
        self._set_label_state(self.server_value, "--", "neutral")
        self._set_label_state(self.mode_value, "--", "neutral")
        self._set_label_state(self.symbol_value, "Checking...", "checking")
        self._set_label_state(self.digits_value, "--", "neutral")
        self._set_label_state(self.volume_min_value, "--", "neutral")
        self._set_label_state(self.volume_max_value, "--", "neutral")

        self._set_label_state(self.db_status_label, "DB: Checking", "checking")
        self._set_label_state(self.mt5_status_label, "MT5: Checking", "checking")
        self._set_label_state(
            self.symbol_status_label, f"Symbol: {DEFAULT_SYMBOL}", "checking"
        )

    def _on_system_status(self, status):
        db_status = status.get("db", "UNKNOWN")
        mt5_status = status.get("mt5", "UNKNOWN")
        account = status.get("account", "--")
        server = status.get("server", "--")
        mode = status.get("mode", "--")
        symbol = status.get("symbol", "--")
        digits = status.get("digits", "--")
        volume_min = status.get("volume_min", "--")
        volume_max = status.get("volume_max", "--")

        db_state = "ok" if db_status == "OK" else "fail"
        mt5_state = "ok" if mt5_status == "OK" else "fail"
        symbol_state = "ok" if symbol not in ("", "--", None) else "fail"

        self._set_label_state(self.db_value, db_status, db_state)
        self._set_label_state(self.mt5_value, mt5_status, mt5_state)
        self._set_label_state(self.account_value, account, "neutral")
        self._set_label_state(self.server_value, server, "neutral")
        self._set_label_state(self.mode_value, mode, "neutral")
        self._set_label_state(self.symbol_value, symbol, symbol_state)
        self._set_label_state(self.digits_value, digits, "neutral")
        self._set_label_state(self.volume_min_value, volume_min, "neutral")
        self._set_label_state(self.volume_max_value, volume_max, "neutral")

        self._set_label_state(self.db_status_label, f"DB: {db_status}", db_state)
        self._set_label_state(self.mt5_status_label, f"MT5: {mt5_status}", mt5_state)
        self._set_label_state(self.symbol_status_label, f"Symbol: {symbol}", symbol_state)

    def _on_checks_finished(self):
        self.append_log("System checks finished.")
        self.statusBar().showMessage("Ready", 5000)

        self._enable_chart_controls()
        self._enable_data_controls(True)

        if not self._initial_chart_requested:
            self._initial_chart_requested = True
            self.request_chart_data("initial")

            if self.live_chart_checkbox.isChecked():
                self._chart_timer.start()

    def _enable_chart_controls(self):
        self.symbol_combo.setEnabled(True)
        self.timeframe_combo.setEnabled(True)
        self.load_chart_button.setEnabled(True)
        self.live_chart_checkbox.setEnabled(True)

    def _enable_data_controls(self, enabled: bool):
        self.data_symbol_combo.setEnabled(enabled)
        self.data_timeframe_combo.setEnabled(enabled)
        self.bars_spin.setEnabled(enabled)
        self.sync_button.setEnabled(enabled)
        self.load_db_button.setEnabled(enabled)

        overlay_enabled = enabled and self._indicator_df is not None
        self.sma_checkbox.setEnabled(overlay_enabled)
        self.ema_checkbox.setEnabled(overlay_enabled)
        self.bb_checkbox.setEnabled(overlay_enabled)

    def request_chart_data(self, source: str = "manual"):
        if self._chart_worker is not None and self._chart_worker.isRunning():
            if source == "manual":
                self.append_log("Chart refresh already in progress.")
            return

        if self._data_worker is not None and self._data_worker.isRunning():
            if source == "manual":
                self.append_log("Data sync in progress. Please wait.")
            return

        self._chart_request_source = source

        symbol = self.symbol_combo.currentText().strip()
        timeframe = self.timeframe_combo.currentText().strip()
        verbose = source != "timer"

        self.chart_status_label.setStyleSheet("color: #f1c40f;")
        self.chart_status_label.setText(f"Loading {symbol} {timeframe}...")

        if verbose:
            self.append_log(f"Requesting chart data: {symbol} {timeframe}")

        self._chart_worker = ChartDataWorker(
            symbol=symbol,
            timeframe=timeframe,
            limit=300,
            verbose=verbose,
        )

        self._chart_worker.log.connect(self.append_log)
        self._chart_worker.data_ready.connect(self._on_chart_data_ready)
        self._chart_worker.error.connect(self._on_chart_error)
        self._chart_worker.start()

    def _on_chart_data_ready(self, data, meta):
        # Plain chart refresh replaces any previous indicator overlay view.
        self._indicator_df = None
        self._indicator_meta = None
        self.chart_widget.set_overlays([])
        self.chart_widget.set_data(data, meta)

        status_text = (
            f"{meta.get('symbol', '')} "
            f"{meta.get('timeframe', '')} | "
            f"{meta.get('rows', 0)} candles | "
            f"Updated {meta.get('updated_at', '')}"
        )

        self.chart_status_label.setStyleSheet("color: #2ecc71;")
        self.chart_status_label.setText(status_text)

        if self._chart_request_source != "timer":
            self.append_log(f"Chart data ready: {status_text}")

    def _on_chart_error(self, message: str):
        self.chart_status_label.setStyleSheet("color: #e74c3c;")
        self.chart_status_label.setText("Chart error. Check Logs.")
        self.append_log(message)

    def _on_live_chart_toggled(self, checked: bool):
        if checked:
            self._indicator_df = None
            self._indicator_meta = None
            self.chart_widget.set_overlays([])
            self.append_log("Live chart updates enabled. Indicator overlays cleared.")
            self._chart_timer.start()
            self.request_chart_data("manual")
        else:
            self._chart_timer.stop()
            self.append_log("Live chart updates disabled.")

    def _on_chart_timer(self):
        if not self.live_chart_checkbox.isChecked():
            return

        if self._chart_worker is not None and self._chart_worker.isRunning():
            return

        self.request_chart_data("timer")

    def request_data_work(self, mode: str):
        if self._data_worker is not None and self._data_worker.isRunning():
            self.append_log("Data operation already in progress.")
            return

        if self._chart_worker is not None and self._chart_worker.isRunning():
            self.append_log("Chart refresh in progress. Please wait.")
            return

        symbol = self.data_symbol_combo.currentText().strip()
        timeframe = self.data_timeframe_combo.currentText().strip()
        limit = int(self.bars_spin.value())

        self._enable_data_controls(False)
        self.data_status_label.setStyleSheet("color: #f1c40f;")
        self.data_status_label.setText(f"Processing {symbol} {timeframe}...")

        self._data_worker = DataWorker(
            symbol=symbol,
            timeframe=timeframe,
            mode=mode,
            limit=limit,
        )
        self._data_worker.log.connect(self.append_log)
        self._data_worker.data_ready.connect(self._on_data_ready)
        self._data_worker.error.connect(self._on_data_error)
        self._data_worker.start()

    def _on_data_ready(self, data, meta):
        self._indicator_df = data
        self._indicator_meta = meta

        self.indicator_output.setPlainText(IndicatorEngine.format_summary(data))

        # Show the loaded history on the Chart tab with overlays.
        self.chart_widget.set_data(data, meta)
        self._apply_chart_overlays()

        # Provide the same indicator-enriched data to the Decision tab.
        self.decision_panel.set_data(data, meta)

        chart_status = (
            f"{meta.get('symbol', '')} {meta.get('timeframe', '')} | "
            f"{meta.get('rows', 0)} candles | source: {meta.get('source', '')}"
        )
        self.chart_status_label.setStyleSheet("color: #2ecc71;")
        self.chart_status_label.setText(chart_status)

        self.data_status_label.setStyleSheet("color: #2ecc71;")
        self.data_status_label.setText(
            f"{meta.get('source', '')} | {meta.get('rows', 0)} candles | "
            f"{meta.get('stored_rows', 0)} stored in SQLite | "
            f"last candle {meta.get('last_time', '')}"
        )

        # Prevent the live timer from immediately replacing overlays.
        if self.live_chart_checkbox.isChecked():
            self.live_chart_checkbox.blockSignals(True)
            self.live_chart_checkbox.setChecked(False)
            self.live_chart_checkbox.blockSignals(False)
            self._chart_timer.stop()
            self.append_log("Live chart paused to preserve indicator overlays.")

        self._enable_data_controls(True)

    def _on_data_error(self, message: str):
        self.data_status_label.setStyleSheet("color: #e74c3c;")
        self.data_status_label.setText("Data operation failed. Check Logs.")
        self.append_log(message)
        self._enable_data_controls(True)

    def _apply_chart_overlays(self):
        if self._indicator_df is None:
            return

        df = self._indicator_df
        overlays = []

        if self.sma_checkbox.isChecked():
            overlays.append(
                {"name": "SMA 20", "color": "#f1c40f", "values": df["sma_20"].tolist()}
            )

        if self.ema_checkbox.isChecked():
            overlays.append(
                {"name": "EMA 50", "color": "#5dade2", "values": df["ema_50"].tolist()}
            )

        if self.bb_checkbox.isChecked():
            for column, color in (
                ("bb_upper", "#af7ac5"),
                ("bb_middle", "#7f8c8d"),
                ("bb_lower", "#af7ac5"),
            ):
                overlays.append(
                    {"name": column, "color": color, "values": df[column].tolist()}
                )

        self.chart_widget.set_overlays(overlays)

    def append_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.appendPlainText(f"[{timestamp}] {message}")

    def _show_about(self):
        QMessageBox.about(
            self,
            "NeuroTrade AI",
            "<h3>NeuroTrade AI</h3>"
            "<p>Personal-use self-learning trading system.</p>"
            "<p>Part 5: rule-based decision engine. "
            "No trading operations are executed and no orders are sent.</p>"
            "<p>DEMO only.</p>",
        )

    def closeEvent(self, event):
        self._chart_timer.stop()

        self.decision_panel.wait_for_worker(3000)

        if self._data_worker is not None and self._data_worker.isRunning():
            self._data_worker.wait(3000)

        if self._chart_worker is not None and self._chart_worker.isRunning():
            self._chart_worker.wait(3000)

        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)

        event.accept()