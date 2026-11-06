import logging
import threading
from typing import Optional, List, Any

import MetaTrader5 as mt5

from config import DEFAULT_SYMBOL, MT5_PATH


class MT5Connector:
    """Handles connection and interactions with the MetaTrader 5 terminal with thread safety."""

    _lock = threading.RLock()
    _active_sessions = 0

    @staticmethod
    def _get_account_mode_name(mode: int) -> str:
        """Return human-readable account trade mode name."""
        mapping = {
            getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): "DEMO",
            getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 1): "REAL",
            getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 2): "CONTEST",
        }
        return mapping.get(mode, f"UNKNOWN({mode})")

    @classmethod
    def initialize(cls) -> bool:
        """Initialize or acquire an MT5 terminal session with reference counting."""
        with cls._lock:
            # If we already have active sessions, verify connection is still alive
            if cls._active_sessions > 0:
                try:
                    account_info = mt5.account_info()
                    if account_info:
                        mode = int(account_info.trade_mode)
                        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
                        if mode == demo_mode:
                            cls._active_sessions += 1
                            logging.debug(
                                f"MT5 session reused. Active sessions: {cls._active_sessions}"
                            )
                            return True
                except Exception:
                    pass
                # Connection dropped or invalid; reset count
                cls._active_sessions = 0

            try:
                if MT5_PATH:
                    initialized = mt5.initialize(MT5_PATH)
                else:
                    initialized = mt5.initialize()
            except Exception as exc:
                logging.error(f"MT5 initialization exception: {exc}")
                return False

            if not initialized:
                logging.error(f"MT5 initialization failed. Error code: {mt5.last_error()}")
                return False

            account_info = mt5.account_info()
            if not account_info:
                logging.error("Failed to get account info. Ensure MT5 terminal is logged in.")
                mt5.shutdown()
                return False

            mode = int(account_info.trade_mode)
            demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
            real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 1)
            mode_name = cls._get_account_mode_name(mode)

            logging.info(
                f"Connected to MT5. Account: {account_info.login}, "
                f"Server: {account_info.server}, Mode: {mode_name} (trade_mode={mode})"
            )

            if mode == real_mode:
                logging.critical("Connected to REAL account. ABORTING! (DEMO ONLY rule enforced)")
                mt5.shutdown()
                return False

            if mode != demo_mode:
                logging.critical(
                    f"Account mode is {mode_name}, not DEMO. ABORTING! (DEMO ONLY rule enforced)"
                )
                mt5.shutdown()
                return False

            cls._active_sessions = 1
            logging.info("DEMO account confirmed.")
            return True

    @classmethod
    def shutdown(cls, force: bool = False):
        """Release an MT5 session. mt5.shutdown() is only called when active sessions reach 0."""
        with cls._lock:
            if force:
                cls._active_sessions = 0
                mt5.shutdown()
                logging.info("MT5 connection forcefully closed.")
                return

            if cls._active_sessions > 0:
                cls._active_sessions -= 1

            if cls._active_sessions == 0:
                mt5.shutdown()
                logging.info("MT5 connection closed (all sessions released).")
            else:
                logging.debug(
                    f"MT5 session released. Remaining active sessions: {cls._active_sessions}"
                )

    @staticmethod
    def _rank_symbol_match(candidate_name: str, symbol_name: str, is_visible: bool = False) -> Optional[int]:
        """Rank candidate broker symbol for deterministic resolution.
        Lower rank number = higher priority.
        """
        c_exact = candidate_name.strip()
        s_exact = symbol_name.strip()
        c_upper = c_exact.upper()
        s_upper = s_exact.upper()

        # 1. Exact case-sensitive match
        if c_exact == s_exact:
            return 0 if is_visible else 1

        # 2. Exact case-insensitive match
        if c_upper == s_upper:
            return 2 if is_visible else 3

        # 3. Prefix match with common broker suffixes (.a, .m, _i, micro, etc.)
        if c_upper.startswith(s_upper):
            suffix_len = len(c_upper) - len(s_upper)
            return 10 + suffix_len if is_visible else 30 + suffix_len

        # 4. Known alias fallback for XAUUSD <-> GOLD
        if s_upper in ("XAUUSD", "GOLD"):
            target_alias = "GOLD" if s_upper == "XAUUSD" else "XAUUSD"
            if c_upper == target_alias:
                return 100 if is_visible else 101
            if c_upper.startswith(target_alias):
                suffix_len = len(c_upper) - len(target_alias)
                return 110 + suffix_len if is_visible else 130 + suffix_len

        return None

    @classmethod
    def resolve_symbol(cls, symbol_name: str, symbols_list=None) -> Optional[str]:
        """Resolve the exact symbol name from the broker with deterministic priority."""
        if not symbol_name:
            return None

        symbols = symbols_list if symbols_list is not None else mt5.symbols_get()
        if not symbols:
            logging.error("Failed to get symbols.")
            return None

        candidates = []
        for s in symbols:
            name = getattr(s, "name", str(s))
            visible = bool(getattr(s, "visible", False))
            rank = cls._rank_symbol_match(name, symbol_name, is_visible=visible)
            if rank is not None:
                candidates.append((rank, name))

        if not candidates:
            logging.error(f"Symbol {symbol_name} not found in broker list.")
            return None

        candidates.sort(key=lambda x: x[0])
        resolved = candidates[0][1]
        if resolved != symbol_name:
            logging.info(f"Resolved {symbol_name} to broker symbol: {resolved}")
        return resolved

    @classmethod
    def get_symbol_info(cls, symbol_name: str):
        """Get symbol information and ensure it is selected in Market Watch."""
        resolved_name = cls.resolve_symbol(symbol_name)
        if not resolved_name:
            return None

        symbol_info = mt5.symbol_info(resolved_name)
        if not symbol_info:
            # Try selecting it if it was not available initially
            if not mt5.symbol_select(resolved_name, True):
                logging.error(f"Failed to select symbol {resolved_name}")
                return None
            symbol_info = mt5.symbol_info(resolved_name)

        if not symbol_info.visible:
            logging.info(f"Symbol {resolved_name} not visible, attempting to select.")
            if not mt5.symbol_select(resolved_name, True):
                logging.error(f"Failed to select symbol {resolved_name}")
                return None

        return mt5.symbol_info(resolved_name)
