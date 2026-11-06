You are building "NeuroTrade AI" - Part 8: Performance Dashboard.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-7 are complete. Now build the performance dashboard.

TASK: Create the Performance Dashboard UI that shows AI brain status and trade results.

REQUIREMENTS:

1. Create ui/dashboard.py:
   - Class PerformanceDashboard(QWidget)
   - Displays in the right panel of MainWindow

2. Dashboard Sections:

   SECTION 1: Brain Status
   ┌─────────────────────────────────┐
   │  🧠 Brain Status: TRAINED       │
   │  Experience: 156 trades         │
   │  Accuracy: 71.8%                │
   │  ████████████████░░░░░░  71.8%  │
   │  State: LEARNING → TRAINED →    │
   │         EXPERT                  │
   │         [■■■■■□□□□□]            │
   └─────────────────────────────────┘

   SECTION 2: Trade Statistics
   ┌─────────────────────────────────┐
   │  📊 Trade Statistics            │
   │  Total Trades:    156           │
   │  Passed (WIN):    112  ✅       │
   │  Failed (LOSS):   44   ❌       │
   │  Win Rate:        71.8%         │
   │  Win Streak:      4             │
   │  Loss Streak:     0             │
   │  Best Streak:     12            │
   └─────────────────────────────────┘

   SECTION 3: Recent Signals
   ┌─────────────────────────────────┐
   │  📋 Recent Signals              │
   │  ✅ BUY LIMIT  | WIN  | +18.0   │
   │  ✅ M. SELL    | WIN  | +17.0   │
   │  ❌ M. BUY     | LOSS | -7.5    │
   │  ✅ M. BUY     | WIN  | +12.0   │
   │  ⏳ SELL LIMIT | OPEN | ---     │
   │  [View All]                     │
   └─────────────────────────────────┘

   SECTION 4: Accuracy Trend Chart
   ┌─────────────────────────────────┐
   │  📈 Accuracy Over Time          │
   │  100% ┤                         │
   │   80% ┤        ╭──╮   ╭─       │
   │   60% ┤   ╭────╯  ╰───╯        │
   │   40% ┤───╯                     │
   │    0% ┼────────────────────     │
   │       Day 1    Day 15   Day 30  │
   └─────────────────────────────────┘

   SECTION 5: Current Signal
   ┌─────────────────────────────────┐
   │  🎯 Current Signal              │
   │  🟢 BUY LIMIT - XAUUSD          │
   │  Entry: 2,340.00                │
   │  SL: 2,333.00                   │
   │  TP: 2,358.00                   │
   │  Confidence: 78%                │
   │  [📋 Copy] [📤 Share] [📝 Note] │
   └─────────────────────────────────┘

3. Widget Implementation:
   - Use QScrollArea for scrollable content
   - Use QLabel for text
   - Use QProgressBar for accuracy bars
   - Use QTableWidget for trade history
   - Use simple drawing or matplotlib for accuracy trend chart

4. Data Updates:
   - Method: update_dashboard(stats)
     Refreshes all sections with new data
   - Method: update_brain_status(status)
     Updates brain state display
   - Method: add_signal_to_list(signal, result)
     Adds new signal to recent list
   - Method: update_accuracy_chart(data)
     Updates the accuracy trend chart

5. Copy Signal Button:
   - Button: "📋 Copy Signal"
   - Copies signal text to clipboard
   - Shows "Copied!" feedback for 2 seconds

6. Styling:
   - Match dark theme from Part 2
   - WIN text: Green (#4ecca3)
   - LOSS text: Red (#e94560)
   - OPEN text: Yellow (#ffd93d)
   - Progress bar: Gradient green
   - Section headers: Bold, accent color

7. Integration:
   - Embed in MainWindow right panel (Part 2)
   - Receive data from FeedbackLoop (Part 7)
   - Receive signals from AIBrain (Part 5)

IMPORTANT RULES:
- All code in English
- All UI text in English
- Clean, readable layout
- Auto-updates when new data arrives
- Professional appearance

Write complete, working code. The dashboard should be visually appealing and informative.