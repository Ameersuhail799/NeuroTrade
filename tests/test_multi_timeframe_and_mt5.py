import unittest
from unittest.mock import MagicMock, patch

from core.mt5_connector import MT5Connector
from core.multi_timeframe_data import MultiTimeframeDataCoordinator


class DummySymbol:
    def __init__(self, name: str, visible: bool = False):
        self.name = name
        self.visible = visible


class MT5ConnectorTests(unittest.TestCase):
    def setUp(self):
        MT5Connector._active_sessions = 0

    def tearDown(self):
        MT5Connector._active_sessions = 0

    def test_symbol_resolution_exact_case_match(self):
        broker_symbols = [
            DummySymbol("XAUUSD.a", visible=True),
            DummySymbol("XAUUSD", visible=False),
            DummySymbol("GOLD", visible=True),
        ]
        resolved = MT5Connector.resolve_symbol("XAUUSD", symbols_list=broker_symbols)
        self.assertEqual(resolved, "XAUUSD")

    def test_symbol_resolution_case_insensitive(self):
        broker_symbols = [
            DummySymbol("xauusd", visible=False),
            DummySymbol("XAUUSD_pro", visible=True),
        ]
        resolved = MT5Connector.resolve_symbol("XAUUSD", symbols_list=broker_symbols)
        self.assertEqual(resolved, "xauusd")

    def test_symbol_resolution_prefix_with_broker_suffix(self):
        broker_symbols = [
            DummySymbol("XAUUSD.ecn", visible=False),
            DummySymbol("XAUUSD.a", visible=True),
            DummySymbol("EURUSD", visible=True),
        ]
        resolved = MT5Connector.resolve_symbol("XAUUSD", symbols_list=broker_symbols)
        self.assertEqual(resolved, "XAUUSD.a")

    def test_symbol_resolution_gold_alias_fallback(self):
        broker_symbols = [
            DummySymbol("EURUSD", visible=True),
            DummySymbol("GOLD.a", visible=True),
            DummySymbol("USOIL", visible=True),
        ]
        resolved = MT5Connector.resolve_symbol("XAUUSD", symbols_list=broker_symbols)
        self.assertEqual(resolved, "GOLD.a")

    def test_symbol_resolution_unknown_returns_none(self):
        broker_symbols = [
            DummySymbol("EURUSD", visible=True),
            DummySymbol("GBPUSD", visible=True),
        ]
        resolved = MT5Connector.resolve_symbol("XAUUSD", symbols_list=broker_symbols)
        self.assertIsNone(resolved)

    @patch("core.mt5_connector.mt5")
    def test_mt5_reference_counted_lifecycle(self, mock_mt5):
        # Setup mock account info for DEMO account
        mock_acc = MagicMock()
        mock_acc.trade_mode = 0  # DEMO
        mock_acc.login = 12345
        mock_acc.server = "Demo-Server"
        mock_mt5.initialize.return_value = True
        mock_mt5.account_info.return_value = mock_acc
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = 1

        # Session 1 starts
        self.assertTrue(MT5Connector.initialize())
        self.assertEqual(MT5Connector._active_sessions, 1)
        self.assertEqual(mock_mt5.initialize.call_count, 1)

        # Session 2 starts while Session 1 is active (e.g. Chart worker + Signal worker)
        self.assertTrue(MT5Connector.initialize())
        self.assertEqual(MT5Connector._active_sessions, 2)
        # Should not call mt5.initialize again
        self.assertEqual(mock_mt5.initialize.call_count, 1)

        # Session 2 finishes and calls shutdown
        MT5Connector.shutdown()
        self.assertEqual(MT5Connector._active_sessions, 1)
        # mt5.shutdown must NOT have been called yet
        mock_mt5.shutdown.assert_not_called()

        # Session 1 finishes and calls shutdown
        MT5Connector.shutdown()
        self.assertEqual(MT5Connector._active_sessions, 0)
        # Now mt5.shutdown must be called
        mock_mt5.shutdown.assert_called_once()

    @patch("core.mt5_connector.mt5")
    def test_mt5_force_shutdown(self, mock_mt5):
        MT5Connector._active_sessions = 5
        MT5Connector.shutdown(force=True)
        self.assertEqual(MT5Connector._active_sessions, 0)
        mock_mt5.shutdown.assert_called_once()

    @patch("core.mt5_connector.os.path.isfile")
    @patch("core.mt5_connector.mt5")
    def test_mt5_initialize_falls_back_when_path_missing(self, mock_mt5, mock_isfile):
        # MT5_PATH does not exist on disk
        mock_isfile.return_value = False
        mock_acc = MagicMock()
        mock_acc.trade_mode = 0
        mock_mt5.initialize.return_value = True
        mock_mt5.account_info.return_value = mock_acc
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = 0

        self.assertTrue(MT5Connector.initialize())
        # Verify mt5.initialize() was called without arguments (or empty kwargs)
        mock_mt5.initialize.assert_called_once_with()


class MultiTimeframeCoordinatorTests(unittest.TestCase):
    def test_bar_count_enforcement(self):
        # 1H requires at least 250 bars
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("1H", 100), 250)
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("1H", 500), 500)

        # 15m requires at least 100 bars
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("15m", 50), 100)
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("15m", 300), 300)

        # 5m requires at least 100 bars
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("5m", 50), 100)
        self.assertEqual(MultiTimeframeDataCoordinator.get_required_bars("5m", 400), 400)


if __name__ == "__main__":
    unittest.main()
