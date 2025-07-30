import os
import tempfile
import sqlite3
import xlsxwriter

from .utils import admin_required, admin_error_catcher, logger
from database import DB_PATH, get_all_failed_deliveries
from admin_panel.invite_admin import export_users_xlsx
from config import BOT_USERNAME

def register_report_handler(bot):

    @bot.message_handler(commands=['full_report'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_full_report(message):
        logger.info("Команда /full_report вызвана пользователем %d", message.from_user.id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            workbook = xlsxwriter.Workbook(tmp.name)

            # --- USERS + ADMINS (лист Users) ---
            add_users_sheet(workbook)

            # --- TICKETS (лист Tickets) ---
            add_tickets_sheet(workbook)

            # --- FAILED DELIVERIES (лист Failed) ---
            add_failed_sheet(workbook)

            # --- INVITE CODES (лист Invites) ---
            add_invites_sheet(workbook)

            workbook.close()
            report_path = tmp.name

        with open(report_path, "rb") as doc:
            bot.send_document(
                message.chat.id, doc,
                caption="📊 Единый Excel-отчёт по системе (все вкладки в одном файле)"
            )
        os.remove(report_path)


def add_users_sheet(workbook):
    # Используем export_users_xlsx, но пишем напрямую в sheet
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT invite_code, username, user_id
        FROM invite_codes
        WHERE user_id IS NOT NULL
    """)
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM admins")
    admin_count = cur.fetchone()[0]

    user_count = len({row[2] for row in rows if row[2] is not None})

    ws = workbook.add_worksheet("Users")

    headers = ["invite_code", "username", "user_id"]
    for col, h in enumerate(headers):
        ws.write(0, col, h)

    for idx, (invite_code, username, user_id) in enumerate(rows, 1):
        ws.write(idx, 0, invite_code)
        ws.write(idx, 1, f"@{username}" if username else "")
        ws.write(idx, 2, user_id)

    ws.write(idx + 2, 0, f"Пользователей: {user_count}")
    ws.write(idx + 3, 0, f"Админов: {admin_count}")

    ws.set_column(0, 0, 22)
    ws.set_column(1, 1, 32)
    ws.set_column(2, 2, 18)
    conn.close()

def add_tickets_sheet(workbook):
    import sqlite3
    from database import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT file_path, original_name, assigned_to, assigned_at, archived_unused, lost, wave_id
        FROM tickets
    """)
    rows = cur.fetchall()
    conn.close()

    ws = workbook.add_worksheet("Tickets")
    headers = ["File Path", "Original Name", "Status", "Assigned To", "Assigned At", "Wave ID"]
    for col, hdr in enumerate(headers):
        ws.write(0, col, hdr)

    for i, (path, orig, assigned_to, assigned_at, archived_unused, lost, wave_id) in enumerate(rows, start=1):
        if lost:
            status = "LOST"
        elif assigned_to is not None:
            status = "SENT"
        elif archived_unused:
            status = "ARCHIVED"
        else:
            status = "AVAILABLE"
        ws.write(i, 0, path)
        ws.write(i, 1, orig)
        ws.write(i, 2, status)
        ws.write(i, 3, assigned_to or "")
        ws.write(i, 4, assigned_at or "")
        ws.write(i, 5, wave_id or "")

    ws.set_column(0, 0, 60)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 14)
    ws.set_column(3, 3, 16)
    ws.set_column(4, 4, 26)
    ws.set_column(5, 5, 10)

def add_failed_sheet(workbook):
    # Аналогично failed_report, но без отправки файла, а в нужный ws
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    failed = dict(get_all_failed_deliveries())

    ws = workbook.add_worksheet("Failed")
    headers = ["user_id", "username", "ticket_path", "original_name", "статус", "Не доставлено"]
    ws.write_row(0, 0, headers)

    for idx, (user_id, ticket_path) in enumerate(failed.items(), 1):
        cur.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        username = f"@{row[0]}" if row and row[0] else ""

        cur.execute("""
            SELECT original_name, lost, archived_unused, assigned_to
            FROM tickets
            WHERE file_path=?
        """, (ticket_path,))
        row = cur.fetchone()

        if row:
            original_name, lost, archived, assigned = row
            if lost:
                status = "Утраченный"
            elif archived:
                status = "Архивный"
            elif assigned:
                status = "Выдан"
            else:
                status = "Активный"
        else:
            original_name = "❓ не найден"
            status = "❌ нет данных"

        ws.write_row(idx, 0, [
            user_id,
            username,
            ticket_path,
            original_name,
            status,
            "Да"
        ])

    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 20)
    ws.set_column(2, 2, 60)
    ws.set_column(3, 3, 30)
    ws.set_column(4, 4, 20)
    ws.set_column(5, 5, 18)
    conn.close()

def add_invites_sheet(workbook):
    # Все инвайты (не только активированные)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    from config import BOT_USERNAME

    cur.execute("""
        SELECT invite_code, is_used, username, user_id
        FROM invite_codes
    """)
    rows = cur.fetchall()

    ws = workbook.add_worksheet("Invites")
    headers = ["invite_code", "invite_link", "is_used", "username", "user_id"]
    ws.write_row(0, 0, headers)

    for idx, (code, is_used, username, user_id) in enumerate(rows, 1):
        link = f"https://t.me/{BOT_USERNAME}?start={code}"
        ws.write(idx, 0, code)
        ws.write(idx, 1, link)
        ws.write(idx, 2, "Да" if is_used else "Нет")
        ws.write(idx, 3, f"@{username}" if username else "")
        ws.write(idx, 4, user_id or "")

    ws.set_column(0, 0, 22)
    ws.set_column(1, 1, 60)
    ws.set_column(2, 2, 10)
    ws.set_column(3, 3, 24)
    ws.set_column(4, 4, 14)
    conn.close()
