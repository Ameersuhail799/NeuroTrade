"""
Simple equity curve widget drawn with PyQt6.

This widget does not use external chart libraries.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


class EquityCurve(QWidget):
    """
    Draws a simple cumulative closed-trade PnL curve.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._values = [0.0]
        self.setMinimumHeight(160)

    def set_data(self, values):
        if values is None or len(values) == 0:
            self._values = [0.0]
        else:
            self._values = [float(value) for value in values]

        self.update()

    def clear(self):
        self._values = [0.0]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0d1013"))

        if not self._values:
            painter.setPen(QColor("#9aa0a6"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No equity data",
            )
            return

        left = 10
        right = 65
        top = 10
        bottom = 10

        plot_width = self.width() - left - right
        plot_height = self.height() - top - bottom

        if plot_width <= 20 or plot_height <= 20:
            return

        values = self._values
        min_value = min(min(values), 0.0)
        max_value = max(max(values), 0.0)

        if max_value == min_value:
            max_value += 1.0
            min_value -= 1.0

        value_range = max_value - min_value
        padding = value_range * 0.08
        min_value -= padding
        max_value += padding
        value_range = max_value - min_value

        def x(index: int) -> float:
            if len(values) == 1:
                return left + plot_width / 2.0
            return left + plot_width * index / (len(values) - 1)

        def y(value: float) -> float:
            return top + (max_value - value) * plot_height / value_range

        # Grid / labels
        painter.setFont(QFont("Segoe UI", 8))

        label_values = [max_value, (max_value + min_value) / 2.0, min_value]

        for value in label_values:
            yy = y(value)
            painter.setPen(QPen(QColor("#2a2f36"), 1))
            painter.drawLine(left, int(yy), left + plot_width, int(yy))

            painter.setPen(QColor("#9aa0a6"))
            painter.drawText(
                QRectF(left + plot_width + 4, yy - 8, right - 8, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.2f}",
            )

        # Zero line
        if min_value <= 0.0 <= max_value:
            zero_y = y(0.0)
            painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(left, int(zero_y), left + plot_width, int(zero_y))

        # Equity line
        painter.setPen(QPen(QColor("#5dade2"), 2))

        previous_x = x(0)
        previous_y = y(values[0])

        if len(values) == 1:
            painter.drawPoint(int(previous_x), int(previous_y))
        else:
            for i in range(1, len(values)):
                current_x = x(i)
                current_y = y(values[i])

                painter.drawLine(
                    int(previous_x),
                    int(previous_y),
                    int(current_x),
                    int(current_y),
                )

                previous_x = current_x
                previous_y = current_y