"""
Demo trade executor for NeuroTrade AI.

Part 6 scope:
- Manual demo order execution only.
- No real-money orders.
- No automated trading.
- No persistence.
- No backtesting.
- All results come from real MT5 order_send responses.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime
import math

import MetaTrader5 as mt5

from core.mt5_connector import MT5Connector


@dataclass
class TradeExecutionResult:
    success: bool
    action: str
    symbol: str
    ticket: int
    retcode: int
    message: str
    price: float
    volume: float
    sl: float
    tp: float
    notes: List[str] = field(default_factory=list)


class DemoTradeExecutor:
    """
    Executes manual demo trades through MT5.

    Safety rules enforced:
    - MT5 must initialize successfully.
    - Account must be DEMO.
    - Algo Trading must be allowed in the terminal.
    - Symbol must be resolved from the broker.
    - Volume and price are normalized according to symbol rules.
    """

    MAGIC = 20260601
    COMMENT = "NeuroTradeAI DEMO"
    DEFAULT_DEVIATION = 100

    @staticmethod
    def _success_codes():
        # Only completed fills are treated as success. PLACED is pending/not filled.
        return {
            getattr(mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }

    @staticmethod
    def _invalid_filling_codes():
        return {
            getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030),
            getattr(mt5, "TRADE_RETCODE_INVALID_FILLING", 10030),
        }

    def _filling_candidates(self):
        candidates = []

        for name in (
            "ORDER_FILLING_IOC",
            "ORDER_FILLING_FOK",
            "ORDER_FILLING_RETURN",
        ):
            value = getattr(mt5, name, None)
            if value is not None and value not in candidates:
                candidates.append(value)

        if not candidates:
            candidates = [1, 0, 2]

        return candidates

    def _initialize(self):
        if not MT5Connector.initialize():
            raise RuntimeError(
                "MT5 initialization failed. "
                "Ensure the MT5 terminal is running and logged into a DEMO account."
            )

        try:
            account = mt5.account_info()
            if not account:
                raise RuntimeError("MT5 account info unavailable.")

            demo_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
            if int(account.trade_mode) != demo_mode:
                raise RuntimeError(
                    "DEMO ONLY rule enforced. "
                    "This executor refuses real or contest accounts."
                )

            terminal = mt5.terminal_info()
            if not terminal:
                raise RuntimeError("MT5 terminal info unavailable.")

            if not bool(terminal.trade_allowed):
                raise RuntimeError(
                    "Algo Trading is disabled in the MT5 terminal. "
                    "Enable the Algo Trading button in MT5."
                )

        except Exception:
            MT5Connector.shutdown()
            raise

    def _shutdown(self):
        MT5Connector.shutdown()

    @staticmethod
    def _ensure_symbol_tradable(symbol_info):
        trade_mode = getattr(symbol_info, "trade_mode", None)
        disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)

        if trade_mode is not None and int(trade_mode) == int(disabled_mode):
            raise RuntimeError("Symbol trading is disabled by the broker.")

    @staticmethod
    def _contract_dict(symbol_info) -> Dict[str, Any]:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        if point <= 0.0:
            raise RuntimeError("Symbol point is invalid.")

        digits = int(getattr(symbol_info, "digits", 2) or 2)

        volume_min = float(getattr(symbol_info, "volume_min", 0.01) or 0.01)
        volume_max = float(getattr(symbol_info, "volume_max", 100.0) or 100.0)
        volume_step = float(getattr(symbol_info, "volume_step", 0.01) or 0.01)

        if volume_step <= 0.0:
            volume_step = 0.01

        stops_level = int(getattr(symbol_info, "trade_stops_level", 0) or 0)

        return {
            "symbol": symbol_info.name,
            "point": point,
            "digits": digits,
            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,
            "stops_level": stops_level,
        }

    @staticmethod
    def round_price(price: float, digits: int) -> float:
        return float(round(float(price), int(digits)))

    @staticmethod
    def normalize_volume(
        requested_volume: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> float:
        requested_volume = float(requested_volume)

        if requested_volume <= 0.0:
            raise RuntimeError("Requested volume must be greater than zero.")

        if volume_step <= 0.0:
            raise RuntimeError("Symbol volume step is invalid.")

        if requested_volume < volume_min - 1e-12:
            raise RuntimeError(
                f"Requested volume {requested_volume} is below broker minimum {volume_min}."
            )

        # Floor to volume_step to avoid rounding risk upward
        steps = math.floor((requested_volume + 1e-12) / volume_step)
        normalized = steps * volume_step
        normalized = float(f"{normalized:.8f}")

        if normalized < volume_min:
            raise RuntimeError(
                f"Requested volume {requested_volume} floored to {normalized}, "
                f"which is below broker minimum {volume_min}."
            )

        if normalized > volume_max:
            normalized = volume_max

        steps = math.floor((normalized + 1e-12) / volume_step)
        normalized = float(f"{steps * volume_step:.8f}")

        if normalized < volume_min or normalized > volume_max:
            raise RuntimeError(
                f"Normalized volume {normalized} is outside broker limits "
                f"{volume_min}-{volume_max}."
            )

        return normalized

    def _calculate_sl_tp(
        self,
        contract: Dict[str, Any],
        side: str,
        price: float,
        sl_points: int,
        tp_points: int,
    ):
        sl_points = int(sl_points)
        tp_points = int(tp_points)

        if sl_points < 0 or tp_points < 0:
            raise RuntimeError("SL/TP points cannot be negative.")

        digits = int(contract["digits"])
        point = float(contract["point"])
        stops_level = int(contract["stops_level"])
        min_distance_price = float(stops_level) * point

        sl_price = 0.0
        tp_price = 0.0

        if side == "buy":
            if sl_points > 0:
                candidate = price - sl_points * point
                if price - candidate < min_distance_price - 1e-12:
                    raise RuntimeError(
                        f"SL is too close. Minimum stop distance is "
                        f"{stops_level} points."
                    )

                sl_price = self.round_price(candidate, digits)
                if sl_price >= price:
                    raise RuntimeError("Buy SL must be below entry price.")

            if tp_points > 0:
                candidate = price + tp_points * point
                if candidate - price < min_distance_price - 1e-12:
                    raise RuntimeError(
                        f"TP is too close. Minimum stop distance is "
                        f"{stops_level} points."
                    )

                tp_price = self.round_price(candidate, digits)
                if tp_price <= price:
                    raise RuntimeError("Buy TP must be above entry price.")

        elif side == "sell":
            if sl_points > 0:
                candidate = price + sl_points * point
                if candidate - price < min_distance_price - 1e-12:
                    raise RuntimeError(
                        f"SL is too close. Minimum stop distance is "
                        f"{stops_level} points."
                    )

                sl_price = self.round_price(candidate, digits)
                if sl_price <= price:
                    raise RuntimeError("Sell SL must be above entry price.")

            if tp_points > 0:
                candidate = price - tp_points * point
                if price - candidate < min_distance_price - 1e-12:
                    raise RuntimeError(
                        f"TP is too close. Minimum stop distance is "
                        f"{stops_level} points."
                    )

                tp_price = self.round_price(candidate, digits)
                if tp_price >= price:
                    raise RuntimeError("Sell TP must be below entry price.")

        else:
            raise RuntimeError(f"Unsupported side: {side}")

        return sl_price, tp_price

    def _account_summary(self) -> Dict[str, Any]:
        account = mt5.account_info()
        if not account:
            raise RuntimeError("MT5 account info unavailable.")

        terminal = mt5.terminal_info()

        return {
            "login": int(account.login),
            "server": str(account.server),
            "balance": float(account.balance),
            "equity": float(account.equity),
            "currency": str(account.currency),
            "trade_allowed": bool(terminal.trade_allowed) if terminal else False,
            "account_mode": "DEMO",
        }

    def _contract_info(self, symbol: str) -> Dict[str, Any]:
        symbol_info = MT5Connector.get_symbol_info(symbol)
        if not symbol_info:
            raise RuntimeError(f"Could not resolve or select symbol {symbol}.")

        self._ensure_symbol_tradable(symbol_info)
        return self._contract_dict(symbol_info)

    def _positions(self, symbol: str) -> List[Dict[str, Any]]:
        contract = self._contract_info(symbol)
        positions = mt5.positions_get(symbol=contract["symbol"])

        if positions is None:
            raise RuntimeError(
                f"positions_get failed for {contract['symbol']}. "
                f"MT5 error: {mt5.last_error()}"
            )

        result = []
        buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)

        for position in positions:
            position_type = "BUY" if int(position.type) == int(buy_type) else "SELL"

            try:
                open_time = datetime.fromtimestamp(int(position.time)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                open_time = str(position.time)

            result.append(
                {
                    "ticket": int(position.ticket),
                    "symbol": str(position.symbol),
                    "type": position_type,
                    "volume": float(position.volume),
                    "open_price": float(position.price_open),
                    "sl": float(position.sl),
                    "tp": float(position.tp),
                    "profit": float(position.profit),
                    "swap": float(position.swap),
                    "comment": str(position.comment),
                    "time": open_time,
                }
            )

        return result

    def get_trading_context(self, symbol: str) -> Dict[str, Any]:
        """
        Refresh account, contract rules and open positions in one operation.
        """
        try:
            self._initialize()

            account = self._account_summary()
            contract = self._contract_info(symbol)
            positions = self._positions(symbol)

            return {
                "account": account,
                "contract": contract,
                "positions": positions,
            }

        finally:
            self._shutdown()

    def _send_order(self, request: Dict[str, Any]):
        candidates = self._filling_candidates()
        invalid_filling_codes = self._invalid_filling_codes()
        last_result = None

        for filling in candidates:
            current_request = dict(request)
            current_request["type_filling"] = filling

            result = mt5.order_send(current_request)

            if result is None:
                raise RuntimeError(
                    f"order_send returned None. MT5 error: {mt5.last_error()}"
                )

            if int(result.retcode) in self._success_codes():
                return result

            last_result = result

            if int(result.retcode) in invalid_filling_codes:
                continue

            break

        return last_result

    def _build_execution_result(
        self,
        result,
        action: str,
        symbol: str,
        request: Dict[str, Any],
        notes: List[str],
    ) -> TradeExecutionResult:
        success = int(result.retcode) in self._success_codes()

        comment = str(getattr(result, "comment", "") or "")
        message = (
            f"retcode={result.retcode}, comment={comment}, "
            f"deal={getattr(result, 'deal', 0)}, order={getattr(result, 'order', 0)}"
        )

        placed_code = getattr(mt5, "TRADE_RETCODE_PLACED", 10008)

        if success:
            message = f"Order filled. {message}"
        elif int(result.retcode) == int(placed_code):
            message = f"Order placed/pending (not filled yet). {message}"
        else:
            message = f"Order failed. {message}"

        ticket = int(getattr(result, "order", 0) or getattr(result, "deal", 0) or 0)

        price = float(getattr(result, "price", 0.0) or request.get("price", 0.0))
        volume = float(getattr(result, "volume", 0.0) or request.get("volume", 0.0))

        return TradeExecutionResult(
            success=success,
            action=action,
            symbol=symbol,
            ticket=ticket,
            retcode=int(result.retcode),
            message=message,
            price=price,
            volume=volume,
            sl=float(request.get("sl", 0.0)),
            tp=float(request.get("tp", 0.0)),
            notes=notes,
        )

    def open_market_position(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl_points: int,
        tp_points: int,
    ) -> TradeExecutionResult:
        """
        Open a manual demo market position.
        """
        side = str(side).lower()
        if side not in ("buy", "sell"):
            raise RuntimeError(f"Unsupported side: {side}")

        notes = []

        try:
            self._initialize()

            symbol_info = MT5Connector.get_symbol_info(symbol)
            if not symbol_info:
                raise RuntimeError(f"Could not resolve or select symbol {symbol}.")

            self._ensure_symbol_tradable(symbol_info)
            contract = self._contract_dict(symbol_info)

            requested_volume = float(volume)
            normalized_volume = self.normalize_volume(
                requested_volume,
                contract["volume_min"],
                contract["volume_max"],
                contract["volume_step"],
            )

            if abs(normalized_volume - requested_volume) > 1e-8:
                notes.append(
                    f"Requested volume {requested_volume} was normalized to "
                    f"{normalized_volume} according to broker volume rules."
                )

            tick = mt5.symbol_info_tick(symbol_info.name)
            if not tick:
                raise RuntimeError(f"Could not get tick data for {symbol_info.name}.")

            if side == "buy":
                raw_price = float(tick.ask)
                order_type = getattr(mt5, "ORDER_TYPE_BUY", 0)
                action = "open_buy"
            else:
                raw_price = float(tick.bid)
                order_type = getattr(mt5, "ORDER_TYPE_SELL", 1)
                action = "open_sell"

            if raw_price <= 0.0:
                raise RuntimeError("Received invalid market price.")

            price = self.round_price(raw_price, contract["digits"])

            sl_price, tp_price = self._calculate_sl_tp(
                contract=contract,
                side=side,
                price=price,
                sl_points=sl_points,
                tp_points=tp_points,
            )

            request = {
                "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
                "symbol": symbol_info.name,
                "volume": normalized_volume,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": self.DEFAULT_DEVIATION,
                "magic": self.MAGIC,
                "comment": self.COMMENT,
                "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
            }

            result = self._send_order(request)
            return self._build_execution_result(
                result=result,
                action=action,
                symbol=symbol_info.name,
                request=request,
                notes=notes,
            )

        finally:
            self._shutdown()

    def close_position(self, ticket: int) -> TradeExecutionResult:
        """
        Close an open demo position by ticket using an opposite market order.
        """
        ticket = int(ticket)

        try:
            self._initialize()

            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                raise RuntimeError(f"Position ticket {ticket} was not found.")

            position = positions[0]

            buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)
            if int(position.type) == int(buy_type):
                order_type = getattr(mt5, "ORDER_TYPE_SELL", 1)
                action = "close_buy_position"
                side_for_price = "sell"
            else:
                order_type = getattr(mt5, "ORDER_TYPE_BUY", 0)
                action = "close_sell_position"
                side_for_price = "buy"

            symbol_info = MT5Connector.get_symbol_info(position.symbol)
            if not symbol_info:
                raise RuntimeError(
                    f"Could not resolve or select symbol {position.symbol}."
                )

            self._ensure_symbol_tradable(symbol_info)
            contract = self._contract_dict(symbol_info)

            tick = mt5.symbol_info_tick(symbol_info.name)
            if not tick:
                raise RuntimeError(f"Could not get tick data for {symbol_info.name}.")

            if side_for_price == "sell":
                raw_price = float(tick.bid)
            else:
                raw_price = float(tick.ask)

            if raw_price <= 0.0:
                raise RuntimeError("Received invalid market price.")

            price = self.round_price(raw_price, contract["digits"])

            request = {
                "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
                "symbol": symbol_info.name,
                "volume": float(position.volume),
                "type": order_type,
                "price": price,
                "position": ticket,
                "deviation": self.DEFAULT_DEVIATION,
                "magic": self.MAGIC,
                "comment": self.COMMENT,
                "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
            }

            result = self._send_order(request)
            return self._build_execution_result(
                result=result,
                action=action,
                symbol=symbol_info.name,
                request=request,
                notes=[],
            )

        finally:
            self._shutdown()