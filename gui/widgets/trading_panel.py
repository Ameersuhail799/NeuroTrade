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
    QFrame,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QPlainTextEdit,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from gui.trade_worker import TradeWorker
from core.trade_executor import DemoTradeExecutor
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
        self._updating_sizing = False
        self._context = {}

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
        order_layout.setVerticalSpacing(8)
        order_layout.setHorizontalSpacing(10)

        # Row 0: Symbol & Spend/Risk Budget
        order_layout.addWidget(QLabel("Symbol"), 0, 0)
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(ALLOWED_SYMBOLS)
        self.symbol_combo.setCurrentText(DEFAULT_SYMBOL)
        self.symbol_combo.currentIndexChanged.connect(self._on_symbol_changed)
        order_layout.addWidget(self.symbol_combo, 0, 1)

        order_layout.addWidget(QLabel("Spend / Risk ($)"), 0, 2)
        risk_input_layout = QHBoxLayout()
        risk_input_layout.setSpacing(4)
        self.risk_spin = QDoubleSpinBox()
        self.risk_spin.setRange(1.0, 100000.0)
        self.risk_spin.setDecimals(2)
        self.risk_spin.setSingleStep(5.0)
        self.risk_spin.setValue(30.0)
        self.risk_spin.setPrefix("$ ")
        self.risk_spin.setStyleSheet("font-weight: bold; color: #ff6b6b;")
        self.risk_spin.valueChanged.connect(self._on_risk_spin_changed)
        risk_input_layout.addWidget(self.risk_spin)

        self.preset_10_btn = QPushButton("$10")
        self.preset_10_btn.setFixedWidth(40)
        self.preset_10_btn.clicked.connect(lambda: self._apply_risk_preset(10.0))
        risk_input_layout.addWidget(self.preset_10_btn)

        self.preset_25_btn = QPushButton("$25")
        self.preset_25_btn.setFixedWidth(40)
        self.preset_25_btn.clicked.connect(lambda: self._apply_risk_preset(25.0))
        risk_input_layout.addWidget(self.preset_25_btn)

        self.preset_50_btn = QPushButton("$50")
        self.preset_50_btn.setFixedWidth(40)
        self.preset_50_btn.clicked.connect(lambda: self._apply_risk_preset(50.0))
        risk_input_layout.addWidget(self.preset_50_btn)

        self.preset_100_btn = QPushButton("$100")
        self.preset_100_btn.setFixedWidth(45)
        self.preset_100_btn.clicked.connect(lambda: self._apply_risk_preset(100.0))
        risk_input_layout.addWidget(self.preset_100_btn)

        self.preset_1pct_btn = QPushButton("1% Balance")
        self.preset_1pct_btn.clicked.connect(lambda: self._apply_balance_pct_preset(1.0))
        risk_input_layout.addWidget(self.preset_1pct_btn)

        order_layout.addLayout(risk_input_layout, 0, 3)

        # Row 1: Volume (Lots) & SL points
        order_layout.addWidget(QLabel("Volume (Lots)"), 1, 0)
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0.01, 100.0)
        self.volume_spin.setDecimals(2)
        self.volume_spin.setSingleStep(0.01)
        self.volume_spin.setValue(0.01)
        self.volume_spin.valueChanged.connect(self._on_volume_spin_changed)
        order_layout.addWidget(self.volume_spin, 1, 1)

        order_layout.addWidget(QLabel("SL points"), 1, 2)
        self.sl_spin = QSpinBox()
        self.sl_spin.setRange(0, 1_000_000)
        self.sl_spin.setValue(300)
        self.sl_spin.valueChanged.connect(self._on_sl_spin_changed)
        order_layout.addWidget(self.sl_spin, 1, 3)

        # Row 2: TP points & Target R/R buttons
        order_layout.addWidget(QLabel("TP points"), 2, 0)
        self.tp_spin = QSpinBox()
        self.tp_spin.setRange(0, 1_000_000)
        self.tp_spin.setValue(600)
        self.tp_spin.valueChanged.connect(self._on_tp_spin_changed)
        order_layout.addWidget(self.tp_spin, 2, 1)

        order_layout.addWidget(QLabel("Target R/R"), 2, 2)
        rr_layout = QHBoxLayout()
        self.rr_1_0_button = QPushButton("1.0R (Scalp)")
        self.rr_1_0_button.clicked.connect(lambda: self._set_rr_target(1.0))
        rr_layout.addWidget(self.rr_1_0_button)

        self.rr_1_5_button = QPushButton("1.5R (Standard)")
        self.rr_1_5_button.clicked.connect(lambda: self._set_rr_target(1.5))
        rr_layout.addWidget(self.rr_1_5_button)

        self.rr_2_0_button = QPushButton("2.0R (Runner)")
        self.rr_2_0_button.clicked.connect(lambda: self._set_rr_target(2.0))
        rr_layout.addWidget(self.rr_2_0_button)
        order_layout.addLayout(rr_layout, 2, 3)

        # Row 3: Live Financial Receipt Card
        self.preview_card = QFrame()
        self.preview_card.setStyleSheet(
            "QFrame { background-color: #1a1e28; border: 1px solid #2d3342; border-radius: 6px; padding: 4px; }"
        )
        card_layout = QGridLayout(self.preview_card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setHorizontalSpacing(16)
        card_layout.setVerticalSpacing(4)

        self.lbl_card_title = QLabel("📊 Live Order Cost & Risk Breakdown:")
        self.lbl_card_title.setStyleSheet("font-weight: bold; color: #8ab4f8; font-size: 11px;")
        card_layout.addWidget(self.lbl_card_title, 0, 0, 1, 3)

        self.lbl_card_risk = QLabel("🛑 Max Loss (SL): -$30.00 (-0.03%)")
        self.lbl_card_risk.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        card_layout.addWidget(self.lbl_card_risk, 1, 0)

        self.lbl_card_profit = QLabel("🎯 Target Profit (TP): +$45.00 (+0.04%) [1.5R]")
        self.lbl_card_profit.setStyleSheet("color: #51cf66; font-weight: bold;")
        card_layout.addWidget(self.lbl_card_profit, 1, 1)

        self.lbl_card_margin = QLabel("🔒 Margin Deposit: $75.30 (1:100 Lev)")
        self.lbl_card_margin.setStyleSheet("color: #74c0fc;")
        card_layout.addWidget(self.lbl_card_margin, 1, 2)

        self.lbl_card_value = QLabel("💼 Controlled Asset Value: $7,530.00")
        self.lbl_card_value.setStyleSheet("color: #ced4da;")
        card_layout.addWidget(self.lbl_card_value, 2, 0)

        self.lbl_card_outcome = QLabel("🏦 Projected Balance: Win: $101,798.11  |  Loss: $101,723.11")
        self.lbl_card_outcome.setStyleSheet("color: #ffd43b;")
        card_layout.addWidget(self.lbl_card_outcome, 2, 1, 1, 2)

        order_layout.addWidget(self.preview_card, 3, 0, 1, 4)

        # Row 4: Action buttons
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_context)
        order_layout.addWidget(self.refresh_button, 4, 0)

        self.open_long_button = QPushButton("Open Demo Long")
        self.open_long_button.clicked.connect(lambda: self._open_position("buy"))
        order_layout.addWidget(self.open_long_button, 4, 1)

        self.open_short_button = QPushButton("Open Demo Short")
        self.open_short_button.clicked.connect(lambda: self._open_position("sell"))
        order_layout.addWidget(self.open_short_button, 4, 2)

        self.close_button = QPushButton("Close Selected Position")
        self.close_button.clicked.connect(self._close_selected_position)
        order_layout.addWidget(self.close_button, 4, 3)

        root_layout.addWidget(order_group)

        # Open positions
        positions_group = QGroupBox("Open Positions")
        positions_layout = QVBoxLayout(positions_group)

        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(11)
        self.positions_table.setHorizontalHeaderLabels(
            [
                "Ticket",
                "Symbol",
                "Type",
                "Volume",
                "Margin ($)",
                "Max Risk ($)",
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

        # Positions action toolbar
        pos_toolbar = QHBoxLayout()
        self.be_button = QPushButton("Move Selected to Breakeven (BE)")
        self.be_button.setStyleSheet("font-weight: bold; color: #2ecc71;")
        self.be_button.clicked.connect(self._move_selected_to_breakeven)
        pos_toolbar.addWidget(self.be_button)

        self.close_pos_button = QPushButton("Close Selected Position")
        self.close_pos_button.clicked.connect(self._close_selected_position)
        pos_toolbar.addWidget(self.close_pos_button)

        self.auto_be_checkbox = QCheckBox("Auto-move to Breakeven at +1.0R profit")
        self.auto_be_checkbox.setChecked(True)
        pos_toolbar.addWidget(self.auto_be_checkbox)

        positions_layout.addLayout(pos_toolbar)
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
            self.risk_spin,
            self.preset_10_btn,
            self.preset_25_btn,
            self.preset_50_btn,
            self.preset_100_btn,
            self.preset_1pct_btn,
            self.volume_spin,
            self.sl_spin,
            self.tp_spin,
            self.rr_1_0_button,
            self.rr_1_5_button,
            self.rr_2_0_button,
            self.refresh_button,
            self.open_long_button,
            self.open_short_button,
            self.close_button,
            self.be_button,
            self.close_pos_button,
            self.auto_be_checkbox,
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

    def _set_rr_target(self, multiple: float):
        sl = max(10, int(self.sl_spin.value()))
        tp = max(10, int(round(sl * multiple)))
        self.tp_spin.setValue(tp)
        self._append_output(
            f"Target R/R set to {multiple:.1f}R: TP={tp} points (based on SL={sl} pts)."
        )
        self._update_preview_card()

    def _apply_risk_preset(self, dollars: float):
        self.risk_spin.setValue(float(dollars))

    def _apply_balance_pct_preset(self, pct: float):
        balance = 100000.0
        if self._context and "account" in self._context:
            balance = float(self._context["account"].get("balance", balance))
        self.risk_spin.setValue(round(balance * (pct / 100.0), 2))

    def _on_risk_spin_changed(self, target_risk: float):
        if self._updating_sizing or target_risk <= 0:
            return
        self._updating_sizing = True
        try:
            self._recalculate_from_risk(target_risk)
        finally:
            self._updating_sizing = False

    def _recalculate_from_risk(self, target_risk: float):
        symbol = self.symbol_combo.currentText().strip()
        sl_points = max(10, int(self.sl_spin.value()))
        tp_points = max(10, int(self.tp_spin.value()))

        try:
            executor = DemoTradeExecutor()
            preview = executor.calculate_order_preview(
                symbol=symbol,
                side="sell",
                volume=float(self.volume_spin.value()),
                sl_points=sl_points,
                tp_points=tp_points,
                target_risk=target_risk,
            )
            if preview and "volume" in preview:
                self.volume_spin.blockSignals(True)
                self.volume_spin.setValue(float(preview["volume"]))
                self.volume_spin.blockSignals(False)
                self._render_preview_card(preview)
        except Exception:
            pass

    def _on_volume_spin_changed(self, volume: float):
        if self._updating_sizing or volume <= 0:
            return
        self._updating_sizing = True
        try:
            self._recalculate_from_volume(volume)
        finally:
            self._updating_sizing = False

    def _recalculate_from_volume(self, volume: float):
        symbol = self.symbol_combo.currentText().strip()
        sl_points = max(10, int(self.sl_spin.value()))
        tp_points = max(10, int(self.tp_spin.value()))

        try:
            executor = DemoTradeExecutor()
            preview = executor.calculate_order_preview(
                symbol=symbol,
                side="sell",
                volume=volume,
                sl_points=sl_points,
                tp_points=tp_points,
            )
            if preview:
                if "risk_dollars" in preview and preview["risk_dollars"] > 0:
                    self.risk_spin.blockSignals(True)
                    self.risk_spin.setValue(float(preview["risk_dollars"]))
                    self.risk_spin.blockSignals(False)
                self._render_preview_card(preview)
        except Exception:
            pass

    def _on_sl_spin_changed(self, sl_points: int):
        if not self._updating_sizing:
            self._on_risk_spin_changed(self.risk_spin.value())

    def _on_tp_spin_changed(self, tp_points: int):
        if not self._updating_sizing:
            self._update_preview_card()

    def _on_symbol_changed(self, idx: int):
        if not self._updating_sizing:
            self._update_preview_card()

    def _update_preview_card(self):
        try:
            symbol = self.symbol_combo.currentText().strip()
            volume = float(self.volume_spin.value())
            sl_points = max(0, int(self.sl_spin.value()))
            tp_points = max(0, int(self.tp_spin.value()))

            executor = DemoTradeExecutor()
            preview = executor.calculate_order_preview(
                symbol=symbol,
                side="sell",
                volume=volume,
                sl_points=sl_points,
                tp_points=tp_points,
            )
            if preview:
                self._render_preview_card(preview)
        except Exception:
            pass

    def _render_preview_card(self, preview: dict):
        if not preview:
            return
        risk_d = float(preview.get("risk_dollars", 0.0))
        risk_pct = float(preview.get("risk_pct", 0.0))
        profit_d = float(preview.get("profit_dollars", 0.0))
        profit_pct = float(preview.get("profit_pct", 0.0))
        margin = float(preview.get("margin", 0.0))
        leverage = int(preview.get("leverage", 100))
        notional = float(preview.get("notional", 0.0))
        b_win = float(preview.get("balance_if_win", 0.0))
        b_loss = float(preview.get("balance_if_loss", 0.0))

        self.lbl_card_risk.setText(f"🛑 Max Loss (SL): -${risk_d:.2f} (-{risk_pct:.2f}%)")
        self.lbl_card_profit.setText(f"🎯 Target Profit (TP): +${profit_d:.2f} (+{profit_pct:.2f}%)")
        self.lbl_card_margin.setText(f"🔒 Margin Deposit: ${margin:.2f} (1:{leverage} Lev)")
        self.lbl_card_value.setText(f"💼 Controlled Asset Value: ${notional:,.2f}")
        self.lbl_card_outcome.setText(f"🏦 Projected Balance: Win: ${b_win:,.2f}  |  Loss: ${b_loss:,.2f}")

    def _move_selected_to_breakeven(self):
        if not self._prepare_mt5_action():
            return

        selected_rows = self.positions_table.selectionModel().selectedRows()
        if not selected_rows:
            self._append_output("Select an open position row from the table first.")
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

        self._append_output(f"Submitting Breakeven request for position ticket #{ticket}...")
        self._start_worker("breakeven", {"ticket": int(ticket)})

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

        self._context = context
        self._update_volume_spin(contract)
        self._populate_positions(positions)
        self._update_preview_card()

        self._append_output(
            f"Refresh complete. Open positions: {len(positions)}."
        )

        self._check_auto_breakeven(positions)
        self._set_controls_enabled(self._enabled)

    def _check_auto_breakeven(self, positions: list):
        if not self.auto_be_checkbox.isChecked():
            return

        for pos in positions:
            ticket = pos.get("ticket")
            pos_type = str(pos.get("type", "")).upper()
            open_p = float(pos.get("open_price", 0.0))
            sl_p = float(pos.get("sl", 0.0))
            curr_p = float(pos.get("current_price", open_p))

            if pos_type == "BUY":
                risk_dist = open_p - sl_p
                # Only if SL is strictly below entry (not yet at or above BE)
                if 0 < sl_p < open_p and risk_dist > 0:
                    profit_dist = curr_p - open_p
                    if profit_dist >= risk_dist and not self.is_worker_running():
                        self._append_output(
                            f"Auto-BE Watchdog: Position #{ticket} (BUY) reached +1.0R "
                            f"(+{profit_dist:.5f} >= {risk_dist:.5f} risk). Moving SL to Breakeven..."
                        )
                        self._start_worker("breakeven", {"ticket": int(ticket)})
                        break
            elif pos_type == "SELL":
                risk_dist = sl_p - open_p
                # Only if SL is strictly above entry (not yet at or below BE)
                if sl_p > open_p and risk_dist > 0:
                    profit_dist = open_p - curr_p
                    if profit_dist >= risk_dist and not self.is_worker_running():
                        self._append_output(
                            f"Auto-BE Watchdog: Position #{ticket} (SELL) reached +1.0R "
                            f"(+{profit_dist:.5f} >= {risk_dist:.5f} risk). Moving SL to Breakeven..."
                        )
                        self._start_worker("breakeven", {"ticket": int(ticket)})
                        break

    def prefill_order_ticket(self, data: dict):
        """
        Pre-fill order controls from a signal setup for manual review and demo execution.
        Strictly no automated order placement.
        """
        symbol = data.get("symbol")
        if symbol:
            idx = self.symbol_combo.findText(symbol)
            if idx >= 0:
                self.symbol_combo.setCurrentIndex(idx)

        sl_points = data.get("sl_points")
        if sl_points is not None:
            self.sl_spin.setValue(max(0, int(sl_points)))

        tp_points = data.get("tp_points")
        if tp_points is not None:
            self.tp_spin.setValue(max(0, int(tp_points)))

        volume = data.get("volume")
        if volume is not None and float(volume) > 0.0:
            self.volume_spin.setValue(float(volume))

        side = str(data.get("side", "")).upper()
        self._update_preview_card()
        self._append_output(
            f"Pre-filled ticket from signal: {symbol} {side} "
            f"| SL={self.sl_spin.value()} pts | TP={self.tp_spin.value()} pts | Vol={self.volume_spin.value():.2f}. "
            f"Carefully review parameters and click 'Open Demo {side.capitalize() if side else 'Position'}' to manually submit."
        )

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
                row, 4, QTableWidgetItem(f"${float(position.get('margin', 0.0)):.2f}")
            )
            max_r = float(position.get("max_risk", 0.0))
            self.positions_table.setItem(
                row, 5, QTableWidgetItem(f"-${max_r:.2f}" if max_r > 0 else "$0.00")
            )
            self.positions_table.setItem(
                row,
                6,
                QTableWidgetItem(f"{float(position.get('open_price', 0.0)):.5f}"),
            )
            self.positions_table.setItem(
                row, 7, QTableWidgetItem(f"{float(position.get('sl', 0.0)):.5f}")
            )
            self.positions_table.setItem(
                row, 8, QTableWidgetItem(f"{float(position.get('tp', 0.0)):.5f}")
            )
            self.positions_table.setItem(
                row, 9, QTableWidgetItem(f"{float(position.get('profit', 0.0)):.2f}")
            )
            self.positions_table.setItem(
                row, 10, QTableWidgetItem(str(position.get("time", "")))
            )

        self.positions_table.resizeColumnsToContents()