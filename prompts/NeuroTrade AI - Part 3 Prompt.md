You are building "NeuroTrade AI" - Part 3: Live Chart Viewer.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-2 (MT5 Connection, Main Window) are complete. Now build the chart viewer.

TASK: Create a smooth, live-updating candlestick chart viewer with XAUUSD as default.

REQUIREMENTS:

1. Create ui/chart_viewer.py:
   - Class ChartViewer(QWidget)
   - Use PyQtGraph for smooth, fast rendering (preferred) OR matplotlib embedded in PyQt6
   - Must display candlestick chart

2. Chart Features:
   - Candlestick chart (green for bullish, red for bearish)
   - Smooth rendering with anti-aliasing
   - Live price updates (refresh every 1-2 seconds)
   - Current price line (horizontal dashed line at current price)
   - Price label on the right side showing current price
   - X-Axis: Date and Time
   - Y-Axis: Price
   - Crosshair on mouse hover showing OHLC values
   - Grid lines (subtle, dark theme compatible)
   - Zoom in/out with mouse wheel
   - Pan/drag to scroll through history

3. Chart Header (above chart):
   - Display: Pair Name | Timeframe | Current Price | Price Change %
   - Example: "XAUUSD | 1H | 2,345.50 | +0.45%"
   - Price color: Green if up, Red if down

4. OHLC Info Bar:
   - Show: O: 2345.00 | H: 2348.50 | L: 2342.00 | C: 2345.50
   - Updates on candle hover

5. Timeframe Switching:
   - When timeframe changes, reload chart data
   - Support: 1m, 5m, 15m, 1H, 4H, 1D
   - Map timeframes to MT5 constants:
     1m = mt5.TIMEFRAME_M1
     5m = mt5.TIMEFRAME_M5
     15m = mt5.TIMEFRAME_M15
     1H = mt5.TIMEFRAME_H1
     4H = mt5.TIMEFRAME_H4
     1D = mt5.TIMEFRAME_D1

6. Pair Switching:
   - When pair changes, reload chart data
   - Default pair: XAUUSD
   - Auto-adjust Y-axis scale for different pairs

7. Data Loading:
   - Use MT5Connector.get_ohlc_data() from Part 1
   - Load last 200 candles initially
   - Update last candle in real-time
   - Add new candle when timeframe period completes

8. Visual Styling:
   - Background: #1a1a2e
   - Grid: #2a2a4a
   - Bullish candle: #4ecca3 (green)
   - Bearish candle: #e94560 (red)
   - Price line: #ffd93d (yellow dashed)
   - Text: #ffffff

9. Integration:
   - ChartViewer should be embeddable in MainWindow (Part 2)
   - Accept pair and timeframe as parameters
   - Method: update_chart(pair, timeframe)
   - Method: refresh_price() - called by timer for live updates

10. Timer for Live Updates:
    - QTimer with 1000ms interval
    - Updates current price
    - Updates last candle
    - Updates price label

IMPORTANT RULES:
- All code in English
- Chart must be SMOOTH and FAST
- No lag when updating
- Professional appearance
- XAUUSD is the PRIMARY focus pair

Write complete, working code. Test that chart renders correctly with sample data.