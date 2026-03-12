"""
Quick initializer script to create DB tables using SQLAlchemy models.
Run: python scripts/init_db.py
"""
from src.app.db import init_db

if __name__ == "__main__":
    init_db()
    print("DB initialized")