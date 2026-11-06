import sys
import argparse
import logging

from PyQt6.QtWidgets import QApplication

from core.mt5_connector import MT5Connector
from core.database import DatabaseManager
from config import DEFAULT_SYMBOL
from gui.main_window import MainWindow
from gui.styles import DARK_STYLE


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def verify_part1() -> int:
    """
    Run the original Part 1 console verification.

    This is kept so Part 1 can still be verified without opening the GUI.
    """
    logging.info("Starting NeuroTrade AI - Part 1 Verification")

    db = DatabaseManager()
    if not db.connect():
        logging.critical("Failed to connect to database. Exiting.")
        return 1

    if not MT5Connector.initialize():
        logging.critical(
            "Failed to initialize MT5. "
            "Ensure terminal is running and logged into a DEMO account. Exiting."
        )
        db.close()
        return 1

    symbol_info = MT5Connector.get_symbol_info(DEFAULT_SYMBOL)
    if symbol_info:
        logging.info(f"Successfully loaded symbol: {symbol_info.name}")
        logging.info(
            f"Digits: {symbol_info.digits}, "
            f"Volume Min: {symbol_info.volume_min}, "
            f"Max: {symbol_info.volume_max}"
        )
    else:
        logging.warning(f"Could not load default symbol {DEFAULT_SYMBOL}.")

    MT5Connector.shutdown()
    db.close()

    logging.info("Part 1 verification completed successfully.")
    return 0


def run_gui() -> int:
    """
    Start the PyQt6 GUI application.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroTrade AI")
    app.setOrganizationName("NeuroTradeAI")
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()

    return app.exec()


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="NeuroTrade AI")
    parser.add_argument(
        "--verify-part1",
        action="store_true",
        help="Run the original Part 1 console verification and exit.",
    )

    args = parser.parse_args()

    if args.verify_part1:
        sys.exit(verify_part1())

    sys.exit(run_gui())


if __name__ == "__main__":
    main()