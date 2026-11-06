"""
Standalone NeuroTrade AI Trading Terminal for Part 6.

This is a manual DEMO-only trade executor.
It does not modify the main NeuroTrade AI window.
"""

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from gui.styles import DARK_STYLE
from gui.widgets.trading_panel import TradingPanel


class TradingTerminalWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI - Demo Trade Executor")
        self.resize(1050, 720)

        self.trading_panel = TradingPanel()
        self.trading_panel.set_enabled(True)

        self.setCentralWidget(self.trading_panel)

    def closeEvent(self, event):
        self.trading_panel.wait_for_worker(3000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI Trading Terminal")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = TradingTerminalWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())