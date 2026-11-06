You are building "NeuroTrade AI" - Part 4: Data Engine.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-3 are complete. Now build the data collection engine.

TASK: Create the Data Engine that collects and processes trading data.

REQUIREMENTS:

1. Create core/data_engine.py:
   - Class DataEngine
   - Responsible for collecting ALL data needed by AI Brain

2. Chart Data Collection:
   - Method: get_candles(symbol, timeframe, count=200)
     Returns: DataFrame with columns [time, open, high, low, close, volume]
   - Method: get_latest_candle(symbol, timeframe)
     Returns: Latest single candle data
   - Method: get_price_history(symbol, timeframe, periods=100)
     Returns: List of closing prices

3. Technical Indicators Calculation:
   - Method: calculate_rsi(data, period=14)
     Returns: RSI values
   - Method: calculate_macd(data, fast=12, slow=26, signal=9)
     Returns: MACD line, Signal line, Histogram
   - Method: calculate_moving_averages(data, periods=[20, 50, 200])
     Returns: Dictionary of MA values
   - Method: calculate_bollinger_bands(data, period=20, std_dev=2)
     Returns: Upper, Middle, Lower bands
   - Method: calculate_atr(data, period=14)
     Returns: Average True Range values
   - Method: calculate_support_resistance(data, lookback=50)
     Returns: List of support levels, List of resistance levels

4. Pattern Detection (Basic):
   - Method: detect_candle_patterns(data)
     Detects: Doji, Hammer, Engulfing, Morning Star, Evening Star
     Returns: Dictionary {pattern_name: True/False, candle_index}
   - Method: detect_trend(data, lookback=20)
     Returns: "UPTREND" / "DOWNTREND" / "SIDEWAYS"
   - Method: detect_breakout(data, support_resistance)
     Returns: Breakout signal if price breaks S/R levels

5. Market Data Aggregation:
   - Method: get_market_snapshot(symbol, timeframe)
     Returns complete snapshot:
     {
       "price": current_price,
       "candles": ohlc_data,
       "rsi": rsi_value,
       "macd": macd_data,
       "ma": moving_averages,
       "bb": bollinger_bands,
       "atr": atr_value,
       "trend": trend_direction,
       "patterns": detected_patterns,
       "support": support_levels,
       "resistance": resistance_levels
     }

6. Data Storage:
   - Method: save_to_database(data, table_name)
     Save collected data to SQLite for AI training
   - Method: load_from_database(table_name, limit=1000)
     Load historical data for AI training

7. Database Schema (create in data/database.db):
   Table: candle_history
   - id, symbol, timeframe, time, open, high, low, close, volume
   
   Table: trade_history
   - id, symbol, type, entry_price, sl, tp, result, profit, timestamp
   
   Table: ai_decisions
   - id, symbol, timeframe, decision, confidence, timestamp, result

8. Integration:
   - DataEngine should work with MT5Connector (Part 1)
   - Provide data to AI Brain (Part 5)
   - Store all data locally in SQLite

IMPORTANT RULES:
- All code in English
- Efficient data processing
- Handle missing data gracefully
- Use pandas for DataFrame operations
- Use numpy for calculations

Write complete, working code with all methods implemented.