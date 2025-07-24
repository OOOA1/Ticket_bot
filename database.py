import sqlite3
from datetime import datetime
from uuid import uuid4
import hashlib
import os


DB_PATH = "users.db"
FOUNDER_IDS = [5477727657]

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
    init_failed_deliveries_table()
    init_admins_table()
    init_wave_meta_table()
    init_invite_codes_table()
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

def init_invite_codes_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invite_code TEXT UNIQUE,
            username TEXT,
            user_id INTEGER,
            is_used INTEGER DEFAULT 0
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

def is_registered(user_id: int) -> bool:
    """
    Проверяет, есть ли user_id в таблице users.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None

def delete_user_everywhere(user_id: int, username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Удаление из основной таблицы пользователей
    cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # Удаление из invite_codes
    cur.execute("DELETE FROM invite_codes WHERE user_id = ?", (user_id,))

    # Удаление из failed_deliveries
    cur.execute("DELETE FROM failed_deliveries WHERE user_id = ?", (user_id,))

    # --- Новый блок: удаление из tickets ---
    # Сбросить assigned_to для всех билетов пользователя
    cur.execute("UPDATE tickets SET assigned_to = NULL, assigned_at = NULL WHERE assigned_to = ?", (user_id,))

    # Если хочешь убрать билеты, загруженные этим пользователем (uploaded_by):
    # cur.execute("DELETE FROM tickets WHERE uploaded_by = ?", (user_id,))

    changes = conn.total_changes
    conn.commit()
    conn.close()

    return changes > 0

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

def resolve_user_id(user_ref):
    """
    Возвращает user_id по username (с @) или по числу (user_id).
    Если ничего не найдено — возвращает None.
    """
    if isinstance(user_ref, int) or (isinstance(user_ref, str) and user_ref.isdigit()):
        return int(user_ref)
    username = user_ref
    if username.startswith("@"):
        username = username[1:]
    return get_user_id_by_username(username)

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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT UNIQUE,
        hash TEXT UNIQUE,
        original_name TEXT,
        uploaded_by INTEGER,
        uploaded_at TEXT,
        assigned_to INTEGER,
        assigned_at TEXT,
        archived_unused INTEGER DEFAULT 0,
        lost INTEGER DEFAULT 0,
        wave_id INTEGER
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

def get_free_ticket(current_wave_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT file_path FROM tickets
        WHERE assigned_to IS NULL
        AND archived_unused = 0
        AND lost = 0
        AND wave_id = ?
    """, (current_wave_id,))
    files = [row[0] for row in cur.fetchall()]
    conn.close()
    for f in files:
        if os.path.isfile(f):
            return f
    return None


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

def mark_ticket_lost(file_path):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET lost=1 WHERE file_path=? AND assigned_to IS NULL", (file_path,))
    conn.commit()
    conn.close()

def archive_missing_tickets():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM tickets WHERE assigned_to IS NULL AND archived_unused=0 AND lost=0")
    lost_count = 0
    for (file_path,) in cur.fetchall():
        if not os.path.isfile(file_path):
            cur.execute("UPDATE tickets SET lost=1 WHERE file_path=?", (file_path,))
            lost_count += 1
    conn.commit()
    conn.close()
    return lost_count

def archive_all_old_free_tickets():
    """
    Отмечает как archived_unused=1 все невыданные билеты (assigned_to IS NULL),
    lost=0, archived_unused=0, и файл на месте.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM tickets WHERE assigned_to IS NULL AND archived_unused=0 AND lost=0")
    for (file_path,) in cur.fetchall():
        if os.path.isfile(file_path):
            cur.execute("UPDATE tickets SET archived_unused=1 WHERE file_path=?", (file_path,))
    conn.commit()
    conn.close()

def release_ticket(ticket_path):
    """
    Освободить один билет: сбросить assigned_to и assigned_at,
    чтобы он стал вновь доступным.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET assigned_to = NULL, assigned_at = NULL WHERE file_path = ?",
        (ticket_path,)
    )
    conn.commit()
    conn.close()

def clear_user_assignments(user_id, exclude_path=None):
    """
    Снять все назначения билетов у пользователя (optionally, кроме одного).
    Это предотвращает ситуацию, когда у одного user_id «висят» несколько билетов.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if exclude_path:
        cur.execute(
            "UPDATE tickets SET assigned_to = NULL, assigned_at = NULL "
            "WHERE assigned_to = ? AND file_path != ?",
            (user_id, exclude_path)
        )
    else:
        cur.execute(
            "UPDATE tickets SET assigned_to = NULL, assigned_at = NULL WHERE assigned_to = ?",
            (user_id,)
        )
    conn.commit()
    conn.close()

# --- Фильтры для статистики ---
def get_stats_statuses():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Свободные: НЕ выданы, не архив, не lost, файл существует
    cur.execute("SELECT file_path FROM tickets WHERE assigned_to IS NULL AND archived_unused=0 AND lost=0")
    free_files = [f for (f,) in cur.fetchall() if os.path.isfile(f)]
    free_tickets = len(free_files)

    # Выданные: assigned_to IS NOT NULL, lost=0
    cur.execute("SELECT COUNT(*) FROM tickets WHERE assigned_to IS NOT NULL AND lost=0")
    issued_tickets = cur.fetchone()[0]

    # Утраченные: lost=1
    cur.execute("SELECT COUNT(*) FROM tickets WHERE lost=1")
    lost_tickets = cur.fetchone()[0]

    conn.close()
    return free_tickets, issued_tickets, lost_tickets

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
    wave_id = cur.lastrowid
    conn.commit()
    conn.close()
    return now, wave_id

def get_latest_wave():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT wave_start FROM waves ORDER BY wave_start DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row else None

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

def is_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь админом (по user_id).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None

def init_wave_meta_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wave_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            status TEXT NOT NULL,
            prepared_at TEXT,
            wave_start TEXT
        )
    """)
    # вставим одну строку, если её нет
    cur.execute("INSERT OR IGNORE INTO wave_meta (id, status) VALUES (1, 'idle')")
    conn.commit()
    conn.close()

def set_wave_state(status, prepared_at=None, wave_start=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE wave_meta SET status = ?, prepared_at = ?, wave_start = ? WHERE id = 1
    """, (status, prepared_at, wave_start))
    conn.commit()
    conn.close()

def get_wave_state():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT status, prepared_at, wave_start FROM wave_meta WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return {
        "status": row[0],
        "prepared_at": row[1],
        "wave_start": row[2]
    }

def get_current_wave_id():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM waves ORDER BY wave_start DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None