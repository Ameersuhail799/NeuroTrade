import sqlite3
import logging
from config import DB_PATH

class DatabaseManager:
    """Handles SQLite database connections and initial setup."""

    def __init__(self):
        self.db_path = DB_PATH
        self.conn = None

    def connect(self):
        """Establish connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            logging.info(f"Connected to SQLite database at {self.db_path}")
            self._create_tables()
            return True
        except sqlite3.Error as e:
            logging.error(f"SQLite connection error: {e}")
            return False

    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Basic table for system state/logs for now
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_key TEXT UNIQUE NOT NULL,
                state_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        logging.info("Database tables verified/created.")

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logging.info("SQLite connection closed.")