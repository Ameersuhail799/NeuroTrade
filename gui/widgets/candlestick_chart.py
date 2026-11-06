from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont


class CandlestickChart(QWidget):
    """
    Lightweight candlestick chart drawn with PyQt6 QPainter.

    Renders a pandas DataFrame with columns:
    time, open, high, low, close.

    Optional indicator overlays are supplied as a list of dicts:
    {"name": str, "color": str, "values": sequence of float/NaN}
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data = None
        self._meta = {}
        self._overlays = []

        self.setMinimumHeight(320)
        self.setMinimumWidth(600)

    def set_data(self, data, meta=None):
        if data is None or len(data) == 0:
            self._data = None
        else:
            self._data = data

        self._meta = meta or {}
        self.update()

    def set_overlays(self, overlays):
        """Set indicator overlays. Values must align with candle rows."""
        self._overlays = overlays or []
        self.update()

    def clear(self):
        self._data = None
        self._meta = {}
        self._overlays = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#0d1013"))

        if self._data is None or len(self._data) == 0:
            painter.setPen(QColor("#9aa0a6"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No candle data loaded",
            )
            return

        left = 10
        top = 24
        right = 70
        bottom = 26

        plot_width = self.width() - left - right
        plot_height = self.height() - top - bottom

        if plot_width <= 20 or plot_height <= 20:
            return

        plot = QRectF(left, top, plot_width, plot_height)
        df = self._data

        low = float(df["low"].min())
        high = float(df["high"].max())

        # Include overlay values in the vertical scale when available.
        for overlay in self._overlays:
            values = overlay.get("values", [])
            valid = [
                float(value)
                for value in values[:len(df)]
                if value is not None
                and str(value) != "nan"
            ]
            if valid:
                low = min(low, min(valid))
                high = max(high, max(valid))

        if high == low:
            high += 1.0
            low -= 1.0

        padding = (high - low) * 0.05
        price_min = low - padding
        price_max = high + padding
        price_span = price_max - price_min

        n = len(df)
        slot = plot.width() / n
        candle_width = max(1, int(slot * 0.65))
        decimals = int(self._meta.get("digits", 2))

        def y(price: float) -> float:
            return plot.top() + (price_max - price) * plot.height() / price_span

        def x(index: int) -> float:
            return plot.left() + slot * index + slot / 2.0

        if self._meta:
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor("#d5d8dc"))
            title = (
                f"{self._meta.get('symbol', '')} "
                f"{self._meta.get('timeframe', '')} | "
                f"Candles: {self._meta.get('rows', 0)} | "
                f"Updated: {self._meta.get('updated_at', '')}"
            )
            painter.drawText(
                QRectF(left, 2, self.width() - left - right, top - 4),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title,
            )

        painter.setFont(QFont("Segoe UI", 8))
        grid_steps = 6
        for i in range(grid_steps + 1):
            price = price_min + price_span * i / grid_steps
            yy = y(price)

            painter.setPen(QPen(QColor("#2a2f36"), 1))
            painter.drawLine(int(plot.left()), int(yy), int(plot.right()), int(yy))

            painter.setPen(QColor("#9aa0a6"))
            painter.drawText(
                QRectF(plot.right() + 4, yy - 8, right - 8, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{price:.{decimals}f}",
            )

        label_count = min(6, n)
        if label_count > 0:
            step = max(1, n // label_count)
            timeframe = str(self._meta.get("timeframe", "")).upper()
            time_format = "%Y-%m-%d" if timeframe == "1D" else "%m-%d %H:%M"

            for i in range(0, n, step):
                xx = x(i)
                label = df["time"].iloc[i].strftime(time_format)

                painter.setPen(QPen(QColor("#2a2f36"), 1))
                painter.drawLine(int(xx), int(plot.bottom()), int(xx), int(plot.bottom() + 4))

                painter.setPen(QColor("#9aa0a6"))
                painter.drawText(
                    QRectF(xx - 45, plot.bottom() + 5, 90, 16),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    label,
                )

        up_color = QColor("#2ecc71")
        down_color = QColor("#e74c3c")

        for i, row in enumerate(df.itertuples(index=False)):
            open_price = float(row.open)
            high_price = float(row.high)
            low_price = float(row.low)
            close_price = float(row.close)

            color = up_color if close_price >= open_price else down_color
            xx = x(i)

            painter.setPen(QPen(color, 1))
            painter.drawLine(int(xx), int(y(high_price)), int(xx), int(y(low_price)))

            body_top = y(max(open_price, close_price))
            body_bottom = y(min(open_price, close_price))
            body_height = max(1, int(body_bottom - body_top))

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, 1))
            painter.drawRect(
                QRectF(xx - candle_width / 2.0, body_top, candle_width, body_height)
            )

        # Indicator overlays. NaN segments are skipped, never drawn as zero.
        for overlay in self._overlays:
            values = overlay.get("values", [])
            color = QColor(overlay.get("color", "#f1c40f"))
            previous = None

            for i in range(min(len(values), n)):
                try:
                    raw_value = values[i]
                    value = float(raw_value)
                    is_valid = value == value  # NaN check without extra dependency
                except (TypeError, ValueError):
                    is_valid = False

                if not is_valid:
                    previous = None
                    continue

                current = (x(i), y(value))
                if previous is not None:
                    painter.setPen(QPen(color, 1))
                    painter.drawLine(
                        int(previous[0]), int(previous[1]),
                        int(current[0]), int(current[1]),
                    )
                previous = current

        last_close = float(df["close"].iloc[-1])
        yy = y(last_close)

        painter.setPen(QPen(QColor("#f1c40f"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(plot.left()), int(yy), int(plot.right()), int(yy))

        painter.setPen(QColor("#f1c40f"))
        painter.drawText(
            QRectF(plot.right() + 4, yy - 8, right - 8, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{last_close:.{decimals}f}",
        )