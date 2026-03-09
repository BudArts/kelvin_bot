import sqlite3
import os
from datetime import datetime
from pathlib import Path

class Database:
    def __init__(self):
        # На BotHost используем директорию data
        data_dir = Path(__file__).parent.parent / 'data'
        data_dir.mkdir(exist_ok=True)
        
        db_path = data_dir / 'bot_database.db'
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                fio TEXT,
                class_name TEXT,
                consent_given BOOLEAN,
                consent_date TIMESTAMP,
                registration_date TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                request_text TEXT,
                response_text TEXT,
                request_time TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, chat_id, fio, class_name):
        self.cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, chat_id, fio, class_name, consent_given, consent_date, registration_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, chat_id, fio, class_name, False, None, datetime.now()))
        self.conn.commit()
    
    def update_consent(self, user_id, consent):
        self.cursor.execute('''
            UPDATE users 
            SET consent_given = ?, consent_date = ?
            WHERE user_id = ?
        ''', (consent, datetime.now() if consent else None, user_id))
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def add_request(self, user_id, chat_id, request_text, response_text):
        self.cursor.execute('''
            INSERT INTO requests (user_id, chat_id, request_text, response_text, request_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, chat_id, request_text, response_text, datetime.now()))
        self.conn.commit()
    
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()