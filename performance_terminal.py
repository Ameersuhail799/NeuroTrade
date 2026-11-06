"""
Standalone NeuroTrade AI Performance Terminal for Part 8.

This window shows real demo-account performance metrics from MT5 history.
It does not send orders.
"""

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from gui.styles import DARK_STYLE
from gui.widgets.performance_panel import PerformancePanel


class PerformanceTerminalWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI - Performance Dashboard")
        self.resize(1100, 760)

        self.performance_panel = PerformancePanel()
        self.performance_panel.set_enabled(True)

        self.setCentralWidget(self.performance_panel)

    def closeEvent(self, event):
        self.performance_panel.wait_for_worker(3000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI Performance Terminal")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = PerformanceTerminalWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())