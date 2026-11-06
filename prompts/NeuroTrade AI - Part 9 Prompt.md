You are building "NeuroTrade AI" - Part 9: Signal System & Copy Feature.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-8 are complete. Now enhance the signal system with copy functionality.

TASK: Create the complete signal display and copy system.

REQUIREMENTS:

1. Enhance TradingSignal Class (from Part 5):
   
   Add method: to_copy_string()
   Returns formatted string:
   """
   ═══════════════════════════════════════
   🧠 NeuroTrade AI Signal
   ═══════════════════════════════════════
   📅 Date:      2024-01-15 14:30
   💱 Pair:      XAUUSD
   📊 Signal:    BUY LIMIT
   
   💰 Entry:     2,340.00
   🛑 Stop Loss: 2,333.00
   🎯 Take Profit: 2,358.00
   
   📈 Confidence: 78%
   📐 Risk:Reward: 1:2.6
   
   📝 Reasons:
   • Uptrend confirmed
   • Pullback to support zone
   • RSI bullish divergence
   • Bullish engulfing pattern
   ═══════════════════════════════════════
   """

   Add method: to_simple_string()
   Returns simple string:
   """
   XAUUSD BUY LIMIT
   Entry: 2340.00
   SL: 2333.00
   TP: 2358.00
   Confidence: 78%
   """

   Add method: copy_to_clipboard()
   - Uses QApplication.clipboard()
   - Copies to_simple_string() to clipboard
   - Returns True if successful

2. Create ui/signal_panel.py:
   - Class SignalPanel(QWidget)
   - Displays current signal prominently

3. Signal Panel Layout:
   ┌─────────────────────────────────────┐
   │  🎯 CURRENT SIGNAL                  │
   │  ┌─────────────────────────────┐   │
   │  │  🟢 BUY LIMIT               │   │
   │  │  Pair: XAUUSD               │   │
   │  │  Entry: 2,340.00            │   │
   │  │  SL: 2,333.00               │   │
   │  │  TP: 2,358.00               │   │
   │  │  Confidence: 78%            │   │
   │  └─────────────────────────────┘   │
   │  [📋 Copy Signal]                   │
   │  [📋 Copy Detailed]                 │
   │  [📤 Share]                         │
   │  ── Signal History ──               │
   │  ✅ BUY  | 14:30 | WIN  | +18.0    │
   │  ✅ SELL | 13:15 | WIN  | +17.0    │
   │  ❌ BUY  | 11:00 | LOSS | -7.5     │
   └─────────────────────────────────────┘

4. Copy Button Functionality:
   
   Button 1: "📋 Copy Signal"
   - Copies simple format
   - Shows toast: "Signal copied!"
   
   Button 2: "📋 Copy Detailed"
   - Copies detailed format with reasons
   - Shows toast: "Detailed signal copied!"
   
   Button 3: "📤 Share"
   - Opens system share dialog (if available)
   - Or copies to clipboard with share message

5. Signal History List:
   - QTableWidget or QListWidget
   - Columns: Result | Type | Time | Status | P/L
   - Color coding:
     WIN = Green
     LOSS = Red
     OPEN = Yellow
   - Double-click to view details

6. Toast Notification:
   - Create a small popup that appears for 2 seconds
   - Text: "✅ Signal copied to clipboard!"
   - Position: Bottom-right of window
   - Auto-fade out

7. Signal Sound Alert (Optional):
   - When new signal generated, play a subtle beep
   - Use QSound or winsound module
   - Can be disabled in settings

8. Integration:
   - SignalPanel goes in MainWindow right panel
   - Receives signals from AIBrain (Part 5)
   - Updates when new signal generated
   - Syncs with PerformanceDashboard (Part 8)

IMPORTANT RULES:
- All code in English
- All UI text in English
- Copy must work reliably
- Signal format must be clean and readable
- Easy to paste into Telegram, WhatsApp, Notes

Write complete, working code. The copy feature is essential for the user.