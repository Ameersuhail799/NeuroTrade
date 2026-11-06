import os

# Database Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = "neurotrade.db"
DB_PATH = os.path.join(BASE_DIR, DB_NAME)

# Trading Configuration
DEFAULT_SYMBOL = "XAUUSD"
ALLOWED_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
ALLOWED_TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "1D"]

# MT5 Configuration
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_LOGIN = None # Relying on terminal saved login for security
MT5_PASSWORD = None
MT5_SERVER = None