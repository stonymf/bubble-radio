import sqlite3
from contextlib import contextmanager
from src.config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()
