"""
Persistent Trading panel for Part 10.

Reuses the Part 6 TradingPanel but replaces its worker with one that
persists demo trade executions to SQLite.
"""

from gui.widgets.trading_panel import TradingPanel
from gui.trade_worker import TradeWorker
from core.trade_executor import DemoTradeExecutor
from core.trade_store import TradeStore


class PersistentTradeWorker(TradeWorker):
    """
    Trade worker that persists execution results locally.
    """

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
                self._persist(result)
                self.execution_ready.emit(result)

            elif self.action == "close":
                result = executor.close_position(
                    ticket=self.payload.get("ticket")
                )
                self._persist(result)
                self.execution_ready.emit(result)

            else:
                raise ValueError(f"Unknown trade worker action: {self.action}")

        except Exception as exc:
            self.error.emit(str(exc))

    def _persist(self, result):
        store = TradeStore()

        try:
            if not store.connect():
                result.notes.append(
                    "Warning: trade store unavailable; execution not persisted."
                )
                return

            local_id = store.save_execution(
                result=result,
                worker_action=self.action,
                payload=self.payload,
            )

            result.notes.append(
                f"Execution persisted with local id {local_id}."
            )

        except Exception as exc:
            result.notes.append(f"Warning: trade persistence failed: {exc}")

        finally:
            store.close()


class PersistentTradingPanel(TradingPanel):
    """
    Trading panel that writes demo executions to SQLite.
    """

    def _start_worker(self, action: str, payload: dict):
        if self.is_worker_running():
            self._append_output("A trade operation is already running.")
            return

        self._set_controls_enabled(False)
        self._append_output(f"Starting {action} operation...")

        self._worker = PersistentTradeWorker(action=action, payload=payload)
        self._worker.context_ready.connect(self._on_context_ready)
        self._worker.execution_ready.connect(self._on_execution_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()