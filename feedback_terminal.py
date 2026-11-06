"""
Standalone NeuroTrade AI Feedback Terminal for Part 7.

This window trains and validates adaptive rule weights.
It does not send orders.
"""

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from gui.styles import DARK_STYLE
from gui.widgets.feedback_panel import FeedbackPanel


class FeedbackTerminalWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroTrade AI - Feedback Terminal")
        self.resize(1050, 760)

        self.feedback_panel = FeedbackPanel()
        self.feedback_panel.set_enabled(True)

        self.setCentralWidget(self.feedback_panel)

    def closeEvent(self, event):
        self.feedback_panel.wait_for_worker(3000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI Feedback Terminal")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = FeedbackTerminalWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())