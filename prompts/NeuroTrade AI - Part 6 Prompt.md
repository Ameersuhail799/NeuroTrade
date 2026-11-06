You are building "NeuroTrade AI" - Part 6: Trade Executor.
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-5 are complete. Now build the trade execution module.

TASK: Create the Trade Executor that places testing trades based on AI signals.

REQUIREMENTS:

1. Create core/trade_executor.py:
   - Class TradeExecutor
   - Executes trades on MT5 (testing/demo mode)

2. Order Types Support:
   - MARKET BUY: Buy at current ask price
   - MARKET SELL: Sell at current bid price
   - BUY LIMIT: Buy at specified lower price
   - SELL LIMIT: Sell at specified higher price

3. Core Methods:
   
   - Method: execute_market_buy(symbol, volume, sl, tp)
     Returns: Order ticket number or error
   
   - Method: execute_market_sell(symbol, volume, sl, tp)
     Returns: Order ticket number or error
   
   - Method: execute_buy_limit(symbol, volume, entry_price, sl, tp)
     Returns: Order ticket number or error
   
   - Method: execute_sell_limit(symbol, volume, entry_price, sl, tp)
     Returns: Order ticket number or error
   
   - Method: close_position(ticket)
     Close a specific position
   
   - Method: close_all_positions(symbol=None)
     Close all open positions
   
   - Method: get_open_positions()
     Returns: List of open positions with details
   
   - Method: get_position_status(ticket)
     Returns: Current profit/loss of position
   
   - Method: modify_position(ticket, new_sl=None, new_tp=None)
     Modify SL/TP of existing position

4. Volume Calculation:
   - Method: calculate_volume(symbol, risk_amount, sl_distance)
     Calculate appropriate lot size based on risk
   - Default risk: 1% of account balance
   - Formula: volume = risk_amount / (sl_distance * tick_value)
   - Round to appropriate lot step (0.01 for most pairs)

5. Testing Trade Mode:
   - Property: is_testing_mode = True (default)
   - In testing mode:
     * Trades are placed on DEMO account
     * Results are recorded for AI learning
     * No real money at risk
   - Method: execute_testing_trade(signal)
     Takes TradingSignal object and executes appropriate order
     Returns: TradeResult object

6. TradeResult Class:
   Attributes:
   - ticket: int
   - symbol: str
   - type: str (MARKET_BUY, MARKET_SELL, BUY_LIMIT, SELL_LIMIT)
   - entry_price: float
   - sl: float
   - tp: float
   - volume: float
   - open_time: datetime
   - close_time: datetime (None if still open)
   - status: "OPEN" / "TP_HIT" / "SL_HIT" / "CLOSED_MANUALLY"
   - profit: float (None if still open)
   - result: "WIN" / "LOSS" / "PENDING"

7. Position Monitoring:
   - Method: check_open_positions()
     Called periodically to check if SL/TP hit
     Updates TradeResult status
     Triggers feedback loop when trade closes
   
   - Use QTimer to check positions every 5 seconds

8. Trade Logging:
   - Method: log_trade(trade_result)
     Save trade result to SQLite database
   - Table: trade_history (from Part 4)

9. Integration:
   - Works with MT5Connector (Part 1) for order execution
   - Receives signals from AIBrain (Part 5)
   - Sends results to FeedbackLoop (Part 7)

10. Error Handling:
    - Handle MT5 order errors
    - Handle insufficient margin
    - Handle invalid stops
    - Handle connection lost
    - Log all errors

IMPORTANT RULES:
- All code in English
- ALWAYS use demo account for testing
- Proper error handling is CRITICAL
- Log every trade for AI learning
- Never risk more than calculated volume

Write complete, working code. This module handles actual trade execution.