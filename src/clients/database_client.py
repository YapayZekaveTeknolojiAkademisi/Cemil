import sqlite3
import uuid
import os
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.core.exceptions import DatabaseError

class DatabaseClient:
    """
    Cemil Bot için merkezi veritabanı yönetim sınıfı.
    SQLite bağlantı yönetiminden sorumludur.
    """

    def __init__(self, db_path: str = "data/cemil_bot.db"):
        self.db_path = db_path
        # Klasör yoksa oluştur
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()

    def get_connection(self):
        """SQLite bağlantısı döndürür."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Dict benzeri erişim için
            return conn
        except sqlite3.Error as e:
            logger.error(f"[X] Veritabanı bağlantı hatası: {e}")
            raise DatabaseError(f"Veritabanına bağlanılamadı: {e}")

    def init_db(self):
        """Temel tabloları hazırlar (Gerekirse)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Kullanıcılar Tablosu (Users)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        gender TEXT,
                        slack_id TEXT UNIQUE,
                        full_name TEXT,
                        first_name TEXT,
                        middle_name TEXT,
                        surname TEXT,
                        email TEXT,
                        country_code TEXT,
                        phone_number TEXT,
                        birthday TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Eşleşme Takip Tablosu (Matches)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS matches (
                        id TEXT PRIMARY KEY,
                        channel_id TEXT,
                        user1_id TEXT,
                        user2_id TEXT,
                        status TEXT DEFAULT 'active',
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.debug("[i] Veritabanı tabloları kontrol edildi.")
        except sqlite3.Error as e:
            logger.error(f"[X] Veritabanı ilklendirme hatası: {e}")
            raise DatabaseError(f"Tablolar oluşturulamadı: {e}")
