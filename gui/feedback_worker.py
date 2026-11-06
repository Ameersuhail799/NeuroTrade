"""
Background worker for the Part 7 Feedback Terminal.

Actions:
- load: load candle history and indicators from MT5 or SQLite.
- train: build feedback samples, adapt weights, validate out-of-sample.
- weights: load persisted weights.
- reset_weights: reset persisted weights to defaults.
"""

from PyQt6.QtCore import QThread, pyqtSignal

from core.mt5_connector import MT5Connector
from core.data_store import CandleStore
from core.data_engine import DataEngine
from core.indicators import IndicatorEngine
from core.weight_store import WeightStore
from core.feedback_engine import FeedbackEngine
from core.rule_features import DEFAULT_WEIGHTS


class FeedbackWorker(QThread):
    data_ready = pyqtSignal(object, object)
    train_ready = pyqtSignal(object, object)
    weights_ready = pyqtSignal(object, str)
    error = pyqtSignal(str)

    def __init__(self, action: str, payload: dict = None, parent=None):
        super().__init__(parent)

        self.action = action
        self.payload = dict(payload or {})

    def run(self):
        try:
            if self.action == "load":
                self._run_load()
            elif self.action == "train":
                self._run_train()
            elif self.action == "weights":
                self._run_weights()
            elif self.action == "reset_weights":
                self._run_reset_weights()
            else:
                raise ValueError(f"Unknown feedback worker action: {self.action}")

        except Exception as exc:
            self.error.emit(str(exc))

    def _run_load(self):
        symbol = str(self.payload.get("symbol", ""))
        timeframe = str(self.payload.get("timeframe", ""))
        bars = int(self.payload.get("bars", 1000))
        mode = str(self.payload.get("mode", "load"))

        candle_store = CandleStore()
        weight_store = WeightStore()
        mt5_started = False

        try:
            if not candle_store.connect():
                self.error.emit("Could not open the SQLite candle store.")
                return

            if not weight_store.connect():
                self.error.emit("Could not open the SQLite weight store.")
                return

            if mode == "sync":
                if not MT5Connector.initialize():
                    self.error.emit(
                        "MT5 initialization failed. "
                        "Ensure MT5 is running and logged into a DEMO account."
                    )
                    return

                mt5_started = True

                symbol_info = MT5Connector.get_symbol_info(symbol)
                if not symbol_info:
                    self.error.emit(f"Could not resolve symbol {symbol}.")
                    return

                resolved_symbol = symbol_info.name
                point = float(symbol_info.point)
                digits = int(symbol_info.digits)

                if point <= 0.0:
                    self.error.emit(f"Invalid point value for {resolved_symbol}.")
                    return

                weight_store.save_contract(symbol, resolved_symbol, point, digits)
                weight_store.save_contract(
                    resolved_symbol, resolved_symbol, point, digits
                )

                engine = DataEngine(
                    symbol=resolved_symbol,
                    timeframe=timeframe,
                    store=candle_store,
                )

                raw = engine.sync_recent(limit=bars)

            else:
                contract = weight_store.load_contract(symbol)

                if not contract:
                    if MT5Connector.initialize():
                        mt5_started = True

                        symbol_info = MT5Connector.get_symbol_info(symbol)
                        if not symbol_info:
                            self.error.emit(f"Could not resolve symbol {symbol}.")
                            return

                        resolved_symbol = symbol_info.name
                        point = float(symbol_info.point)
                        digits = int(symbol_info.digits)

                        if point <= 0.0:
                            self.error.emit(
                                f"Invalid point value for {resolved_symbol}."
                            )
                            return

                        weight_store.save_contract(
                            symbol, resolved_symbol, point, digits
                        )
                        weight_store.save_contract(
                            resolved_symbol, resolved_symbol, point, digits
                        )

                    else:
                        self.error.emit(
                            "No stored contract info for this symbol. "
                            "Run Sync MT5 Data once while MT5 is open."
                        )
                        return

                else:
                    resolved_symbol = contract["resolved_symbol"]
                    point = float(contract["point"])
                    digits = int(contract["digits"])

                raw = candle_store.load_candles(
                    resolved_symbol,
                    timeframe,
                    bars,
                )

                if raw.empty:
                    self.error.emit(
                        f"No stored candles for {resolved_symbol} {timeframe}. "
                        "Run Sync MT5 Data first."
                    )
                    return

            enriched = IndicatorEngine.add_indicators(raw)

            meta = {
                "symbol": resolved_symbol,
                "requested_symbol": symbol,
                "timeframe": timeframe,
                "source": "MT5" if mode == "sync" else "SQLite",
                "rows": int(len(enriched)),
                "point": float(point),
                "digits": int(digits),
            }

            self.data_ready.emit(enriched, meta)

        finally:
            if mt5_started:
                MT5Connector.shutdown()

            candle_store.close()
            weight_store.close()

    def _run_train(self):
        df = self.payload.get("df")
        meta = dict(self.payload.get("meta", {}))

        horizon = int(self.payload.get("horizon", 30))
        min_outcome_points = float(self.payload.get("min_outcome_points", 50.0))
        learning_rate = float(self.payload.get("learning_rate", 0.01))
        train_fraction = float(self.payload.get("train_fraction", 0.70))
        start_from_default = bool(self.payload.get("start_from_default", True))

        point = float(meta.get("point", 0.0))
        if point <= 0.0:
            self.error.emit("Cannot train without a valid symbol point value.")
            return

        weight_store = WeightStore()

        try:
            if not weight_store.connect():
                self.error.emit("Could not open the SQLite weight store.")
                return

            if start_from_default:
                start_weights = dict(DEFAULT_WEIGHTS)
            else:
                start_weights = weight_store.load_weights()

            samples = FeedbackEngine.build_samples(
                df=df,
                point=point,
                horizon=horizon,
                min_outcome_points=min_outcome_points,
                train_fraction=train_fraction,
            )

            adapted_weights, updates = FeedbackEngine.train_weights(
                start_weights=start_weights,
                samples=samples,
                learning_rate=learning_rate,
            )

            start_metrics = FeedbackEngine.evaluate_validation(
                samples=samples,
                weights=start_weights,
            )

            adapted_metrics = FeedbackEngine.evaluate_validation(
                samples=samples,
                weights=adapted_weights,
            )

            report = FeedbackEngine.format_report(
                meta=meta,
                samples=samples,
                start_weights=start_weights,
                adapted_weights=adapted_weights,
                start_metrics=start_metrics,
                adapted_metrics=adapted_metrics,
                learning_rate=learning_rate,
                updates=updates,
                horizon=horizon,
                min_outcome_points=min_outcome_points,
                train_fraction=train_fraction,
            )

            # Only save weights if candidate validation metrics do not degrade relative to start_metrics
            accept_candidate = (
                adapted_metrics.get("signals", 0) > 0
                and adapted_metrics.get("avg_signal_return_points", 0.0)
                >= start_metrics.get("avg_signal_return_points", 0.0)
            )

            if accept_candidate:
                weight_store.save_weights(adapted_weights)
                final_weights = adapted_weights
                status_note = (
                    "\n\nCandidate Acceptance: ADAPTED weights accepted and saved "
                    "(validation return improved or held)."
                )
            else:
                final_weights = start_weights
                status_note = (
                    "\n\nCandidate Rejection: ADAPTED weights degraded or generated 0 signals on "
                    "out-of-sample validation. Starting weights were retained and NOT overwritten."
                )

            report = report + status_note

            weight_store.save_run(
                symbol=str(meta.get("symbol", "UNKNOWN")),
                timeframe=str(meta.get("timeframe", "UNKNOWN")),
                report=report,
            )

            self.train_ready.emit(report, final_weights)

        finally:
            weight_store.close()

    def _run_weights(self):
        weight_store = WeightStore()

        try:
            if not weight_store.connect():
                self.error.emit("Could not open the SQLite weight store.")
                return

            weights = weight_store.load_weights()
            self.weights_ready.emit(weights, "Persisted weights loaded.")

        finally:
            weight_store.close()

    def _run_reset_weights(self):
        weight_store = WeightStore()

        try:
            if not weight_store.connect():
                self.error.emit("Could not open the SQLite weight store.")
                return

            weight_store.reset_weights()
            weights = weight_store.load_weights()

            self.weights_ready.emit(weights, "Weights reset to defaults.")

        finally:
            weight_store.close()