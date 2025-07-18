import telebot
from config import BOT_TOKEN, DEFAULT_TICKET_FOLDER
from database import *  # init_db, add_user
from datetime import datetime
import sqlite3

# --- Новый импорт для админки ---
from admin_panel import register_admin_handlers

bot = telebot.TeleBot(BOT_TOKEN)

# Регистрируем все админские хендлеры
register_admin_handlers(bot)

init_db()
# sync_ticket_folder(DEFAULT_TICKET_FOLDER)

@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()

    # 1) Пользователь без параметра или с неправильным форматом
    if len(args) < 2 or not args[1].startswith("inv_"):
        bot.send_message(
            message.chat.id,
            "ВЫ ПЫТАЕТЕСЬ НАЧАТЬ ОБЩЕНИЕ С БОТОМ БЕЗ ПРИГЛАШЕНИЯ. "
            "ДЛЯ ПОЛУЧЕНИЯ ПРИГЛАШЕНИЯ СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return

    invite_code = args[1]

    # 2) Проверяем invite-код в базе
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT is_used FROM invite_codes WHERE invite_code = ?",
        (invite_code,)
    )
    row = cur.fetchone()

    # 2.1) Код не найден
    if not row:
        conn.close()
        bot.send_message(
            message.chat.id,
            "❗️ ПРИГЛАШЕНИЕ НЕ НАЙДЕНО. СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return

    # 2.2) Код уже использован
    if row[0] == 1:
        conn.close()
        bot.send_message(
            message.chat.id,
            "⛔️ ЭТА ССЫЛКА УЖЕ ИСПОЛЬЗОВАНА. ПОЖАЛУЙСТА, СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return

    # 3) Активируем invite и регистрируем пользователя
    cur.execute(
        "UPDATE invite_codes SET is_used = 1, user_id = ?, username = ? WHERE invite_code = ?",
        (message.from_user.id, message.from_user.username, invite_code)
    )
    conn.commit()
    conn.close()

    add_user(message.from_user.id, message.from_user.username)

    # 4) Приветственное сообщение
    bot.send_message(
        message.chat.id,
        f"ПРИВЕТ, {message.from_user.first_name}! СПАСИБО, ЧТО ПОДПИСАЛИСЬ НА РАССЫЛКУ БИЛЕТОВ. "
        "СКОРО ВЫ ПОЛУЧИТЕ ИНФОРМАЦИЮ О ДОСТУПНЫХ МАТЧАХ."
    )

# Запуск бота
print("Бот запущен.")
bot.infinity_polling()
