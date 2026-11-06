"""
Background worker for Part 8 Performance Dashboard.

Loads real MT5 demo account history and calculates performance metrics.
No orders are sent.
"""

from datetime import datetime, timedelta

import MetaTrader5 as mt5
from PyQt6.QtCore import QThread, pyqtSignal

from core.mt5_connector import MT5Connector
from core.performance_engine import (
    build_closed_trades,
    calculate_metrics,
)


class PerformanceWorker(QThread):
    """
    Refreshes performance metrics from MT5 history.
    """

    report_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, symbol_filter: str, days: int, parent=None):
        super().__init__(parent)

        self.symbol_filter = str(symbol_filter or "ALL")
        self.days = max(1, int(days))

    def run(self):
        mt5_started = False

        try:
            if not MT5Connector.initialize():
                self.error.emit(
                    "MT5 initialization failed. "
                    "Ensure MT5 is running and logged into a DEMO account."
                )
                return

            mt5_started = True

            account = mt5.account_info()
            if not account:
                self.error.emit("Could not read MT5 account info.")
                return

            account_data = {
                "login": int(account.login),
                "server": str(account.server),
                "currency": str(account.currency),
            }

            end_time = datetime.now() + timedelta(days=1)
            start_time = datetime.now() - timedelta(days=self.days)

            deals = mt5.history_deals_get(start_time, end_time)

            if deals is None:
                self.error.emit(
                    f"MT5 history_deals_get failed. MT5 error: {mt5.last_error()}"
                )
                return

            resolved_filter = "ALL"

            if self.symbol_filter != "ALL":
                symbol_info = MT5Connector.get_symbol_info(self.symbol_filter)

                if not symbol_info:
                    self.error.emit(
                        f"Could not resolve symbol {self.symbol_filter}."
                    )
                    return

                resolved_filter = symbol_info.name

                deals = tuple(
                    deal
                    for deal in deals
                    if str(getattr(deal, "symbol", "")) == resolved_filter
                )

            trades, warnings = build_closed_trades(deals)

            metrics = calculate_metrics(
                trades=trades,
                warnings=warnings,
                symbol_filter=resolved_filter,
                days=self.days,
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                account=account_data,
            )

            self.report_ready.emit(metrics)

        except Exception as exc:
            self.error.emit(str(exc))

        finally:
            if mt5_started:
                MT5Connector.shutdown()