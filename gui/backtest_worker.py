"""Background QThread worker for executing backtests, walk-forward, and ablation studies."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.data_store import CandleStore
from core.intraday_backtester import BacktestConfig, IntradayBacktester
from core.market_regimes import IntradayStrategyConfig
from core.mt5_connector import MT5Connector
from core.multi_timeframe_data import MultiTimeframeDataCoordinator
from core.walk_forward_validator import WalkForwardConfig, WalkForwardValidator


class BacktestWorker(QThread):
    """Executes intraday backtests off the main UI thread."""

    backtest_ready = pyqtSignal(object, str)
    error = pyqtSignal(str)

    def __init__(
        self,
        symbol: str,
        mode: str = "load",
        run_type: str = "backtest",
        bars: int = 2000,
        capital: float = 10000.0,
        risk: float = 0.01,
        spread: float = 20.0,
        slippage: float = 5.0,
        scale_out_tp1: bool = True,
        strategy_config: Optional[IntradayStrategyConfig] = None,
        wf_config: Optional[WalkForwardConfig] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.symbol = symbol
        self.mode = mode
        self.run_type = run_type
        self.bars = bars
        self.capital = capital
        self.risk = risk
        self.spread = spread
        self.slippage = slippage
        self.scale_out_tp1 = scale_out_tp1
        self.strategy_config = strategy_config or IntradayStrategyConfig()
        self.wf_config = wf_config or WalkForwardConfig()

    def run(self):
        store = CandleStore()
        if not store.connect():
            self.error.emit("Failed to connect to local CandleStore SQLite database.")
            return

        mt5_acquired = False
        try:
            if self.mode == "sync":
                if not MT5Connector.initialize():
                    self.error.emit(
                        "MT5 is unavailable or not logged into a DEMO account. "
                        "Cannot sync live MT5 history."
                    )
                    return
                mt5_acquired = True

                resolved = MT5Connector.resolve_symbol(self.symbol)
                if not resolved:
                    self.error.emit(f"Could not resolve broker symbol for: {self.symbol}")
                    return

                coord = MultiTimeframeDataCoordinator(symbol=resolved, store=store)
                mtf_data = coord.sync_all(requested_bars=self.bars)
            else:
                coord = MultiTimeframeDataCoordinator(symbol=self.symbol, store=store)
                mtf_data = coord.load_all(requested_bars=self.bars)

            h1 = mtf_data.get("1H")
            m15 = mtf_data.get("15m")
            m5 = mtf_data.get("5m")

            if h1 is None or m15 is None or m5 is None or h1.empty or m15.empty or m5.empty:
                self.error.emit(
                    f"Insufficient candle history for {self.symbol}. "
                    "Run 'Sync MT5 & Backtest' or sync data in the Data tab first."
                )
                return

            b_cfg = BacktestConfig(
                symbol=self.symbol,
                initial_capital=self.capital,
                risk_per_trade_pct=self.risk,
                default_spread_points=self.spread,
                slippage_points=self.slippage,
                scale_out_tp1=self.scale_out_tp1,
            )

            if self.run_type == "backtest":
                bt = IntradayBacktester(config=b_cfg, strategy_config=self.strategy_config)
                result = bt.run(h1, m15, m5)
                report = IntradayBacktester.format_report(result)
                self.backtest_ready.emit(result, report)

            elif self.run_type == "ablation":
                rows = WalkForwardValidator.run_ablation_study(
                    h1=h1,
                    m15=m15,
                    m5=m5,
                    symbol=self.symbol,
                    backtest_config=b_cfg,
                )
                report = WalkForwardValidator.format_ablation_report(rows)
                self.backtest_ready.emit(rows, report)

            elif self.run_type == "walk_forward":
                summary = WalkForwardValidator.run_walk_forward(
                    h1=h1,
                    m15=m15,
                    m5=m5,
                    symbol=self.symbol,
                    backtest_config=b_cfg,
                    strategy_config=self.strategy_config,
                    wf_config=self.wf_config,
                )
                report = WalkForwardValidator.format_walk_forward_report(summary)
                self.backtest_ready.emit(summary, report)

            else:
                self.error.emit(f"Unknown backtest run_type: {self.run_type}")

        except Exception as exc:
            logging.exception(f"BacktestWorker execution error: {exc}")
            self.error.emit(f"Backtest execution error: {exc}")
        finally:
            if mt5_acquired:
                MT5Connector.shutdown()
            store.close()
