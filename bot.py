import telebot
from config import BOT_TOKEN
from database import init_db, add_user, get_admins
from admin_panel import register_admin_handlers
import sqlite3

bot = telebot.TeleBot(BOT_TOKEN)

# Регистрируем админские хендлеры
register_admin_handlers(bot)

# Инициализируем БД
init_db()

@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()
    user_id = message.from_user.id

    # 1) Без INVITE_CODE или неправильный формат
    if len(args) < 2 or not args[1].startswith("inv_"):
        bot.send_message(
            message.chat.id,
            "ВЫ ПЫТАЕТЕСЬ НАЧАТЬ ОБЩЕНИЕ С БОТОМ БЕЗ ПРИГЛАШЕНИЯ. ДЛЯ ПОЛУЧЕНИЯ ПРИГЛАШЕНИЯ СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return
    invite_code = args[1]

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    # 2) Проверка, подписан ли уже пользователь
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone():
        # Пользователь пытается активировать второй код: "сжечь" invite и уведомить админов
        cur.execute(
            "UPDATE invite_codes SET is_used = 1 WHERE invite_code = ?",
            (invite_code,)
        )
        conn.commit()
        conn.close()
    
        # Уведомляем всех админов из БД
        for admin_id in get_admins():
            try:
                bot.send_message(
                    admin_id,
                    f"⚠️ Пользователь {user_id} попытался активировать второй инвайт-код {invite_code}. Код заблокирован."
                )
            except Exception:
                # на случай, если какой-то админ заблокировал бота
                pass

        bot.send_message(
            message.chat.id,
            "ВЫ УЖЕ ПОДПИСАНЫ НА РАССЫЛКУ. ВАШЕ ДЕЙСТВИЕ ЗАБЛОКИРОВАНО И АДМИНЫ УВЕДОМЛЕНЫ."
        )
        return

    # 3) Проверка invite-кода в базе
    cur.execute("SELECT is_used FROM invite_codes WHERE invite_code = ?", (invite_code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        bot.send_message(
            message.chat.id,
            "❗️ ПРИГЛАШЕНИЕ НЕ НАЙДЕНО. СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return
    if row[0] == 1:
        conn.close()
        bot.send_message(
            message.chat.id,
            "⛔️ ЭТА ССЫЛКА УЖЕ ИСПОЛЬЗОВАНА. ПОЖАЛУЙСТА, СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ."
        )
        return

    # 4) Активируем invite и регистрируем пользователя
    cur.execute(
        "UPDATE invite_codes SET is_used = 1, user_id = ?, username = ? WHERE invite_code = ?",
        (user_id, message.from_user.username, invite_code)
    )
    conn.commit()
    conn.close()

    add_user(user_id, message.from_user.username)

    # 5) Приветственное сообщение
    bot.send_message(
        message.chat.id,
        f"ПРИВЕТ, {message.from_user.first_name}! СПАСИБО, ЧТО ПОДПИСАЛИСЬ НА РАССЫЛКУ БИЛЕТОВ. "
        "СКОРО ВЫ ПОЛУЧИТЕ ИНФОРМАЦИЮ О ДОСТУПНЫХ МАТЧАХ."
    )

# Запуск бота
print("Бот запущен.")
bot.infinity_polling()