You are building "NeuroTrade AI" - a personal use, self-learning AI trading system for Forex trading. 
This is NOT for sale, NOT multi-user. It is a single-user desktop application.

TECH STACK:
- Python 3.x
- PyQt6 (GUI)
- MetaTrader 5 (Trading)
- SQLite (Local Database)
- OS: Windows 11

TASK: Create the project setup and MT5 connection module.

REQUIREMENTS:

1. Create project folder structure:
   NeuroTradeAI/
   ├── main.py
   ├── config.py
   ├── ui/
   │   ├── __init__.py
   │   ├── main_window.py
   │   ├── chart_viewer.py
   │   └── dashboard.py
   ├── core/
   │   ├── __init__.py
   │   ├── mt5_connector.py
   │   ├── data_engine.py
   │   ├── ai_brain.py
   │   ├── trade_executor.py
   │   └── feedback_loop.py
   ├── data/
   │   ├── database.db
   │   └── models/
   └── requirements.txt

2. Create config.py:
   - APP_NAME = "NeuroTrade AI"
   - VERSION = "1.0.0"
   - DEFAULT_PAIR = "XAUUSD"
   - DEFAULT_TIMEFRAME = "1H"
   - DB_PATH = "data/database.db"
   - TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "1D"]
   - CURRENCY_PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

3. Create core/mt5_connector.py:
   - Class MT5Connector
   - Method: connect() - Initialize and connect to MT5 terminal
   - Method: disconnect() - Shutdown MT5 connection
   - Method: is_connected() - Check connection status
   - Method: get_account_info() - Return account balance, equity, margin
   - Method: get_symbol_info(symbol) - Return symbol details (spread, digits, volume)
   - Method: get_current_price(symbol) - Return current bid/ask price
   - Method: get_ohlc_data(symbol, timeframe, count) - Return OHLC data as pandas DataFrame
   - Handle all errors gracefully with try/except
   - Print connection status messages

4. Create main.py:
   - Import MT5Connector
   - Test connection on startup
   - Print account info if connected
   - Print "NeuroTrade AI - Connection Successful" or error message

5. Create requirements.txt:
   MetaTrader5
   PyQt6
   pandas
   numpy

IMPORTANT RULES:
- All code must be in English
- All comments in English
- All variable names in English
- Use proper error handling
- Make it modular and clean
- This is for PERSONAL USE ONLY

Write complete, working, production-ready code for all files.