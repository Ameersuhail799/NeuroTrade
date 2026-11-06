You are building "NeuroTrade AI" - Part 5: AI Brain Core.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-4 are complete. Now build the AI Brain that makes trading decisions.

TASK: Create the AI Brain Core that analyzes data and generates trading signals.

REQUIREMENTS:

1. Create core/ai_brain.py:
   - Class AIBrain
   - This is the core decision-making engine

2. Brain States:
   - LEARNING: Initial phase, collecting data, low confidence
   - TRAINED: Has enough experience, moderate confidence
   - EXPERT: High accuracy, reliable signals
   
   Property: brain_state (auto-updates based on trade history)
   Property: experience_level (number of trades analyzed)
   Property: accuracy_percentage (win rate)

3. Decision Making Method:
   - Method: analyze_market(market_snapshot)
     Input: Data from DataEngine.get_market_snapshot()
     Process:
       a) Analyze trend direction
       b) Check RSI (overbought/oversold)
       c) Check MACD crossover
       d) Check Moving Average alignment
       e) Check candle patterns
       f) Check support/resistance proximity
       g) Calculate confidence score
     Output: TradingSignal object

4. TradingSignal Class:
   Attributes:
   - signal_type: "MARKET_BUY" / "MARKET_SELL" / "BUY_LIMIT" / "SELL_LIMIT" / "WAIT"
   - pair: str (e.g., "XAUUSD")
   - entry_price: float
   - stop_loss: float
   - take_profit: float
   - confidence: float (0-100%)
   - reasons: list of strings explaining why
   - timestamp: datetime
   
   Methods:
   - to_dict(): Convert to dictionary
   - to_string(): Convert to copyable string format
   - copy_to_clipboard(): Copy signal text to clipboard

5. Signal Generation Logic:
   
   MARKET BUY conditions (ALL must be true):
   - Trend is UPTREND
   - RSI < 70 (not overbought)
   - MACD bullish crossover
   - Price above MA20
   - Bullish candle pattern detected
   - Confidence > 70%
   
   MARKET SELL conditions (ALL must be true):
   - Trend is DOWNTREND
   - RSI > 30 (not oversold)
   - MACD bearish crossover
   - Price below MA20
   - Bearish candle pattern detected
   - Confidence > 70%
   
   BUY LIMIT conditions:
   - Trend is UPTREND
   - Price is above support level
   - Waiting for pullback to support
   - Entry price = nearest support level
   
   SELL LIMIT conditions:
   - Trend is DOWNTREND
   - Price is below resistance level
   - Waiting for pullback to resistance
   - Entry price = nearest resistance level
   
   WAIT conditions:
   - No clear trend
   - RSI in neutral zone (40-60)
   - No pattern detected
   - Confidence < 50%

6. SL/TP Calculation:
   - Method: calculate_sl_tp(signal_type, entry_price, atr, support_resistance)
   - BUY: SL below nearest support or entry - (1.5 * ATR)
   - SELL: SL above nearest resistance or entry + (1.5 * ATR)
   - TP: Minimum 2:1 Risk-Reward ratio
   - TP = entry + (2 * risk_distance) for BUY
   - TP = entry - (2 * risk_distance) for SELL

7. Confidence Calculation:
   - Start at 50%
   - +10% for trend confirmation
   - +10% for RSI confirmation
   - +10% for MACD confirmation
   - +10% for pattern confirmation
   - +5% for MA alignment
   - +5% for S/R confirmation
   - Maximum: 95%

8. Learning Integration:
   - Method: record_decision(signal, result)
     Stores decision and result for future learning
   - Method: get_statistics()
     Returns accuracy, win rate, total trades
   - Method: update_brain_state()
     Updates brain state based on performance

9. Signal Output Format:
   Example output string:
   """
   ═══════════════════════════════════
   🟢 NeuroTrade AI Signal
   ═══════════════════════════════════
   Pair:       XAUUSD
   Signal:     BUY LIMIT
   Entry:      2,340.00
   Stop Loss:  2,333.00
   Take Profit: 2,358.00
   Confidence: 78%
   Risk:Reward: 1:2.6
   ───────────────────────────────────
   Reasons:
   • Uptrend confirmed
   • Pullback to support zone
   • RSI showing bullish divergence
   • Bullish engulfing pattern
   ═══════════════════════════════════
   """

IMPORTANT RULES:
- All code in English
- Clean, modular design
- Easy to understand logic
- Well-commented code
- Confidence must be realistic (not always 100%)

Write complete, working code. This is the HEART of the application.