import sqlite3 as sq

db = sq.connect('tg.db')
cur = db.cursor()

async def db_start():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY,
            payment_id TEXT,
            end_date TEXT,
            access_key TEXT
        )
    ''')