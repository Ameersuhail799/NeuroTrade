"""
Background worker for Part 5 decision evaluation.

The decision calculation is usually fast, but it is still kept off the GUI
thread to preserve the project rule that heavy/work operations should not
block the UI.
"""

from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd

from core.decision_engine import RuleBasedDecisionEngine


class DecisionWorker(QThread):
    """
    Evaluates the rule-based decision engine on a copy of the indicator data.

    This worker does not access MT5, SQLite, or the network.
    It never places orders.
    """

    result_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        df: pd.DataFrame,
        meta: dict,
        exclude_latest: bool = True,
        parent=None,
    ):
        super().__init__(parent)

        self.df = None if df is None else df.copy()
        self.meta = dict(meta or {})
        self.exclude_latest = bool(exclude_latest)

    def run(self):
        try:
            engine = RuleBasedDecisionEngine()
            result = engine.evaluate(
                df=self.df,
                meta=self.meta,
                exclude_latest=self.exclude_latest,
            )
            self.result_ready.emit(result)

        except Exception as exc:
            self.error.emit(f"Decision engine error: {exc}")