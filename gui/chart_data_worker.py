import MetaTrader5 as mt5
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime

from core.mt5_connector import MT5Connector


TIMEFRAME_MAP = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "1H": mt5.TIMEFRAME_H1,
    "4H": mt5.TIMEFRAME_H4,
    "1D": mt5.TIMEFRAME_D1,
}


class ChartDataWorker(QThread):
    """
    Background worker that loads candle data from MT5.

    This worker is used only for chart display in Part 3.
    It does not place trades and does not calculate indicators.
    """

    log = pyqtSignal(str)
    data_ready = pyqtSignal(object, object)
    error = pyqtSignal(str)

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300,
        verbose: bool = True,
        parent=None,
    ):
        super().__init__(parent)

        self.symbol = symbol
        self.timeframe = timeframe
        self.limit = max(10, int(limit))
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            self.log.emit(message)

    def run(self):
        mt5_started = False

        try:
            self._log(
                f"Initializing MT5 for chart data: "
                f"{self.symbol} {self.timeframe}..."
            )

            if not MT5Connector.initialize():
                self.error.emit(
                    "MT5 initialization failed. "
                    "Ensure MT5 is running and logged into a DEMO account."
                )
                return

            mt5_started = True

            symbol_info = MT5Connector.get_symbol_info(self.symbol)
            if not symbol_info:
                self.error.emit(
                    f"Could not resolve or select symbol {self.symbol}."
                )
                return

            resolved_symbol = symbol_info.name
            digits = int(symbol_info.digits)

            timeframe_id = TIMEFRAME_MAP.get(self.timeframe)
            if timeframe_id is None:
                self.error.emit(f"Unsupported timeframe: {self.timeframe}")
                return

            self._log(
                f"Loading {self.limit} candles for "
                f"{resolved_symbol} {self.timeframe}..."
            )

            rates = mt5.copy_rates_from_pos(
                resolved_symbol,
                timeframe_id,
                0,
                self.limit,
            )

            if rates is None or len(rates) == 0:
                mt5_error = mt5.last_error()
                self.error.emit(
                    f"No candle data returned for "
                    f"{resolved_symbol} {self.timeframe}. "
                    f"MT5 error: {mt5_error}"
                )
                return

            df = pd.DataFrame(rates)

            required_columns = [
                "time",
                "open",
                "high",
                "low",
                "close",
            ]

            missing_columns = [
                column
                for column in required_columns
                if column not in df.columns
            ]

            if missing_columns:
                self.error.emit(
                    "MT5 returned unexpected candle data format. "
                    f"Missing columns: {', '.join(missing_columns)}"
                )
                return

            df["time"] = pd.to_datetime(df["time"], unit="s")

            for column in ["open", "high", "low", "close"]:
                df[column] = pd.to_numeric(df[column], errors="coerce")

            df = df[required_columns].copy()
            df.dropna(inplace=True)
            df.sort_values("time", inplace=True)
            df.reset_index(drop=True, inplace=True)

            if df.empty:
                self.error.emit(
                    f"Candle data for {resolved_symbol} {self.timeframe} "
                    "was empty after cleaning."
                )
                return

            meta = {
                "requested_symbol": self.symbol,
                "symbol": resolved_symbol,
                "timeframe": self.timeframe,
                "rows": int(len(df)),
                "digits": digits,
                "first_time": str(df["time"].iloc[0]),
                "last_time": str(df["time"].iloc[-1]),
                "last_close": float(df["close"].iloc[-1]),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self._log(
                f"Loaded {len(df)} candles for "
                f"{resolved_symbol} {self.timeframe}."
            )

            self.data_ready.emit(df, meta)

        except Exception as exc:
            self.error.emit(f"Chart data error: {exc}")

        finally:
            if mt5_started:
                MT5Connector.shutdown()
                self._log("MT5 connection closed after chart data request.")