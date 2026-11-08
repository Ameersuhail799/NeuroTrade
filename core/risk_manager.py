"""
Portfolio Risk Management & Guardrailed Execution for Level 6.

Enforces strict mathematical position sizing, daily equity circuit breakers,
and position exposure limits. No automated order placement.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RiskProfile:
    """
    Institutional risk parameters.
    """
    max_daily_drawdown_pct: float = 2.0
    max_positions_per_symbol: int = 1
    max_total_positions: int = 2
    default_risk_pct: float = 1.0
    max_risk_pct: float = 2.0
    min_risk_pct: float = 0.1


class RiskManager:
    """
    Enforces risk guardrails before order pre-fill or manual submission.
    """

    def __init__(self, profile: Optional[RiskProfile] = None):
        self.profile = profile or RiskProfile()

    @staticmethod
    def calculate_lot_size(
        equity: float,
        risk_pct: float,
        stop_distance_price: float,
        contract_info: Dict[str, Any],
        raise_on_below_min: bool = True,
    ) -> float:
        """
        Calculate mathematical lot size based on equity risk, stop distance,
        and broker contract specifications.

        Parameters:
        -----------
        equity: Current account balance/equity in quote/account currency.
        risk_pct: Percentage of equity to risk (e.g. 1.0 for 1%).
        stop_distance_price: Distance in price between entry and stop loss.
        contract_info: Broker contract specification dictionary containing:
            - point (float)
            - tick_value or trade_tick_value (float, optional)
            - contract_size (float, optional)
            - volume_step (float, default 0.01)
            - volume_min (float, default 0.01)
            - volume_max (float, default 100.0)
        raise_on_below_min: If True, raises ValueError when the calculated lot size
            is less than volume_min. If False, returns 0.0.

        Returns:
        --------
        Floored lot size rounded to volume_step, clamped between volume_min and volume_max.
        """
        if equity <= 0.0:
            raise ValueError(f"Equity must be positive: {equity}")
        if risk_pct <= 0.0:
            raise ValueError(f"Risk percentage must be positive: {risk_pct}")
        if stop_distance_price <= 0.0:
            raise ValueError(f"Stop distance must be positive: {stop_distance_price}")

        risk_dollars = equity * (risk_pct / 100.0)
        point = float(contract_info.get("point", 0.01))
        if point <= 0.0:
            raise ValueError(f"Invalid point value: {point}")

        ticks = stop_distance_price / point
        if ticks <= 0.0:
            raise ValueError(f"Calculated ticks must be positive: {ticks}")

        # Tick value or contract size fallback
        tick_value = contract_info.get("tick_value") or contract_info.get("trade_tick_value")
        if tick_value is not None and float(tick_value) > 0.0:
            tick_value_per_lot = float(tick_value)
        else:
            contract_size = float(contract_info.get("contract_size", 100000.0))
            tick_value_per_lot = point * contract_size

        if tick_value_per_lot <= 0.0:
            raise ValueError(f"Invalid tick value: {tick_value_per_lot}")

        raw_volume = risk_dollars / (ticks * tick_value_per_lot)

        volume_step = float(contract_info.get("volume_step", 0.01))
        volume_min = float(contract_info.get("volume_min", 0.01))
        volume_max = float(contract_info.get("volume_max", 100.0))

        if volume_step <= 0.0:
            volume_step = 0.01

        # Strictly floor to avoid increasing risk beyond target
        steps = math.floor(raw_volume / volume_step + 1e-9)
        calculated_volume = round(steps * volume_step, 6)

        if calculated_volume < volume_min:
            if raise_on_below_min:
                raise ValueError(
                    f"Calculated volume {calculated_volume:.2f} is below broker minimum {volume_min:.2f}. "
                    f"Increase account equity, widen stop distance, or increase risk percentage."
                )
            return 0.0

        if calculated_volume > volume_max:
            calculated_volume = volume_max

        return calculated_volume

    @staticmethod
    def check_daily_drawdown_limit(
        starting_daily_equity: float,
        current_equity: float,
        max_loss_pct: float = 2.0,
    ) -> bool:
        """
        Circuit breaker check: Returns False (blocked) if current equity represents
        a loss >= max_loss_pct of starting daily equity.
        """
        if starting_daily_equity <= 0.0:
            return False

        loss_dollars = starting_daily_equity - current_equity
        loss_pct = (loss_dollars / starting_daily_equity) * 100.0

        if loss_pct >= max_loss_pct:
            return False

        return True

    @staticmethod
    def check_max_open_positions(
        current_positions: List[Any],
        symbol: str,
        max_per_symbol: int = 1,
        max_total: int = 2,
    ) -> bool:
        """
        Blocks opening new positions if total positions or symbol-specific
        positions exceed maximum configured limits.
        """
        if len(current_positions) >= max_total:
            return False

        clean_sym = symbol.strip().upper()
        matching = 0

        for pos in current_positions:
            pos_sym = ""
            if isinstance(pos, dict):
                pos_sym = str(pos.get("symbol", "")).strip().upper()
            elif hasattr(pos, "symbol"):
                pos_sym = str(getattr(pos, "symbol", "")).strip().upper()

            if not pos_sym:
                continue

            # Direct match, prefix match (broker suffixes), or alias
            if (
                pos_sym == clean_sym
                or pos_sym.startswith(clean_sym)
                or clean_sym.startswith(pos_sym)
            ):
                matching += 1

        if matching >= max_per_symbol:
            return False

        return True

    def validate_pre_order(
        self,
        symbol: str,
        equity: float,
        starting_daily_equity: float,
        current_positions: List[Any],
        risk_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive pre-trade validation check.
        Returns a dict with 'allowed': bool and 'reasons': List[str].
        """
        reasons = []
        target_risk = risk_pct if risk_pct is not None else self.profile.default_risk_pct

        if target_risk > self.profile.max_risk_pct:
            reasons.append(
                f"Requested risk {target_risk:.1f}% exceeds maximum allowed {self.profile.max_risk_pct:.1f}%."
            )

        if not self.check_daily_drawdown_limit(
            starting_daily_equity, equity, self.profile.max_daily_drawdown_pct
        ):
            reasons.append(
                f"Daily drawdown circuit breaker tripped (loss >= {self.profile.max_daily_drawdown_pct:.1f}%)."
            )

        if not self.check_max_open_positions(
            current_positions,
            symbol,
            self.profile.max_positions_per_symbol,
            self.profile.max_total_positions,
        ):
            reasons.append(
                f"Position limit exceeded (max {self.profile.max_positions_per_symbol} per symbol, {self.profile.max_total_positions} total)."
            )

        return {
            "allowed": len(reasons) == 0,
            "reasons": reasons,
            "target_risk_pct": target_risk,
        }
