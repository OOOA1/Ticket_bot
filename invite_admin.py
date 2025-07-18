import sqlite3
import secrets
import tempfile
import os
import xlsxwriter

DB_FILE = "users.db"
BOT_USERNAME = "todoVanekbot"  # без @

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

        # Автоширина (достаточно большая для ссылок)
        worksheet.set_column(0, 0, 22)
        worksheet.set_column(1, 1, 60)

        workbook.close()
        return tmp.name
