"""Purged & Embargoed Rolling Walk-Forward Validator and 5-Stage Ablation Study.

Enforces zero outcome overlap between walk-forward folds and measures the marginal
impact of each v2 filter gate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from core.intraday_backtester import BacktestConfig, BacktestResult, IntradayBacktester
from core.market_regimes import IntradayStrategyConfig


@dataclass
class WalkForwardConfig:
    """Configuration for purged rolling walk-forward validation."""

    n_folds: int = 4
    embargo_m5_bars: int = 48  # 4-hour embargo buffer between folds


@dataclass
class WalkForwardFoldResult:
    """Metrics for an individual out-of-sample walk-forward fold."""

    fold_index: int
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    total_bars: int
    total_trades: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    net_profit: float
    max_drawdown_pct: float


@dataclass
class WalkForwardSummary:
    """Aggregated scorecard across all walk-forward validation folds."""

    symbol: str
    total_folds: int
    active_folds: int
    positive_folds: int
    consistency_ratio: float
    mean_expectancy_r: float
    total_trades: int
    total_net_profit: float
    worst_fold_drawdown_pct: float
    folds: List[WalkForwardFoldResult]


@dataclass
class AblationRow:
    """Single stage scorecard in the 5-stage filter ablation study."""

    stage_name: str
    total_trades: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_pct: float
    net_profit: float


class WalkForwardValidator:
    """Validates intraday strategy robustness across out-of-sample folds and ablation stages."""

    @classmethod
    def run_walk_forward(
        cls,
        h1: pd.DataFrame,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        symbol: str = "XAUUSD",
        backtest_config: Optional[BacktestConfig] = None,
        strategy_config: Optional[IntradayStrategyConfig] = None,
        wf_config: Optional[WalkForwardConfig] = None,
    ) -> WalkForwardSummary:
        """Execute purged and embargoed rolling out-of-sample walk-forward validation."""
        cfg = copy.deepcopy(backtest_config or BacktestConfig(symbol=symbol))
        strat_cfg = copy.deepcopy(strategy_config or IntradayStrategyConfig())
        wf = wf_config or WalkForwardConfig()

        # Sort and ensure datetime
        h1 = h1.sort_values("time").reset_index(drop=True)
        m15 = m15.sort_values("time").reset_index(drop=True)
        m5 = m5.sort_values("time").reset_index(drop=True)

        h1["time"] = pd.to_datetime(h1["time"])
        m15["time"] = pd.to_datetime(m15["time"])
        m5["time"] = pd.to_datetime(m5["time"])

        # Precompute candle completion times
        h1_close_times = (h1["time"] + pd.Timedelta(hours=1)).values
        m15_close_times = (m15["time"] + pd.Timedelta(minutes=15)).values
        m5_close_times = m5["time"] + pd.Timedelta(minutes=5)

        # Find first M5 bar where indicator warm-up is satisfied
        min_h1_req = 220
        min_m15_req = 60
        min_m5_req = 60

        warmup_m5_idx = None
        for i in range(len(m5)):
            cur_m5_close_val = m5_close_times.iloc[i].to_datetime64()
            h1_idx = np.searchsorted(h1_close_times, cur_m5_close_val, side="right") - 1
            m15_idx = np.searchsorted(m15_close_times, cur_m5_close_val, side="right") - 1
            if h1_idx >= min_h1_req - 1 and m15_idx >= min_m15_req - 1 and i >= min_m5_req - 1:
                warmup_m5_idx = i
                break

        if warmup_m5_idx is None or warmup_m5_idx >= len(m5) - 20:
            raise ValueError(
                f"Insufficient historical candle data for walk-forward validation. "
                f"H1 bars: {len(h1)}, M15 bars: {len(m15)}, M5 bars: {len(m5)}."
            )

        eval_bars_total = len(m5) - warmup_m5_idx
        n_folds = max(1, wf.n_folds)
        embargo = max(0, wf.embargo_m5_bars)

        # Net bars available for evaluation across folds
        net_eval_bars = eval_bars_total - (n_folds - 1) * embargo
        if net_eval_bars < n_folds * 10:
            # Not enough bars for requested embargo; scale back embargo
            embargo = max(0, (eval_bars_total - n_folds * 10) // max(1, n_folds - 1))
            net_eval_bars = eval_bars_total - (n_folds - 1) * embargo

        fold_bar_len = max(5, net_eval_bars // n_folds)

        folds: List[WalkForwardFoldResult] = []
        cur_start_idx = warmup_m5_idx

        for k in range(n_folds):
            if k == n_folds - 1:
                cur_end_idx = len(m5) - 1
            else:
                cur_end_idx = min(len(m5) - 1, cur_start_idx + fold_bar_len - 1)

            if cur_start_idx >= len(m5) or cur_start_idx > cur_end_idx:
                break

            fold_start_time = m5.iloc[cur_start_idx]["time"]
            fold_end_time = m5.iloc[cur_end_idx]["time"]

            # Run backtester preserving full prior history for indicator warm-up
            # but restricting signal execution strictly to [fold_start_time, fold_end_time]
            bt = IntradayBacktester(config=cfg, strategy_config=strat_cfg)
            res = bt.run(
                h1=h1,
                m15=m15,
                m5=m5,
                eval_start_time=fold_start_time,
                eval_end_time=fold_end_time,
            )

            folds.append(
                WalkForwardFoldResult(
                    fold_index=k + 1,
                    start_time=fold_start_time,
                    end_time=fold_end_time,
                    total_bars=res.total_bars_m5,
                    total_trades=res.total_trades,
                    win_rate=res.win_rate,
                    expectancy_r=res.expectancy_r,
                    profit_factor=res.profit_factor,
                    net_profit=res.net_profit,
                    max_drawdown_pct=res.max_drawdown_pct,
                )
            )

            # Advance with embargo buffer to eliminate outcome contamination
            cur_start_idx = cur_end_idx + 1 + embargo

        active_folds = sum(1 for f in folds if f.total_trades > 0)
        positive_folds = sum(1 for f in folds if f.net_profit > 0)
        consistency_ratio = (
            round((positive_folds / active_folds) * 100.0, 1) if active_folds > 0 else 0.0
        )
        mean_exp_r = (
            round(float(np.mean([f.expectancy_r for f in folds if f.total_trades > 0])), 2)
            if active_folds > 0
            else 0.0
        )
        total_trades = sum(f.total_trades for f in folds)
        total_net_profit = round(sum(f.net_profit for f in folds), 2)
        worst_dd_pct = max((f.max_drawdown_pct for f in folds), default=0.0)

        return WalkForwardSummary(
            symbol=symbol,
            total_folds=len(folds),
            active_folds=active_folds,
            positive_folds=positive_folds,
            consistency_ratio=consistency_ratio,
            mean_expectancy_r=mean_exp_r,
            total_trades=total_trades,
            total_net_profit=total_net_profit,
            worst_fold_drawdown_pct=worst_dd_pct,
            folds=folds,
        )

    @classmethod
    def run_ablation_study(
        cls,
        h1: pd.DataFrame,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        symbol: str = "XAUUSD",
        backtest_config: Optional[BacktestConfig] = None,
    ) -> List[AblationRow]:
        """Run 5-stage ablation study measuring incremental gate contributions."""
        base_cfg = copy.deepcopy(backtest_config or BacktestConfig(symbol=symbol))

        stages = [
            (
                "1_Baseline_v1",
                IntradayStrategyConfig(
                    enable_rollover_block=False,
                    restrict_to_prime_sessions=False,
                    block_asian_breakouts=False,
                    enable_spread_filter=False,
                    enable_regime_filter=False,
                ),
                False,  # scale_out_tp1
            ),
            (
                "2_Plus_Session_Rollover",
                IntradayStrategyConfig(
                    enable_rollover_block=True,
                    restrict_to_prime_sessions=False,
                    block_asian_breakouts=True,
                    enable_spread_filter=False,
                    enable_regime_filter=False,
                ),
                False,
            ),
            (
                "3_Plus_Spread_Gate",
                IntradayStrategyConfig(
                    enable_rollover_block=True,
                    restrict_to_prime_sessions=False,
                    block_asian_breakouts=True,
                    enable_spread_filter=True,
                    enable_regime_filter=False,
                ),
                False,
            ),
            (
                "4_Full_v2_Regime_Gate",
                IntradayStrategyConfig(
                    enable_rollover_block=True,
                    restrict_to_prime_sessions=False,
                    block_asian_breakouts=True,
                    enable_spread_filter=True,
                    enable_regime_filter=True,
                ),
                False,
            ),
            (
                "5_Full_v2_ScaleOut_TP1_BE",
                IntradayStrategyConfig(
                    enable_rollover_block=True,
                    restrict_to_prime_sessions=False,
                    block_asian_breakouts=True,
                    enable_spread_filter=True,
                    enable_regime_filter=True,
                ),
                True,
            ),
        ]

        rows: List[AblationRow] = []

        for stage_name, strat_cfg, scale_out in stages:
            cfg = copy.deepcopy(base_cfg)
            cfg.scale_out_tp1 = scale_out

            bt = IntradayBacktester(config=cfg, strategy_config=strat_cfg)
            res = bt.run(h1, m15, m5)

            rows.append(
                AblationRow(
                    stage_name=stage_name,
                    total_trades=res.total_trades,
                    win_rate=res.win_rate,
                    expectancy_r=res.expectancy_r,
                    profit_factor=res.profit_factor,
                    max_drawdown_pct=res.max_drawdown_pct,
                    net_profit=res.net_profit,
                )
            )

        return rows

    @classmethod
    def format_walk_forward_report(cls, summary: WalkForwardSummary) -> str:
        """Format clean tabular text report for walk-forward validation results."""
        lines = []
        lines.append("=" * 80)
        lines.append("          NEUROTRADE AI - ROLLING WALK-FORWARD VALIDATION SCORECARD          ")
        lines.append("=" * 80)
        lines.append(f" Instrument:          {summary.symbol}")
        lines.append(f" Total Folds:         {summary.total_folds} (Active: {summary.active_folds})")
        lines.append(f" Positive Folds:      {summary.positive_folds} / {summary.active_folds}")
        lines.append(f" Consistency Ratio:   {summary.consistency_ratio:.1f}%")
        sign = "+" if summary.mean_expectancy_r >= 0 else ""
        lines.append(f" Mean Expectancy:     {sign}{summary.mean_expectancy_r:.2f} R per trade")
        lines.append(f" Total Trades:        {summary.total_trades}")
        pnl_sign = "+" if summary.total_net_profit >= 0 else ""
        lines.append(f" Total Net Profit:    {pnl_sign}${summary.total_net_profit:,.2f}")
        lines.append(f" Worst Fold Drawdown: {summary.worst_fold_drawdown_pct:.2f}%")
        lines.append("-" * 80)
        lines.append(
            f" {'Fold':<6} {'Start Date':<12} {'End Date':<12} {'Trades':<8} "
            f"{'WinRate':<9} {'Expectancy':<12} {'PF':<6} {'Net Profit':<12}"
        )
        lines.append("-" * 80)

        for f in summary.folds:
            s_dt = f.start_time.strftime("%Y-%m-%d")
            e_dt = f.end_time.strftime("%Y-%m-%d")
            wr_str = f"{f.win_rate:.1f}%" if f.total_trades > 0 else "--"
            exp_str = f"{f.expectancy_r:+.2f} R" if f.total_trades > 0 else "--"
            pf_str = f"{f.profit_factor:.2f}" if f.total_trades > 0 else "--"
            f_pnl_sign = "+" if f.net_profit >= 0 else ""
            pnl_str = f"{f_pnl_sign}${f.net_profit:,.2f}"
            lines.append(
                f" #{f.fold_index:<5} {s_dt:<12} {e_dt:<12} {f.total_trades:<8} "
                f"{wr_str:<9} {exp_str:<12} {pf_str:<6} {pnl_str:<12}"
            )

        lines.append("=" * 80)
        return "\n".join(lines)

    @classmethod
    def format_ablation_report(cls, rows: List[AblationRow]) -> str:
        """Format clean tabular text report for 5-stage ablation study."""
        lines = []
        lines.append("=" * 85)
        lines.append("               NEUROTRADE AI - 5-STAGE STRATEGY ABLATION STUDY               ")
        lines.append("=" * 85)
        lines.append(
            f" {'Stage Name':<28} {'Trades':<8} {'WinRate':<9} {'Expectancy':<12} "
            f"{'PF':<6} {'MaxDD%':<8} {'Net Profit':<12}"
        )
        lines.append("-" * 85)

        for r in rows:
            wr_str = f"{r.win_rate:.1f}%" if r.total_trades > 0 else "--"
            exp_str = f"{r.expectancy_r:+.2f} R" if r.total_trades > 0 else "--"
            pf_str = f"{r.profit_factor:.2f}" if r.total_trades > 0 else "--"
            dd_str = f"{r.max_drawdown_pct:.1f}%"
            pnl_sign = "+" if r.net_profit >= 0 else ""
            pnl_str = f"{pnl_sign}${r.net_profit:,.2f}"
            lines.append(
                f" {r.stage_name:<28} {r.total_trades:<8} {wr_str:<9} {exp_str:<12} "
                f"{pf_str:<6} {dd_str:<8} {pnl_str:<12}"
            )

        lines.append("=" * 85)
        return "\n".join(lines)
