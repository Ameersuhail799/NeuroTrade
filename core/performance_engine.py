"""
Performance engine for Part 8.

This module reconstructs closed trades from real MT5 history deals and
calculates honest performance metrics.

Important honesty constraints:
- DEMO only is enforced by the worker/connection layer.
- No backtest statistics are generated.
- No results are invented.
- Max drawdown here is based on the closed-trade PnL curve, not full
  account equity including deposits/withdrawals.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import MetaTrader5 as mt5


@dataclass
class ClosedTrade:
    position_id: int
    symbol: str
    direction: str
    volume: float
    open_time: Optional[datetime]
    close_time: Optional[datetime]
    net_profit: float
    deals_count: int


@dataclass
class PerformanceMetrics:
    symbol_filter: str
    days: int
    start_time: str
    end_time: str

    account_login: int
    account_server: str
    account_currency: str

    total_trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: Optional[float]

    total_net: float
    gross_profit: float
    gross_loss: float
    profit_factor: Optional[float]

    expectancy: Optional[float]
    avg_win: Optional[float]
    avg_loss: Optional[float]

    max_drawdown_money: float

    long_trades: int
    short_trades: int
    long_net: float
    short_net: float

    avg_duration_seconds: Optional[float]

    equity_curve: List[float] = field(default_factory=list)
    trades: List[ClosedTrade] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def build_closed_trades(deals) -> Tuple[List[ClosedTrade], List[str]]:
    """
    Reconstruct closed trades from MT5 history deals.

    This implementation is intentionally conservative:
    - It groups deals by position_id.
    - It requires at least one exit-type deal.
    - It skips positions that still appear partially open.
    - It uses profit + swap + commission as net trade PnL.

    Broker deal conventions can vary, so this module reports warnings
    instead of silently inventing trades.
    """
    warnings: List[str] = []

    if deals is None:
        return [], ["MT5 returned no history deals."]

    if len(deals) == 0:
        return [], []

    buy_type = int(getattr(mt5, "DEAL_TYPE_BUY", 0))
    sell_type = int(getattr(mt5, "DEAL_TYPE_SELL", 1))
    allowed_deal_types = {buy_type, sell_type}

    entry_in = int(getattr(mt5, "DEAL_ENTRY_IN", 0))
    entry_out = int(getattr(mt5, "DEAL_ENTRY_OUT", 1))
    entry_inout = int(getattr(mt5, "DEAL_ENTRY_INOUT", 2))
    entry_out_by = int(getattr(mt5, "DEAL_ENTRY_OUT_BY", 3))
    exit_entries = {entry_out, entry_inout, entry_out_by}

    sorted_deals = sorted(
        deals,
        key=lambda d: (
            int(getattr(d, "time", 0) or 0),
            int(getattr(d, "time_msc", 0) or 0),
        ),
    )

    groups: Dict[int, Dict[str, Any]] = {}
    missing_position_id = 0
    skipped_partial_open = 0

    for deal in sorted_deals:
        try:
            deal_type = int(getattr(deal, "type", -1))
            entry = int(getattr(deal, "entry", -1))
        except Exception:
            continue

        if deal_type not in allowed_deal_types:
            continue

        position_id = int(getattr(deal, "position_id", 0) or 0)
        if position_id == 0:
            position_id = int(getattr(deal, "order", 0) or 0)

        if position_id == 0:
            missing_position_id += 1
            continue

        if position_id not in groups:
            groups[position_id] = {
                "symbol": "",
                "direction": None,
                "entry_volume": 0.0,
                "exit_volume": 0.0,
                "net": 0.0,
                "has_exit": False,
                "deals_count": 0,
                "first_time": None,
                "open_time": None,
                "close_time": None,
                "last_time": None,
            }

        group = groups[position_id]
        group["deals_count"] += 1

        symbol = str(getattr(deal, "symbol", "") or "")
        if symbol and not group["symbol"]:
            group["symbol"] = symbol

        deal_time = datetime.fromtimestamp(int(getattr(deal, "time", 0) or 0))

        if group["first_time"] is None:
            group["first_time"] = deal_time

        group["last_time"] = deal_time

        profit = float(getattr(deal, "profit", 0.0) or 0.0)
        swap = float(getattr(deal, "swap", 0.0) or 0.0)
        commission = float(getattr(deal, "commission", 0.0) or 0.0)
        volume = float(getattr(deal, "volume", 0.0) or 0.0)

        group["net"] += profit + swap + commission

        if entry == entry_in:
            group["entry_volume"] += volume

            if group["direction"] is None:
                group["direction"] = "LONG" if deal_type == buy_type else "SHORT"

            if group["open_time"] is None:
                group["open_time"] = deal_time

        elif entry in exit_entries:
            group["has_exit"] = True
            group["exit_volume"] += volume

            if group["direction"] is None:
                # Closing a long usually creates a sell deal.
                # Closing a short usually creates a buy deal.
                group["direction"] = "LONG" if deal_type == sell_type else "SHORT"

            group["close_time"] = deal_time

        else:
            # Unknown entry type. Keep the PnL but do not infer volume.
            pass

    trades: List[ClosedTrade] = []

    for position_id, group in groups.items():
        if not group["has_exit"]:
            continue

        remaining_volume = group["entry_volume"] - group["exit_volume"]

        # If we saw entry volume and it has not been fully exited, treat the
        # position as still open or partially open and skip it.
        if group["entry_volume"] > 1e-12 and remaining_volume > 1e-8:
            skipped_partial_open += 1
            continue

        direction = group["direction"] or "UNKNOWN"
        open_time = group["open_time"] or group["first_time"]
        close_time = group["close_time"] or group["last_time"]
        volume = max(group["entry_volume"], group["exit_volume"])

        trades.append(
            ClosedTrade(
                position_id=int(position_id),
                symbol=group["symbol"],
                direction=direction,
                volume=float(volume),
                open_time=open_time,
                close_time=close_time,
                net_profit=float(group["net"]),
                deals_count=int(group["deals_count"]),
            )
        )

    if missing_position_id > 0:
        warnings.append(
            f"{missing_position_id} history deals had no usable position_id "
            "and were excluded."
        )

    if skipped_partial_open > 0:
        warnings.append(
            f"{skipped_partial_open} position groups appear partially open "
            "and were excluded."
        )

    trades.sort(
        key=lambda t: t.close_time or datetime.min,
        reverse=False,
    )

    return trades, warnings


def calculate_metrics(
    trades: List[ClosedTrade],
    warnings: List[str] = None,
    symbol_filter: str = "ALL",
    days: int = 30,
    start_time: str = "",
    end_time: str = "",
    account: Dict[str, Any] = None,
) -> PerformanceMetrics:
    """
    Calculate performance metrics from closed trades.
    """
    warnings = list(warnings or [])
    account = dict(account or {})

    trades_sorted = sorted(
        trades,
        key=lambda t: t.close_time or datetime.min,
    )

    equity_curve: List[float] = [0.0]
    cumulative = 0.0
    peak = 0.0
    max_drawdown_money = 0.0

    wins = 0
    losses = 0
    breakevens = 0

    gross_profit = 0.0
    gross_loss = 0.0
    total_net = 0.0

    long_trades = 0
    short_trades = 0
    long_net = 0.0
    short_net = 0.0

    durations: List[float] = []

    epsilon = 1e-8

    for trade in trades_sorted:
        net = float(trade.net_profit)

        cumulative += net
        equity_curve.append(float(cumulative))

        if cumulative > peak:
            peak = cumulative

        drawdown = peak - cumulative
        if drawdown > max_drawdown_money:
            max_drawdown_money = float(drawdown)

        total_net += net

        if net > epsilon:
            wins += 1
            gross_profit += net
        elif net < -epsilon:
            losses += 1
            gross_loss += abs(net)
        else:
            breakevens += 1

        if trade.direction == "LONG":
            long_trades += 1
            long_net += net
        elif trade.direction == "SHORT":
            short_trades += 1
            short_net += net

        if trade.open_time is not None and trade.close_time is not None:
            duration = (trade.close_time - trade.open_time).total_seconds()
            if duration >= 0:
                durations.append(duration)

    total_trades = len(trades_sorted)

    win_rate = None
    if total_trades > 0:
        win_rate = float(wins / total_trades * 100.0)

    profit_factor = None
    if gross_loss > epsilon:
        profit_factor = float(gross_profit / gross_loss)
    elif gross_profit > epsilon:
        # No losing trades. Keep None and format as infinity with a warning.
        profit_factor = None

    expectancy = None
    if total_trades > 0:
        expectancy = float(total_net / total_trades)

    avg_win = None
    if wins > 0:
        avg_win = float(gross_profit / wins)

    avg_loss = None
    if losses > 0:
        avg_loss = float(gross_loss / losses)

    avg_duration_seconds = None
    if durations:
        avg_duration_seconds = float(sum(durations) / len(durations))

    if gross_loss <= epsilon and gross_profit > epsilon:
        warnings.append(
            "Profit factor is infinite because there were no losing trades. "
            "This is not robust evidence of edge."
        )

    return PerformanceMetrics(
        symbol_filter=str(symbol_filter),
        days=int(days),
        start_time=str(start_time),
        end_time=str(end_time),

        account_login=int(account.get("login", 0)),
        account_server=str(account.get("server", "")),
        account_currency=str(account.get("currency", "")),

        total_trades=int(total_trades),
        wins=int(wins),
        losses=int(losses),
        breakevens=int(breakevens),
        win_rate=win_rate,

        total_net=float(total_net),
        gross_profit=float(gross_profit),
        gross_loss=float(gross_loss),
        profit_factor=profit_factor,

        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,

        max_drawdown_money=float(max_drawdown_money),

        long_trades=int(long_trades),
        short_trades=int(short_trades),
        long_net=float(long_net),
        short_net=float(short_net),

        avg_duration_seconds=avg_duration_seconds,

        equity_curve=equity_curve,
        trades=trades_sorted,
        warnings=warnings,
    )


def _format_money(value: Optional[float], currency: str) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f} {currency}".strip()


def _format_optional(value: Optional[float], pattern: str = "{:.2f}") -> str:
    if value is None:
        return "N/A"
    return pattern.format(value)


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "N/A"

    minutes = seconds / 60.0

    if minutes < 90.0:
        return f"{minutes:.1f} minutes"

    hours = minutes / 60.0

    if hours < 48.0:
        return f"{hours:.1f} hours"

    days = hours / 24.0
    return f"{days:.1f} days"


def _format_profit_factor(metrics: PerformanceMetrics) -> str:
    if metrics.total_trades == 0:
        return "N/A"

    if metrics.gross_loss > 1e-8:
        return f"{metrics.gross_profit / metrics.gross_loss:.2f}"

    if metrics.gross_profit > 1e-8:
        return "∞ (no losing trades)"

    return "0.00"


def format_report(metrics: PerformanceMetrics) -> str:
    """
    Format the performance dashboard report.
    """
    lines = []

    lines.append("NeuroTrade AI Performance Dashboard")
    lines.append("DEMO account history only. No backtest results.")
    lines.append("")

    lines.append(
        f"Account: {metrics.account_login or '--'} | "
        f"Server: {metrics.account_server or '--'} | "
        f"Currency: {metrics.account_currency or '--'}"
    )

    lines.append(
        f"Period: last {metrics.days} days "
        f"({metrics.start_time} to {metrics.end_time})"
    )

    lines.append(f"Symbol filter: {metrics.symbol_filter}")
    lines.append("")

    if metrics.warnings:
        lines.append("Warnings:")
        for warning in metrics.warnings:
            lines.append(f"  {warning}")
        lines.append("")

    if metrics.total_trades == 0:
        lines.append("No closed trades were found for the selected filter.")
        lines.append("")
        lines.append(
            "If you expected trades here, make sure the MT5 terminal has "
            "loaded account history for the selected period."
        )
        return "\n".join(lines)

    lines.append("Core metrics:")
    lines.append(f"  Closed trades: {metrics.total_trades}")

    win_rate_text = _format_optional(metrics.win_rate, "{:.1f}%")
    lines.append(
        f"  Win rate: {win_rate_text} "
        f"({metrics.wins}W / {metrics.losses}L / {metrics.breakevens}BE)"
    )

    lines.append(f"  Total net PnL: {_format_money(metrics.total_net, metrics.account_currency)}")
    lines.append(f"  Gross profit: {_format_money(metrics.gross_profit, metrics.account_currency)}")
    lines.append(f"  Gross loss: {_format_money(-metrics.gross_loss, metrics.account_currency)}")
    lines.append(f"  Profit factor: {_format_profit_factor(metrics)}")

    expectancy_text = _format_money(metrics.expectancy, metrics.account_currency)
    lines.append(f"  Expectancy: {expectancy_text} per trade")

    avg_win_text = _format_money(metrics.avg_win, metrics.account_currency)
    avg_loss_text = _format_money(-metrics.avg_loss if metrics.avg_loss is not None else None, metrics.account_currency)

    lines.append(f"  Average win: {avg_win_text}")
    lines.append(f"  Average loss: {avg_loss_text}")

    lines.append(
        "  Max closed-trade drawdown: "
        f"{_format_money(metrics.max_drawdown_money, metrics.account_currency)}"
    )

    lines.append("")
    lines.append("Direction breakdown:")
    lines.append(
        f"  Long trades: {metrics.long_trades} | "
        f"Net: {_format_money(metrics.long_net, metrics.account_currency)}"
    )
    lines.append(
        f"  Short trades: {metrics.short_trades} | "
        f"Net: {_format_money(metrics.short_net, metrics.account_currency)}"
    )

    lines.append("")
    lines.append("Timing:")
    lines.append(f"  Average trade duration: {_format_duration(metrics.avg_duration_seconds)}")

    lines.append("")
    lines.append("Honesty notes:")
    lines.append("  - Win rate alone is not success.")
    lines.append("  - Profit factor, expectancy and drawdown must be considered together.")
    lines.append("  - Results are real MT5 demo history, not a simulation.")
    lines.append("  - Spread, commission and swap are included as reported by MT5.")
    lines.append("  - Max drawdown here is based on closed-trade PnL, not full balance equity.")

    return "\n".join(lines)