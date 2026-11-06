from PyQt6.QtCore import QThread, pyqtSignal
import MetaTrader5 as mt5

from core.mt5_connector import MT5Connector
from core.database import DatabaseManager
from config import DEFAULT_SYMBOL


class StartupCheckWorker(QThread):
    """
    Background worker for Part 2 startup checks.

    This worker checks:
    - SQLite database connectivity
    - MT5 demo connection
    - Default symbol availability

    It does NOT place trades.
    """

    log = pyqtSignal(str)
    status = pyqtSignal(dict)
    finished_check = pyqtSignal()

    def run(self):
        result = {
            "db": "FAIL",
            "mt5": "FAIL",
            "account": "--",
            "server": "--",
            "mode": "--",
            "symbol": "--",
            "digits": "--",
            "volume_min": "--",
            "volume_max": "--",
        }

        self._check_database(result)
        self._check_mt5(result)

        self.status.emit(result)
        self.finished_check.emit()

    def _check_database(self, result):
        try:
            self.log.emit("Checking SQLite database...")

            db = DatabaseManager()
            if db.connect():
                result["db"] = "OK"
                self.log.emit("SQLite database check passed.")
                db.close()
            else:
                self.log.emit("SQLite database check failed.")

        except Exception as exc:
            result["db"] = "FAIL"
            self.log.emit(f"Database check error: {exc}")

    def _check_mt5(self, result):
        mt5_started = False

        try:
            self.log.emit("Checking MT5 connection...")

            if MT5Connector.initialize():
                mt5_started = True
                result["mt5"] = "OK"

                account_info = mt5.account_info()
                if account_info:
                    result["account"] = str(account_info.login)
                    result["server"] = account_info.server

                    mode = int(account_info.trade_mode)
                    demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)

                    result["mode"] = "DEMO" if mode == demo_mode else f"UNKNOWN({mode})"

                    self.log.emit(
                        f"MT5 demo check passed. "
                        f"Account: {account_info.login}, "
                        f"Server: {account_info.server}."
                    )
                else:
                    self.log.emit("MT5 connected, but account info was unavailable.")

                symbol_info = MT5Connector.get_symbol_info(DEFAULT_SYMBOL)
                if symbol_info:
                    result["symbol"] = symbol_info.name
                    result["digits"] = str(symbol_info.digits)
                    result["volume_min"] = str(symbol_info.volume_min)
                    result["volume_max"] = str(symbol_info.volume_max)

                    self.log.emit(f"Symbol check passed: {symbol_info.name}")
                else:
                    self.log.emit(f"Symbol check failed for {DEFAULT_SYMBOL}.")

            else:
                self.log.emit(
                    "MT5 check failed. "
                    "Ensure MT5 is running and logged into a DEMO account."
                )

        except Exception as exc:
            result["mt5"] = "FAIL"
            self.log.emit(f"MT5 check error: {exc}")

        finally:
            if mt5_started:
                MT5Connector.shutdown()
                self.log.emit("MT5 connection closed by startup check.")