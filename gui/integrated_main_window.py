"""
Integrated NeuroTrade AI main window for Part 10.

This subclass reuses the existing Part 2-5 MainWindow and adds:
- Trading panel with local execution persistence
- Feedback panel
- Performance panel
- Persistent Signal History panel

No previous file is rewritten.
"""

from gui.main_window import MainWindow
from gui.widgets.persistent_trading_panel import PersistentTradingPanel
from gui.widgets.feedback_panel import FeedbackPanel
from gui.widgets.performance_panel import PerformancePanel
from gui.widgets.persistent_signal_panel import PersistentSignalHistoryPanel


class IntegratedMainWindow(MainWindow):
    """
    Integrated terminal combining all completed modules.
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI - Integrated Terminal")
        self.resize(1350, 860)

        # Part 6 + Part 10 persistence
        self.trading_panel = PersistentTradingPanel()

        # Part 7
        self.feedback_panel = FeedbackPanel()

        # Part 8
        self.performance_panel = PerformancePanel()

        # Part 9 + Part 10 persistence
        self.signal_panel = PersistentSignalHistoryPanel()

        # Add integrated tabs.
        self.tabs.addTab(self.trading_panel, "Trading")
        self.tabs.addTab(self.feedback_panel, "Feedback")
        self.tabs.addTab(self.performance_panel, "Performance")
        self.tabs.addTab(self.signal_panel, "Signals")

        # MT5 coordination for the trading panel.
        self.trading_panel.set_mt5_guard(self._mt5_guard_allowed)
        self.trading_panel.mt5_operation_requested.connect(
            self._pause_live_chart_for_trading
        )

        # Feedback panel also performs MT5 work.
        self.feedback_panel.mt5_operation_requested.connect(
            self._pause_live_chart_for_trading
        )

        # Performance panel performs MT5 work.
        self.performance_panel.mt5_operation_requested.connect(
            self._pause_live_chart_for_trading
        )

        # Signal panel performs MT5 work when syncing live data.
        self.signal_panel.mt5_operation_requested.connect(
            self._pause_live_chart_for_trading
        )

        # Pause live chart when entering MT5-heavy tabs.
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)

        if widget in (
            self.trading_panel,
            self.feedback_panel,
            self.performance_panel,
            self.signal_panel,
        ):
            self._pause_live_chart_for_trading()

    def _mt5_guard_allowed(self) -> bool:
        """
        Prevent concurrent MT5 operations where supported.
        """
        if self._worker is not None and self._worker.isRunning():
            return False

        if self._chart_worker is not None and self._chart_worker.isRunning():
            return False

        if self._data_worker is not None and self._data_worker.isRunning():
            return False

        if self.trading_panel.is_worker_running():
            return False

        if self.feedback_panel.is_worker_running():
            return False

        if self.performance_panel.is_worker_running():
            return False

        if self.signal_panel.is_worker_running():
            return False

        return True

    def _pause_live_chart_for_trading(self):
        """
        Pause the Part 3 live chart to reduce MT5 concurrency issues.
        """
        try:
            if self.live_chart_checkbox.isChecked():
                self.live_chart_checkbox.blockSignals(True)
                self.live_chart_checkbox.setChecked(False)
                self.live_chart_checkbox.blockSignals(False)

                self._chart_timer.stop()

                self.append_log(
                    "Live chart paused for integrated MT5 operations."
                )
        except Exception:
            # If the live chart objects are unavailable for any reason,
            # do not block the user's current operation.
            pass

    def _on_checks_finished(self):
        """
        Enable integrated panels after Part 2 startup checks complete.
        """
        super()._on_checks_finished()

        self.trading_panel.set_enabled(True)
        self.feedback_panel.set_enabled(True)
        self.performance_panel.set_enabled(True)
        self.signal_panel.set_enabled(True)

    def closeEvent(self, event):
        """
        Wait for integrated workers and close persistent stores.
        """
        self.trading_panel.wait_for_worker(3000)
        self.feedback_panel.wait_for_worker(3000)
        self.performance_panel.wait_for_worker(3000)
        self.signal_panel.wait_for_worker(3000)

        self.signal_panel.close_store()

        super().closeEvent(event)