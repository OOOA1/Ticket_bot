import sqlite3
from datetime import datetime
from uuid import uuid4
import hashlib
import os


DB_PATH = "users.db"
FOUNDER_IDS = [781477708]

def init_failed_deliveries_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS failed_deliveries (
        user_id INTEGER PRIMARY KEY,
        ticket_path TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def add_failed_delivery(user_id, ticket_path):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO failed_deliveries (user_id, ticket_path)
        VALUES (?, ?)
    """, (user_id, ticket_path))
    conn.commit()
    conn.close()

def remove_failed_delivery(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM failed_deliveries WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_failed_deliveries():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, ticket_path FROM failed_deliveries")
    rows = cur.fetchall()
    conn.close()
    return rows  # [(user_id, ticket_path), ...]

def clear_failed_deliveries():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM failed_deliveries")
    conn.commit()
    conn.close()

def init_db():
    init_user_table()
    init_ticket_table()
    init_wave_table()
    init_wave_confirmation_table()
    init_failed_deliveries_table()
    init_admins_table()

    for founder in FOUNDER_IDS:
        add_admin(founder)

# === USERS ===
def init_user_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        last_ticket_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_user_last_ticket_time(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_ticket_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row and row[0] else None

def update_user_ticket_time(user_id, assigned_at):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_ticket_at=? WHERE user_id=?", (assigned_at, user_id))
    conn.commit()
    conn.close()

def get_user_id_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return user_ids

# === TICKETS ===
def init_ticket_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS tickets")
    cur.execute("""
    CREATE TABLE tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT UNIQUE,
        hash TEXT UNIQUE,
        original_name TEXT,
        uploaded_by INTEGER,
        uploaded_at TEXT,
        assigned_to INTEGER,
        assigned_at TEXT,
        archived_unused INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def insert_ticket(file_path, file_hash, original_name, uploaded_by):
    uploaded_at = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (file_path, hash, original_name, uploaded_by, uploaded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (file_path, file_hash, original_name, uploaded_by, uploaded_at))
    conn.commit()
    conn.close()

def is_duplicate_hash(file_hash):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM tickets WHERE hash=?", (file_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def get_free_ticket():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM tickets WHERE assigned_to IS NULL AND (archived_unused IS NULL OR archived_unused=0) LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def assign_ticket(file_path, user_id):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET assigned_to=?, assigned_at=? WHERE file_path=?", (user_id, now, file_path))
    conn.commit()
    conn.close()
    update_user_ticket_time(user_id, now)

def reserve_ticket_for_user(file_path, user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET assigned_to=?, assigned_at=NULL WHERE file_path=?", (user_id, file_path))
    conn.commit()
    conn.close()

def mark_ticket_archived_unused(file_path):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET archived_unused=1 WHERE file_path=? AND assigned_to IS NULL", (file_path,))
    conn.commit()
    conn.close()



# === WAVES ===
def init_wave_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS waves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wave_start TEXT NOT NULL,
        created_by INTEGER,
        confirmed_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def create_new_wave(created_by):
    now = datetime.now().replace(microsecond=0).isoformat(" ")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO waves (wave_start, created_by, confirmed_at) VALUES (?, ?, ?)", (now, created_by, now))
    conn.commit()
    conn.close()
    return now

def get_latest_wave():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT wave_start FROM waves ORDER BY wave_start DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row else None

# === WAVE CONFIRMATIONS ===
def init_wave_confirmation_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wave_confirmations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        status TEXT,
        started_at TEXT,
        confirmed_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def start_wave_confirmation(admin_id):
    now = datetime.now().replace(microsecond=0).isoformat(" ")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO wave_confirmations (admin_id, status, started_at) VALUES (?, 'awaiting', ?)", (admin_id, now))
    conn.commit()
    conn.close()

def confirm_wave(admin_id):
    now = datetime.now().replace(microsecond=0).isoformat(" ")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE wave_confirmations 
        SET status = 'confirmed', confirmed_at = ? 
        WHERE admin_id = ? AND status = 'awaiting'
    """, (now, admin_id))
    conn.commit()
    conn.close()

def has_pending_confirmation(admin_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM wave_confirmations WHERE admin_id = ? AND status = 'awaiting'", (admin_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None

# === STATS ===
def get_wave_stats(wave_start):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE last_ticket_at >= ?", (wave_start.isoformat(),))
    users_with_ticket = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tickets WHERE assigned_to IS NULL")
    free_tickets = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    all_users = cur.fetchone()[0]
    conn.close()
    return users_with_ticket, free_tickets, all_users

def get_free_ticket_count():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tickets WHERE assigned_to IS NULL")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_wave_count():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM waves")
    count = cur.fetchone()[0]
    conn.close()
    return count

# АДМИНЫ

def init_admins_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id    INTEGER PRIMARY KEY,
            added_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_admin(user_id: int):
    """Добавить user_id в таблицу admins (игнорировать, если уже есть)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_admin(user_id: int):
    """Удалить user_id из таблицы admins."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_admins() -> list[int]:
    """Вернуть список всех user_id из таблицы admins."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in cur.fetchall()]
    conn.close()
    return admins