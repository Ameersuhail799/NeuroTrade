"""Command-line interface for running realistic event-driven intraday backtests.

Supports loading data from SQLite CandleStore or local CSV files.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

import pandas as pd

from core.csv_loader import CSVDataLoader
from core.data_store import CandleStore
from core.intraday_backtester import BacktestConfig, IntradayBacktester
from core.walk_forward_validator import WalkForwardConfig, WalkForwardValidator


def parse_args():
    parser = argparse.ArgumentParser(
        description="NeuroTrade AI - Intraday Strategy Backtester Terminal"
    )
    parser.add_argument(
        "--source",
        choices=["sqlite", "csv"],
        default="sqlite",
        help="Data source: 'sqlite' (local CandleStore) or 'csv' (external files).",
    )
    parser.add_argument(
        "--symbol",
        default="XAUUSD",
        help="Trading instrument symbol (default: XAUUSD).",
    )
    parser.add_argument(
        "--h1-csv",
        type=str,
        help="Path to H1 candle CSV file (required if --source csv).",
    )
    parser.add_argument(
        "--m15-csv",
        type=str,
        help="Path to M15 candle CSV file (required if --source csv).",
    )
    parser.add_argument(
        "--m5-csv",
        type=str,
        help="Path to M5 candle CSV file (required if --source csv).",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=5000,
        help="Number of M5 bars to load when --source sqlite (default: 5000).",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital in USD (default: 10000.0).",
    )
    parser.add_argument(
        "--risk",
        type=float,
        default=0.01,
        help="Risk per trade percentage as decimal (default: 0.01 for 1%%).",
    )
    parser.add_argument(
        "--fixed-lot",
        type=float,
        default=None,
        help="Optional fixed lot size per trade (overrides risk percentage).",
    )
    parser.add_argument(
        "--spread",
        type=float,
        default=20.0,
        help="Default spread in points (default: 20.0 points = 0.20 on XAUUSD).",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=5.0,
        help="Slippage in points (default: 5.0 points = 0.05 on XAUUSD).",
    )
    parser.add_argument(
        "--no-scale-out",
        action="store_true",
        help="Disable 50%% scale-out at TP1 (exit 100%% at TP1).",
    )
    parser.add_argument(
        "--ablation",
        action="store_true",
        help="Run 5-stage filter ablation study comparing Baseline v1 vs full v2 gates.",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run purged & embargoed rolling walk-forward validation (4 folds).",
    )
    parser.add_argument(
        "--max-hold-bars",
        type=int,
        default=48,
        help="Maximum M5 holding bars before time exit (default: 48 = 4 hours).",
    )
    parser.add_argument(
        "--trades-csv",
        type=str,
        default=None,
        help="Optional CSV file path to export individual trade records.",
    )
    return parser.parse_args()


def load_from_sqlite(symbol: str, m5_bars: int):
    store = CandleStore()
    if not store.connect():
        raise RuntimeError("Could not connect to CandleStore database.")

    try:
        # H1 needs roughly m5_bars / 12, with minimum 500
        h1_limit = max(500, int(m5_bars / 12) + 250)
        # M15 needs roughly m5_bars / 3, with minimum 500
        m15_limit = max(500, int(m5_bars / 3) + 100)

        h1 = store.load_candles(symbol, "1H", limit=h1_limit)
        m15 = store.load_candles(symbol, "15m", limit=m15_limit)
        m5 = store.load_candles(symbol, "5m", limit=m5_bars)

        if h1.empty or m15.empty or m5.empty:
            raise RuntimeError(
                f"Insufficient candles in CandleStore for {symbol}. "
                f"Loaded: H1={len(h1)}, M15={len(m15)}, M5={len(m5)}. "
                "Sync historical data first or use --source csv."
            )

        return h1, m15, m5
    finally:
        store.close()


def load_from_csv(h1_path: str, m15_path: str, m5_path: str):
    if not (h1_path and m15_path and m5_path):
        raise ValueError(
            "When --source csv is specified, --h1-csv, --m15-csv, and --m5-csv must all be provided."
        )

    h1 = CSVDataLoader.load_csv(h1_path)
    m15 = CSVDataLoader.load_csv(m15_path)
    m5 = CSVDataLoader.load_csv(m5_path)
    return h1, m15, m5


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"Loading data for {args.symbol} from {args.source.upper()}...")
    try:
        if args.source == "sqlite":
            h1, m15, m5 = load_from_sqlite(args.symbol, args.bars)
        else:
            h1, m15, m5 = load_from_csv(args.h1_csv, args.m15_csv, args.m5_csv)
    except Exception as exc:
        print(f"Error loading candles: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Candles loaded: 1H={len(h1)}, 15m={len(m15)}, 5m={len(m5)}")
    print("Executing event-driven intraday backtest...")

    cfg = BacktestConfig(
        symbol=args.symbol,
        initial_capital=args.capital,
        risk_per_trade_pct=args.risk,
        fixed_lot_size=args.fixed_lot,
        default_spread_points=args.spread,
        slippage_points=args.slippage,
        scale_out_tp1=not args.no_scale_out,
        max_hold_m5_bars=args.max_hold_bars,
    )

    if args.ablation:
        print("Executing 5-stage strategy ablation study...")
        rows = WalkForwardValidator.run_ablation_study(
            h1=h1,
            m15=m15,
            m5=m5,
            symbol=args.symbol,
            backtest_config=cfg,
        )
        report = WalkForwardValidator.format_ablation_report(rows)
        print("\n" + report)
        return

    if getattr(args, "walk_forward", False):
        print("Executing rolling purged walk-forward validation (4 folds)...")
        summary = WalkForwardValidator.run_walk_forward(
            h1=h1,
            m15=m15,
            m5=m5,
            symbol=args.symbol,
            backtest_config=cfg,
        )
        report = WalkForwardValidator.format_walk_forward_report(summary)
        print("\n" + report)
        return

    backtester = IntradayBacktester(config=cfg)
    result = backtester.run(h1, m15, m5)

    report = IntradayBacktester.format_report(result)
    print("\n" + report)

    if args.trades_csv and result.trades:
        trades_data = []
        for t in result.trades:
            trades_data.append(
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "signal_time": t.signal_time,
                    "entry_time": t.entry_time,
                    "entry_fill": t.entry_fill,
                    "initial_stop_loss": t.initial_stop_loss,
                    "take_profit_1": t.take_profit_1,
                    "take_profit_2": t.take_profit_2,
                    "lot_size": t.lot_size,
                    "partial_exit_time": t.partial_exit_time,
                    "partial_exit_price": t.partial_exit_price,
                    "final_exit_time": t.final_exit_time,
                    "final_exit_price": t.final_exit_price,
                    "final_exit_reason": t.final_exit_reason,
                    "net_pnl": t.net_pnl,
                    "realized_r": t.realized_r,
                    "session": t.session,
                }
            )
        pd.DataFrame(trades_data).to_csv(args.trades_csv, index=False)
        print(f"Trade log exported to: {args.trades_csv}")


if __name__ == "__main__":
    main()
