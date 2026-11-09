"""Event-Driven Realistic Intraday Backtester for NeuroTrade AI.

Simulates the H1 / M15 / M5 intraday trading strategy with:
- Zero look-ahead bias via causal stepping on completed candle close times
- Realistic next-bar open fill with spread, slippage, and commission
- Pessimistic intrabar tie-breaking (Stop Loss evaluated before Take Profit)
- Two-stage exit (50% scale-out at TP1, move remaining 50% stop to breakeven)
- Institutional scorecard and session breakdown (Asian, London, London/NY, NY Afternoon, Rollover)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.intraday_signal_engine import IntradaySignal, IntradaySignalEngine
from core.market_regimes import IntradayStrategyConfig


@dataclass
class BacktestConfig:
    """Configuration for intraday event-driven backtesting."""

    symbol: str = "XAUUSD"
    initial_capital: float = 10000.0
    risk_per_trade_pct: float = 0.01  # 1% equity risk per trade
    fixed_lot_size: Optional[float] = None  # If set, overrides risk_per_trade_pct
    default_spread_points: float = 20.0  # 20 points (0.20 on XAUUSD)
    slippage_points: float = 5.0  # 5 points (0.05 on XAUUSD)
    point: float = 0.01
    contract_size: float = 100.0  # 100 oz per lot for XAUUSD
    commission_per_lot: float = 7.0  # $7.00 round-turn commission per lot
    scale_out_tp1: bool = True  # 50% exit at TP1, move remaining stop to breakeven
    max_hold_m5_bars: int = 48  # 4 hours max holding time (48 * 5m)
    digits: int = 2


@dataclass
class BacktestTrade:
    """Record of a simulated intraday trade."""

    trade_id: int
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_bar_idx: int
    entry_fill: float
    initial_risk_r: float  # Price distance |entry_fill - stop_loss|
    initial_stop_loss: float
    current_stop_loss: float
    take_profit_1: float
    take_profit_2: float
    lot_size: float
    remaining_lots: float
    stage: str = "OPEN"  # 'OPEN', 'TP1_SCALED', 'CLOSED'
    partial_exit_time: Optional[pd.Timestamp] = None
    partial_exit_price: Optional[float] = None
    partial_exit_lots: float = 0.0
    final_exit_time: Optional[pd.Timestamp] = None
    final_exit_price: Optional[float] = None
    final_exit_reason: Optional[str] = None  # 'STOP_LOSS', 'BE_STOP', 'TP1', 'TP2', 'TIME_EXIT'
    gross_pnl: float = 0.0
    commission: float = 0.0
    net_pnl: float = 0.0
    realized_r: float = 0.0
    session: str = ""
    confluence_score: float = 0.0
    market_regime: str = ""


@dataclass
class BacktestResult:
    """Comprehensive performance results from an intraday backtest."""

    config: BacktestConfig
    start_time: Optional[pd.Timestamp]
    end_time: Optional[pd.Timestamp]
    total_bars_m5: int
    total_trades: int
    long_trades: int
    short_trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float
    expectancy_r: float
    initial_capital: float
    ending_capital: float
    net_profit: float
    net_profit_pct: float
    gross_profit: float
    gross_loss: float
    total_commission: float
    profit_factor: float
    payoff_ratio: float
    max_drawdown_currency: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    session_metrics: Dict[str, Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]
    trades: List[BacktestTrade]


class IntradayBacktester:
    """Event-driven intraday backtester for H1/M15/M5 strategy."""

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        strategy_config: Optional[IntradayStrategyConfig] = None,
    ):
        self.config = config or BacktestConfig()
        self.strategy_config = strategy_config or IntradayStrategyConfig()
        self.engine = IntradaySignalEngine(config=self.strategy_config)

    @staticmethod
    def classify_session(dt: pd.Timestamp) -> str:
        """Classify UTC timestamp into standard forex trading sessions."""
        hour = dt.hour
        if 0 <= hour < 7:
            return "Asian"
        elif 7 <= hour < 13:
            return "London"
        elif 13 <= hour < 17:
            return "London_NY_Overlap"
        elif 17 <= hour < 21:
            return "NY_Afternoon"
        else:
            return "Rollover"

    def run(
        self,
        h1: pd.DataFrame,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        eval_start_time: Optional[Union[pd.Timestamp, str]] = None,
        eval_end_time: Optional[Union[pd.Timestamp, str]] = None,
    ) -> BacktestResult:
        """Run the causal backtest across the provided candle datasets."""
        # Ensure chronological ordering and datetime index/column
        h1 = h1.sort_values("time").reset_index(drop=True)
        m15 = m15.sort_values("time").reset_index(drop=True)
        m5 = m5.sort_values("time").reset_index(drop=True)

        h1["time"] = pd.to_datetime(h1["time"])
        m15["time"] = pd.to_datetime(m15["time"])
        m5["time"] = pd.to_datetime(m5["time"])

        for df in (h1, m15, m5):
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

        eval_start_ts = pd.to_datetime(eval_start_time) if eval_start_time is not None else None
        eval_end_ts = pd.to_datetime(eval_end_time) if eval_end_time is not None else None

        # Precompute candle completion times (time = open timestamp)
        h1_close_times = (h1["time"] + pd.Timedelta(hours=1)).values
        m15_close_times = (m15["time"] + pd.Timedelta(minutes=15)).values
        m5_close_times = m5["time"] + pd.Timedelta(minutes=5)

        current_equity = self.config.initial_capital
        equity_curve: List[Dict[str, Any]] = [
            {
                "time": m5.iloc[0]["time"],
                "equity": current_equity,
                "drawdown": 0.0,
            }
        ]

        trades: List[BacktestTrade] = []
        open_trade: Optional[BacktestTrade] = None
        trade_id_seq = 0

        # Minimum required bars check
        min_h1_req = self.engine.MIN_H1_BARS
        min_m15_req = self.engine.MIN_M15_BARS
        min_m5_req = self.engine.MIN_M5_BARS

        # Pending signal generated at bar i to be executed on bar i + 1 open
        pending_signal: Optional[IntradaySignal] = None
        pending_signal_bar_idx: Optional[int] = None

        m5_len = len(m5)

        for i in range(m5_len):
            current_bar = m5.iloc[i]
            bar_time = current_bar["time"]
            bar_open = float(current_bar["open"])
            bar_high = float(current_bar["high"])
            bar_low = float(current_bar["low"])
            bar_close = float(current_bar["close"])
            bar_spread_raw = current_bar.get("spread", 0)
            bar_spread_pts = (
                float(bar_spread_raw)
                if (bar_spread_raw is not None and float(bar_spread_raw) > 0)
                else self.config.default_spread_points
            )
            spread_val = bar_spread_pts * self.config.point
            slip_val = self.config.slippage_points * self.config.point

            # -------------------------------------------------------------
            # 1. PROCESS PENDING SIGNAL AT NEXT BAR OPEN
            # -------------------------------------------------------------
            if pending_signal is not None and open_trade is None and i == pending_signal_bar_idx + 1:
                sig = pending_signal
                pending_signal = None
                pending_signal_bar_idx = None

                direction = sig.direction.upper() if sig.direction else ""  # 'BUY'/'LONG' or 'SELL'/'SHORT'
                if direction in ("BUY", "LONG"):
                    entry_fill = bar_open + spread_val + slip_val
                    init_stop = float(sig.stop_loss)
                    tp1 = float(sig.take_profit_1)
                    tp2 = float(sig.take_profit_2)
                    risk_r = entry_fill - init_stop

                    # Gap validation: cancel if open/fill gaps beyond stop or leaves non-positive risk
                    if bar_open <= init_stop or entry_fill <= init_stop or risk_r <= 0 or entry_fill >= tp1:
                        logging.debug(f"LONG setup at {bar_time} gap invalidated.")
                    else:
                        trade_id_seq += 1
                        if self.config.fixed_lot_size is not None:
                            lot_size = self.config.fixed_lot_size
                        else:
                            risk_cash = current_equity * self.config.risk_per_trade_pct
                            lot_size = round(risk_cash / (risk_r * self.config.contract_size), 2)
                            lot_size = max(0.01, lot_size)

                        open_trade = BacktestTrade(
                            trade_id=trade_id_seq,
                            symbol=self.config.symbol,
                            direction="LONG",
                            signal_time=sig.decision_time,
                            entry_time=bar_time,
                            entry_bar_idx=i,
                            entry_fill=round(entry_fill, self.config.digits),
                            initial_risk_r=round(risk_r, self.config.digits),
                            initial_stop_loss=init_stop,
                            current_stop_loss=init_stop,
                            take_profit_1=tp1,
                            take_profit_2=tp2,
                            lot_size=lot_size,
                            remaining_lots=lot_size,
                            session=self.classify_session(bar_time),
                            confluence_score=sig.confluence_score,
                            market_regime=sig.market_regime,
                        )

                elif direction in ("SELL", "SHORT"):
                    entry_fill = bar_open - slip_val
                    init_stop = float(sig.stop_loss)
                    tp1 = float(sig.take_profit_1)
                    tp2 = float(sig.take_profit_2)
                    risk_r = init_stop - entry_fill

                    # Gap validation for SHORT
                    if bar_open >= init_stop or entry_fill >= init_stop or risk_r <= 0 or entry_fill <= tp1:
                        logging.debug(f"SHORT setup at {bar_time} gap invalidated.")
                    else:
                        trade_id_seq += 1
                        if self.config.fixed_lot_size is not None:
                            lot_size = self.config.fixed_lot_size
                        else:
                            risk_cash = current_equity * self.config.risk_per_trade_pct
                            lot_size = round(risk_cash / (risk_r * self.config.contract_size), 2)
                            lot_size = max(0.01, lot_size)

                        open_trade = BacktestTrade(
                            trade_id=trade_id_seq,
                            symbol=self.config.symbol,
                            direction="SHORT",
                            signal_time=sig.decision_time,
                            entry_time=bar_time,
                            entry_bar_idx=i,
                            entry_fill=round(entry_fill, self.config.digits),
                            initial_risk_r=round(risk_r, self.config.digits),
                            initial_stop_loss=init_stop,
                            current_stop_loss=init_stop,
                            take_profit_1=tp1,
                            take_profit_2=tp2,
                            lot_size=lot_size,
                            remaining_lots=lot_size,
                            session=self.classify_session(bar_time),
                            confluence_score=sig.confluence_score,
                            market_regime=sig.market_regime,
                        )

            # -------------------------------------------------------------
            # 2. INTRABAR POSITION MONITORING & RESOLUTION
            # -------------------------------------------------------------
            if open_trade is not None:
                tr = open_trade
                bars_held = i - tr.entry_bar_idx

                if tr.direction == "LONG":
                    # LONG exits at Bid
                    # Pessimistic tie-breaker: Stop loss checked FIRST before TP
                    hit_stop = bar_low <= tr.current_stop_loss
                    if hit_stop:
                        tr.final_exit_time = bar_time
                        fill_sl = min(bar_open, tr.current_stop_loss) - slip_val
                        tr.final_exit_price = round(fill_sl, self.config.digits)
                        tr.final_exit_reason = "BE_STOP" if tr.stage == "TP1_SCALED" else "STOP_LOSS"
                        tr.stage = "CLOSED"
                    else:
                        # Stop not hit; check targets
                        if tr.stage == "OPEN":
                            if bar_high >= tr.take_profit_1:
                                if self.config.scale_out_tp1:
                                    # Scale out 50%
                                    scale_lots = round(tr.lot_size * 0.5, 2)
                                    tr.partial_exit_time = bar_time
                                    tr.partial_exit_price = tr.take_profit_1
                                    tr.partial_exit_lots = scale_lots
                                    tr.remaining_lots = round(tr.lot_size - scale_lots, 2)
                                    tr.current_stop_loss = tr.entry_fill  # Move stop to breakeven
                                    tr.stage = "TP1_SCALED"

                                    # Check if TP2 also hit on same bar with confirming close
                                    if bar_high >= tr.take_profit_2 and bar_close >= tr.take_profit_1:
                                        tr.final_exit_time = bar_time
                                        tr.final_exit_price = tr.take_profit_2
                                        tr.final_exit_reason = "TP2"
                                        tr.stage = "CLOSED"
                                else:
                                    tr.final_exit_time = bar_time
                                    tr.final_exit_price = tr.take_profit_1
                                    tr.final_exit_reason = "TP1"
                                    tr.stage = "CLOSED"

                        elif tr.stage == "TP1_SCALED":
                            if bar_high >= tr.take_profit_2:
                                tr.final_exit_time = bar_time
                                tr.final_exit_price = tr.take_profit_2
                                tr.final_exit_reason = "TP2"
                                tr.stage = "CLOSED"

                    # Max holding time exit
                    if tr.stage != "CLOSED" and bars_held >= self.config.max_hold_m5_bars:
                        tr.final_exit_time = bar_time
                        tr.final_exit_price = round(bar_close - slip_val, self.config.digits)
                        tr.final_exit_reason = "TIME_EXIT"
                        tr.stage = "CLOSED"

                elif tr.direction == "SHORT":
                    # SHORT exits at Ask (Bid + spread)
                    ask_high = bar_high + spread_val
                    ask_low = bar_low + spread_val
                    ask_open = bar_open + spread_val
                    ask_close = bar_close + spread_val

                    # Pessimistic tie-breaker: Stop loss checked FIRST before TP
                    hit_stop = ask_high >= tr.current_stop_loss
                    if hit_stop:
                        tr.final_exit_time = bar_time
                        fill_sl = max(ask_open, tr.current_stop_loss) + slip_val
                        tr.final_exit_price = round(fill_sl, self.config.digits)
                        tr.final_exit_reason = "BE_STOP" if tr.stage == "TP1_SCALED" else "STOP_LOSS"
                        tr.stage = "CLOSED"
                    else:
                        if tr.stage == "OPEN":
                            if ask_low <= tr.take_profit_1:
                                if self.config.scale_out_tp1:
                                    scale_lots = round(tr.lot_size * 0.5, 2)
                                    tr.partial_exit_time = bar_time
                                    tr.partial_exit_price = tr.take_profit_1
                                    tr.partial_exit_lots = scale_lots
                                    tr.remaining_lots = round(tr.lot_size - scale_lots, 2)
                                    tr.current_stop_loss = tr.entry_fill  # Move stop to breakeven
                                    tr.stage = "TP1_SCALED"

                                    if ask_low <= tr.take_profit_2 and ask_close <= tr.take_profit_1:
                                        tr.final_exit_time = bar_time
                                        tr.final_exit_price = tr.take_profit_2
                                        tr.final_exit_reason = "TP2"
                                        tr.stage = "CLOSED"
                                else:
                                    tr.final_exit_time = bar_time
                                    tr.final_exit_price = tr.take_profit_1
                                    tr.final_exit_reason = "TP1"
                                    tr.stage = "CLOSED"

                        elif tr.stage == "TP1_SCALED":
                            if ask_low <= tr.take_profit_2:
                                tr.final_exit_time = bar_time
                                tr.final_exit_price = tr.take_profit_2
                                tr.final_exit_reason = "TP2"
                                tr.stage = "CLOSED"

                    # Max holding time exit
                    if tr.stage != "CLOSED" and bars_held >= self.config.max_hold_m5_bars:
                        tr.final_exit_time = bar_time
                        tr.final_exit_price = round(ask_close + slip_val, self.config.digits)
                        tr.final_exit_reason = "TIME_EXIT"
                        tr.stage = "CLOSED"

                # If trade closed on this bar, settle P&L and update equity
                if tr.stage == "CLOSED":
                    pnl_partial = 0.0
                    if tr.partial_exit_lots > 0:
                        if tr.direction == "LONG":
                            pnl_partial = (
                                (tr.partial_exit_price - tr.entry_fill)
                                * tr.partial_exit_lots
                                * self.config.contract_size
                            )
                        else:
                            pnl_partial = (
                                (tr.entry_fill - tr.partial_exit_price)
                                * tr.partial_exit_lots
                                * self.config.contract_size
                            )

                    pnl_final = 0.0
                    if tr.direction == "LONG":
                        pnl_final = (
                            (tr.final_exit_price - tr.entry_fill)
                            * tr.remaining_lots
                            * self.config.contract_size
                        )
                    else:
                        pnl_final = (
                            (tr.entry_fill - tr.final_exit_price)
                            * tr.remaining_lots
                            * self.config.contract_size
                        )

                    tr.gross_pnl = round(pnl_partial + pnl_final, 2)
                    tr.commission = round(tr.lot_size * self.config.commission_per_lot, 2)
                    tr.net_pnl = round(tr.gross_pnl - tr.commission, 2)

                    initial_risk_cash = tr.initial_risk_r * tr.lot_size * self.config.contract_size
                    if initial_risk_cash > 0:
                        tr.realized_r = round(tr.net_pnl / initial_risk_cash, 3)
                    else:
                        tr.realized_r = 0.0

                    current_equity = round(current_equity + tr.net_pnl, 2)
                    peak_equity = max(pt["equity"] for pt in equity_curve)
                    peak_equity = max(peak_equity, current_equity)
                    drawdown = round(peak_equity - current_equity, 2)

                    equity_curve.append(
                        {
                            "time": bar_time,
                            "equity": current_equity,
                            "drawdown": drawdown,
                        }
                    )

                    trades.append(tr)
                    open_trade = None

            # -------------------------------------------------------------
            # 3. EVALUATE SIGNAL AT COMPLETED M5 BAR CLOSE (if no active trade)
            # -------------------------------------------------------------
            in_eval_window = (
                (eval_start_ts is None or bar_time >= eval_start_ts)
                and (eval_end_ts is None or bar_time <= eval_end_ts)
            )

            if open_trade is None and pending_signal is None and i < m5_len - 1 and in_eval_window:
                cur_m5_close_dt = m5_close_times.iloc[i]
                cur_m5_close_val = cur_m5_close_dt.to_datetime64()

                # Zero look-ahead: search for latest H1 and M15 bars whose close <= cur_m5_close
                h1_idx = np.searchsorted(h1_close_times, cur_m5_close_val, side="right") - 1
                m15_idx = np.searchsorted(m15_close_times, cur_m5_close_val, side="right") - 1

                if (
                    h1_idx >= min_h1_req - 1
                    and m15_idx >= min_m15_req - 1
                    and i >= min_m5_req - 1
                ):
                    # Slices of completed candles up to causal boundary, capped for fast evaluation
                    h1_end = h1_idx + 1
                    m15_end = m15_idx + 1
                    m5_end = i + 1

                    h1_slice = h1.iloc[max(0, h1_end - 250) : h1_end]
                    m15_slice = m15.iloc[max(0, m15_end - 120) : m15_end]
                    m5_slice = m5.iloc[max(0, m5_end - 120) : m5_end]

                    try:
                        sig = self.engine.generate_signal(
                            h1_slice,
                            m15_slice,
                            m5_slice,
                            symbol=self.config.symbol,
                            digits=self.config.digits,
                            exclude_latest=False,  # Slices are already closed completed candles
                            point=self.config.point,
                        )
                        if sig.action in ("LONG_SETUP", "SHORT_SETUP"):
                            pending_signal = sig
                            pending_signal_bar_idx = i
                    except Exception as exc:
                        logging.debug(f"Signal generation error at {bar_time}: {exc}")

        # Compute summary statistics
        total_trades = len(trades)
        long_trades = sum(1 for t in trades if t.direction == "LONG")
        short_trades = sum(1 for t in trades if t.direction == "SHORT")
        wins = sum(1 for t in trades if t.net_pnl > 0.0)
        losses = sum(1 for t in trades if t.net_pnl < 0.0)
        breakevens = sum(1 for t in trades if t.net_pnl == 0.0)

        win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
        expectancy_r = round(float(np.mean([t.realized_r for t in trades])), 2) if total_trades > 0 else 0.0

        net_profit = round(current_equity - self.config.initial_capital, 2)
        net_profit_pct = round((net_profit / self.config.initial_capital) * 100, 2)

        gross_profit = round(sum(t.net_pnl for t in trades if t.net_pnl > 0), 2)
        gross_loss = round(abs(sum(t.net_pnl for t in trades if t.net_pnl < 0)), 2)
        total_commission = round(sum(t.commission for t in trades), 2)

        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        else:
            profit_factor = float("inf") if gross_profit > 0 else 0.0

        avg_win = (gross_profit / wins) if wins > 0 else 0.0
        avg_loss = (gross_loss / losses) if losses > 0 else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        # Drawdown computation
        max_drawdown_curr = max((pt["drawdown"] for pt in equity_curve), default=0.0)
        peak = self.config.initial_capital
        max_dd_pct = 0.0
        for pt in equity_curve:
            eq = pt["equity"]
            if eq > peak:
                peak = eq
            dd_pct = ((peak - eq) / peak) * 100 if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
        max_dd_pct = round(max_dd_pct, 2)

        # Max consecutive losses
        max_cons_losses = 0
        cur_cons_losses = 0
        for t in trades:
            if t.net_pnl < 0:
                cur_cons_losses += 1
                if cur_cons_losses > max_cons_losses:
                    max_cons_losses = cur_cons_losses
            else:
                cur_cons_losses = 0

        # Session metrics
        session_names = ["Asian", "London", "London_NY_Overlap", "NY_Afternoon", "Rollover"]
        session_metrics: Dict[str, Dict[str, Any]] = {}
        for s_name in session_names:
            s_trades = [t for t in trades if t.session == s_name]
            s_count = len(s_trades)
            s_wins = sum(1 for t in s_trades if t.net_pnl > 0)
            s_losses = sum(1 for t in s_trades if t.net_pnl < 0)
            s_wr = round((s_wins / s_count) * 100, 1) if s_count > 0 else 0.0
            s_exp_r = round(float(np.mean([t.realized_r for t in s_trades])), 2) if s_count > 0 else 0.0
            s_pnl = round(sum(t.net_pnl for t in s_trades), 2)
            session_metrics[s_name] = {
                "trades": s_count,
                "wins": s_wins,
                "losses": s_losses,
                "win_rate": s_wr,
                "expectancy_r": s_exp_r,
                "net_profit": s_pnl,
            }

        start_time = (
            eval_start_ts
            if eval_start_ts is not None
            else (m5.iloc[0]["time"] if len(m5) > 0 else None)
        )
        end_time = (
            eval_end_ts
            if eval_end_ts is not None
            else (m5.iloc[-1]["time"] if len(m5) > 0 else None)
        )
        eval_bars = (
            int(
                (
                    (m5["time"] >= eval_start_ts if eval_start_ts is not None else True)
                    & (m5["time"] <= eval_end_ts if eval_end_ts is not None else True)
                ).sum()
            )
            if (eval_start_ts is not None or eval_end_ts is not None)
            else m5_len
        )

        return BacktestResult(
            config=self.config,
            start_time=start_time,
            end_time=end_time,
            total_bars_m5=eval_bars,
            total_trades=total_trades,
            long_trades=long_trades,
            short_trades=short_trades,
            wins=wins,
            losses=losses,
            breakevens=breakevens,
            win_rate=win_rate,
            expectancy_r=expectancy_r,
            initial_capital=self.config.initial_capital,
            ending_capital=current_equity,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            total_commission=total_commission,
            profit_factor=profit_factor,
            payoff_ratio=payoff_ratio,
            max_drawdown_currency=max_drawdown_curr,
            max_drawdown_pct=max_dd_pct,
            max_consecutive_losses=max_cons_losses,
            session_metrics=session_metrics,
            equity_curve=equity_curve,
            trades=trades,
        )

    @classmethod
    def format_report(cls, res: BacktestResult) -> str:
        """Format an institutional ASCII scorecard report."""
        lines = []
        lines.append("=" * 80)
        lines.append("                    NEUROTRADE AI - INTRADAY BACKTEST REPORT                    ")
        lines.append("=" * 80)

        date_range_str = f"{res.start_time} to {res.end_time}" if res.start_time else "N/A"
        lines.append(f" Instrument:       {res.config.symbol} (1H Trend / 15m Setup / 5m Trigger)")
        lines.append(f" Date Range:       {date_range_str} ({res.total_bars_m5:,} M5 bars)")
        lines.append(f" Initial Capital:  ${res.initial_capital:,.2f}")
        lines.append(f" Ending Capital:   ${res.ending_capital:,.2f}")
        net_sign = "+" if res.net_profit >= 0 else ""
        lines.append(
            f" Net Profit:       {net_sign}${res.net_profit:,.2f} ({net_sign}{res.net_profit_pct:.2f}%) "
            f"[Comm: ${res.total_commission:,.2f}]"
        )
        lines.append(f" Total Trades:     {res.total_trades} (Long: {res.long_trades}, Short: {res.short_trades})")
        lines.append(
            f" Win Rate:         {res.win_rate:.1f}% (Wins: {res.wins}, Losses: {res.losses}, BE: {res.breakevens})"
        )
        exp_sign = "+" if res.expectancy_r >= 0 else ""
        lines.append(f" Expectancy:       {exp_sign}{res.expectancy_r:.2f} R per trade")
        lines.append(f" Profit Factor:    {res.profit_factor:.2f}")
        lines.append(f" Payoff Ratio:     {res.payoff_ratio:.2f}")
        lines.append(
            f" Max Drawdown:     ${res.max_drawdown_currency:,.2f} ({res.max_drawdown_pct:.2f}%)"
        )
        lines.append(f" Max Cons. Losses: {res.max_consecutive_losses} trades")
        lines.append("-" * 80)
        lines.append(" SESSION BREAKDOWN (UTC)")
        lines.append(
            f" {'Session':<20} {'Trades':<8} {'Win Rate':<11} {'Expectancy':<15} {'Net Profit':<12}"
        )
        lines.append("-" * 80)

        for s_name, data in res.session_metrics.items():
            wr_str = f"{data['win_rate']:.1f}%" if data["trades"] > 0 else "--"
            exp_str = f"{data['expectancy_r']:+.2f} R" if data["trades"] > 0 else "--"
            pnl_sign = "+" if data["net_profit"] >= 0 else ""
            pnl_str = f"{pnl_sign}${data['net_profit']:,.2f}" if data["trades"] > 0 else "$0.00"
            lines.append(
                f" {s_name:<20} {data['trades']:<8} {wr_str:<11} {exp_str:<15} {pnl_str:<12}"
            )

        lines.append("=" * 80)
        return "\n".join(lines)
