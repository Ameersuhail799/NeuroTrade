"""
Standalone NeuroTrade AI Signal Terminal for Part 9.

Generates real decision records from candle data and provides
session history plus copy-to-clipboard actions.

No orders are sent.
"""

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from gui.styles import DARK_STYLE
from gui.widgets.signal_history_panel import SignalHistoryPanel


class SignalTerminalWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI - Signal Terminal")
        self.resize(1150, 780)

        self.signal_panel = SignalHistoryPanel()
        self.signal_panel.set_enabled(True)

        self.setCentralWidget(self.signal_panel)

    def closeEvent(self, event):
        self.signal_panel.wait_for_worker(3000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI Signal Terminal")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = SignalTerminalWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())