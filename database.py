import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        last_ticket_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT UNIQUE,
        assigned_to INTEGER,
        assigned_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_user_last_ticket_time(user_id):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT last_ticket_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row and row[0] else None

def update_user_ticket_time(user_id, assigned_at):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_ticket_at=? WHERE user_id=?", (assigned_at, user_id))
    conn.commit()
    conn.close()

def sync_ticket_folder(folder):
    import os
    files = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    for file in files:
        full_path = os.path.join(folder, file)
        cur.execute("INSERT OR IGNORE INTO tickets (file_path) VALUES (?)", (full_path,))
    conn.commit()
    conn.close()

def get_free_ticket():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM tickets WHERE assigned_to IS NULL LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def assign_ticket(file_path, user_id):
    now = datetime.now().isoformat()
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET assigned_to=?, assigned_at=? WHERE file_path=?", (user_id, now, file_path))
    conn.commit()
    conn.close()
    update_user_ticket_time(user_id, now)

def get_wave_stats(wave_start):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    # Количество пользователей, получивших билет в этой волне
    cur.execute("SELECT COUNT(*) FROM users WHERE last_ticket_at >= ?", (wave_start.isoformat(),))
    users_with_ticket = cur.fetchone()[0]
    # Количество невыданных билетов
    cur.execute("SELECT COUNT(*) FROM tickets WHERE assigned_to IS NULL")
    free_tickets = cur.fetchone()[0]
    # Всего пользователей
    cur.execute("SELECT COUNT(*) FROM users")
    all_users = cur.fetchone()[0]
    conn.close()
    return users_with_ticket, free_tickets, all_users

def get_user_id_by_username(username):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_user_ids():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return user_ids
