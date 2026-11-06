You are building "NeuroTrade AI" - Part 2: Main Window UI Framework.
This is a PERSONAL USE desktop trading application.

CONTEXT: Part 1 (MT5 Connection) is already complete. Now build the main window.

TASK: Create the main window UI using PyQt6.

REQUIREMENTS:

1. Create ui/main_window.py:
   - Class MainWindow(QMainWindow)
   - Window title: "NeuroTrade AI - Self-Learning Trading System"
   - Window size: 1400x900 (resizable)
   - Dark theme styling (dark background, light text)
   
2. Layout Structure:
   ┌─────────────────────────────────────────────────────────┐
   │  MENU BAR: File | View | Settings | Help                │
   ├─────────────────────────────────────────────────────────┤
   │  TOOLBAR: [Pair Selector] [Timeframe] [Connect] [Status]│
   ├──────────────────────────────────┬──────────────────────┤
   │                                  │  RIGHT PANEL:        │
   │   MAIN AREA:                     │  ┌────────────────┐  │
   │   (Chart Viewer - Part 3)        │  │ Signal Panel   │  │
   │                                  │  ├────────────────┤  │
   │                                  │  │ Performance    │  │
   │                                  │  │ Dashboard      │  │
   │                                  │  ├────────────────┤  │
   │                                  │  │ Brain Status   │  │
   │                                  │  └────────────────┘  │
   ├──────────────────────────────────┴──────────────────────┤
   │  STATUS BAR: Connection | Account | Time | Version       │
   └─────────────────────────────────────────────────────────┘

3. Toolbar Components:
   - QComboBox for Currency Pair (default: XAUUSD)
     Options: XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD
   - QComboBox for Timeframe (default: 1H)
     Options: 1m, 5m, 15m, 1H, 4H, 1D
   - QPushButton "Connect MT5" (green when connected, red when disconnected)
   - QLabel showing connection status: "● Connected" or "● Disconnected"
   - QLabel showing current price (updates live)

4. Right Panel (QDockWidget or fixed panel, width ~350px):
   - Signal Panel (placeholder for Part 9)
   - Performance Dashboard (placeholder for Part 8)
   - Brain Status indicator

5. Status Bar:
   - Left: MT5 Connection status
   - Center: Account Balance & Equity
   - Right: Current Time (updates every second) | Version 1.0.0

6. Styling (Dark Theme):
   - Background: #1a1a2e
   - Panel background: #16213e
   - Accent color: #e94560
   - Text color: #ffffff
   - Success green: #4ecca3
   - Error red: #e94560
   - Warning yellow: #ffd93d

7. Menu Bar:
   - File: Exit
   - View: Toggle Right Panel, Toggle Status Bar
   - Settings: Default Pair, Default Timeframe
   - Help: About

8. Update main.py:
   - Import MainWindow
   - Create QApplication
   - Show MainWindow
   - Handle MT5 connection on startup

IMPORTANT RULES:
- All code in English
- All UI text in English
- Clean, modular code
- Use PyQt6 (NOT PyQt5)
- Personal use only, no multi-user features

Write complete, working code. Make the UI look professional and modern.