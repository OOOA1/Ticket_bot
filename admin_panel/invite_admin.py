import sqlite3
import secrets
import tempfile
import xlsxwriter
from config import BOT_USERNAME
from database import DB_PATH as DB_FILE


def generate_invites(count):
    codes = set()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS invite_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invite_code TEXT UNIQUE,
        username TEXT,
        user_id INTEGER,
        is_used INTEGER DEFAULT 0
    )
    ''')
    conn.commit()

    def generate_code():
        return 'inv_' + secrets.token_hex(4)

    while len(codes) < count:
        code = generate_code()
        try:
            cur.execute("INSERT INTO invite_codes (invite_code, is_used) VALUES (?, 0)", (code,))
            codes.add(code)
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    conn.close()
    return codes

def export_invites_xlsx(codes):
    # Создаем временный .xlsx-файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        workbook = xlsxwriter.Workbook(tmp.name)
        worksheet = workbook.add_worksheet("Invite Codes")

        # Заголовки
        worksheet.write(0, 0, "invite_code")
        worksheet.write(0, 1, "invite_link")

        # Данные
        for idx, code in enumerate(codes, 1):
            link = f"https://t.me/{BOT_USERNAME}?start={code}"
            worksheet.write(idx, 0, code)
            worksheet.write(idx, 1, link)

        # Автоширина
        worksheet.set_column(0, 0, 22)
        worksheet.set_column(1, 1, 60)

        workbook.close()
        return tmp.name

def export_users_xlsx():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Получаем пользователей с активированным invite-кодом
    cur.execute("""
        SELECT invite_code, username, user_id
        FROM invite_codes
        WHERE user_id IS NOT NULL
    """)
    rows = cur.fetchall()

    # Считаем уникальных пользователей
    user_count = len({row[2] for row in rows if row[2] is not None})

    # Считаем админов
    cur.execute("SELECT COUNT(*) FROM admins")
    admin_count = cur.fetchone()[0]

    conn.close()

    # Генерируем .xlsx
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        workbook = xlsxwriter.Workbook(tmp.name)
        worksheet = workbook.add_worksheet("Users")

        # Заголовки
        worksheet.write(0, 0, "invite_code")
        worksheet.write(0, 1, "username")
        worksheet.write(0, 2, "user_id")

        for idx, (invite_code, username, user_id) in enumerate(rows, 1):
            worksheet.write(idx, 0, invite_code)
            worksheet.write(idx, 1, f"@{username}" if username else "")
            worksheet.write(idx, 2, user_id)

        worksheet.set_column(0, 0, 22)
        worksheet.set_column(1, 1, 32)
        worksheet.set_column(2, 2, 18)

        # Числа пользователей и админов внизу (можно и в caption при отправке)
        worksheet.write(idx + 2, 0, f"Пользователей: {user_count}")
        worksheet.write(idx + 3, 0, f"Админов: {admin_count}")

        workbook.close()
        return tmp.name, user_count, admin_count
