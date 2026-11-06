"""
Background worker for Part 6 trading operations.

All MT5 order execution is performed off the GUI thread.
"""

from PyQt6.QtCore import QThread, pyqtSignal

from core.trade_executor import DemoTradeExecutor


class TradeWorker(QThread):
    """
    Worker actions:
    - context: refresh account, contract rules and open positions.
    - open: open a demo market position.
    - close: close a demo position by ticket.
    """

    context_ready = pyqtSignal(object)
    execution_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, action: str, payload: dict = None, parent=None):
        super().__init__(parent)

        self.action = action
        self.payload = dict(payload or {})

    def run(self):
        executor = DemoTradeExecutor()

        try:
            if self.action == "context":
                symbol = self.payload.get("symbol")
                context = executor.get_trading_context(symbol)
                self.context_ready.emit(context)

            elif self.action == "open":
                result = executor.open_market_position(
                    symbol=self.payload.get("symbol"),
                    side=self.payload.get("side"),
                    volume=self.payload.get("volume"),
                    sl_points=self.payload.get("sl_points", 0),
                    tp_points=self.payload.get("tp_points", 0),
                )
                self.execution_ready.emit(result)

            elif self.action == "close":
                result = executor.close_position(
                    ticket=self.payload.get("ticket")
                )
                self.execution_ready.emit(result)

            else:
                raise ValueError(f"Unknown trade worker action: {self.action}")

        except Exception as exc:
            self.error.emit(str(exc))