"""
Background worker for Part 4 data sync and indicator calculation.
"""

import MetaTrader5 as mt5
from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime

from core.mt5_connector import MT5Connector
from core.data_store import CandleStore
from core.data_engine import DataEngine
from core.indicators import IndicatorEngine


class DataWorker(QThread):
    """
    mode="sync": download real candles from MT5, store in SQLite, calculate indicators.
    mode="load": load stored candles from SQLite and calculate indicators.

    Never places orders.
    """

    log = pyqtSignal(str)
    data_ready = pyqtSignal(object, object)
    error = pyqtSignal(str)

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        mode: str = "sync",
        limit: int = 500,
        parent=None,
    ):
        super().__init__(parent)
        self.symbol = symbol
        self.timeframe = timeframe
        self.mode = mode
        self.limit = max(10, int(limit))

    def run(self):
        store = CandleStore()
        store_connected = False
        mt5_started = False

        try:
            self.log.emit(f"Opening candle history store for {self.symbol} {self.timeframe}...")

            if not store.connect():
                self.error.emit("Could not open the SQLite candle history store.")
                return
            store_connected = True

            engine = DataEngine(
                symbol=self.symbol,
                timeframe=self.timeframe,
                store=store,
            )

            if self.mode == "load":
                self.log.emit("Loading stored candles from SQLite (no MT5 call)...")
                raw = engine.load_recent(self.limit)
                source = "SQLite"
                rows_written = 0
            else:
                self.log.emit("Initializing MT5 for history sync...")
                if not MT5Connector.initialize():
                    self.error.emit(
                        "MT5 initialization failed. "
                        "Ensure MT5 is running and logged into a DEMO account."
                    )
                    return
                mt5_started = True

                self.log.emit(f"Downloading up to {self.limit} candles from MT5...")
                raw = engine.sync_recent(self.limit)
                source = "MT5"
                rows_written = len(raw)

            resolved = engine.resolved_symbol or self.symbol

            self.log.emit("Calculating SMA/EMA/RSI/ATR/MACD/Bollinger (pandas/numpy)...")
            enriched = IndicatorEngine.add_indicators(raw)

            stored_count = store.count_candles(resolved, self.timeframe)

            meta = {
                "symbol": resolved,
                "requested_symbol": self.symbol,
                "timeframe": self.timeframe,
                "source": source,
                "rows": int(len(enriched)),
                "rows_written": int(rows_written),
                "stored_rows": int(stored_count),
                "digits": int(engine.digits),
                "first_time": str(enriched["time"].iloc[0]),
                "last_time": str(enriched["time"].iloc[-1]),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self.log.emit(
                f"{source}: {len(enriched)} candles loaded, "
                f"{stored_count} stored for {resolved} {self.timeframe}."
            )

            self.data_ready.emit(enriched, meta)

        except Exception as exc:
            self.error.emit(f"Data engine error: {exc}")

        finally:
            if mt5_started:
                MT5Connector.shutdown()
                self.log.emit("MT5 connection closed after data sync.")

            if store_connected:
                store.close()