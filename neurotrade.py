"""
NeuroTrade AI integrated application entrypoint for Part 10.

This is the recommended launcher going forward.
It does not modify the original main.py entrypoint.
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication

from gui.styles import DARK_STYLE
from gui.integrated_main_window import IntegratedMainWindow


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def main() -> int:
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = IntegratedMainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())