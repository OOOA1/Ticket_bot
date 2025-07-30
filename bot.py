import telebot
from config import BOT_TOKEN
from database import init_db, add_user, get_admins
from admin_panel import register_admin_handlers
from admin_panel.utils import log_chat
from admin_panel.admin_menu import register_admin_menu
from telebot.handler_backends import BaseMiddleware
import sqlite3
import logging
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, use_class_middlewares=True)
register_admin_menu(bot)

class LogChatMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_types = ['message']

    def pre_process(self, message, data):
        user_id = message.from_user.id
        if message.text:
            log_chat(user_id, "USER", message.text)
        elif message.document:
            log_chat(user_id, "USER", f"[DOCUMENT] {message.document.file_name}")
        elif message.photo:
            log_chat(user_id, "USER", "[PHOTO]")
        elif message.audio:
            log_chat(user_id, "USER", "[AUDIO]")
        elif message.video:
            log_chat(user_id, "USER", "[VIDEO]")
        elif message.voice:
            log_chat(user_id, "USER", "[VOICE]")
        elif message.sticker:
            log_chat(user_id, "USER", "[STICKER]")
        else:
            log_chat(user_id, "USER", "[UNKNOWN TYPE]")
        return message, data

    def post_process(self, message, data, exception):
        # Пропуск
        pass

bot.setup_middleware(LogChatMiddleware())


# Регистрируем админские хендлеры
register_admin_handlers(bot)

# Инициализируем БД
init_db()

@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()
    user_id = message.from_user.id

    # ---------- ПРОВЕРКА USERNAME ----------
    if not message.from_user.username:
        bot.send_message(
            message.chat.id,
            "⛔️ У вас не установлен username в Telegram.\n\n"
            "Без него вы не сможете получить билет.\n\n"
            "Что делать:\n"
            "1. Откройте настройки Telegram.\n"
            "2. Установите имя пользователя (username).\n"
            "3. Снова перейдите по вашей пригласительной ссылке."
        )

        for admin_id in get_admins():
            try:
                bot.send_message(
                    admin_id,
                    f"⚠️ Пользователь {user_id} не смог активироваться по инвайту {args[1] if len(args)>1 else '[нет кода]'} — у него нет username.\n"
                    f"Инвайт не сожжён. Пользователь не добавлен в базу."
                )
            except Exception:
                pass
        return

    # 1) Без INVITE_CODE или неправильный формат
    if len(args) < 2 or not args[1].startswith("inv_"):
        bot.send_message(
            message.chat.id,
            "Вы пытаетесь начать общение с ботом без приглашения. Для получения приглоашения свяжитесь с администратором."
        )
        log_chat(user_id, "BOT", "Вы пытаетесь начать общение с ботом без приглашения. Для получения приглоашения свяжитесь с администратором.")
        return
    invite_code = args[1]
    logger.info("Пользователь %d пытается активировать код %s", user_id, invite_code)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    # 2) Проверка, подписан ли уже пользователь
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone():
        # Пользователь пытается активировать второй код: сжечь invite и уведомить администраторов
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
                pass  # если какой-то администратор заблокировал бота

        bot.send_message(
            message.chat.id,
            "Вы уже подписаны на рассылку. Ваше действие заблокировано и админы уведомлены."
        )
        log_chat(
            user_id,
            "BOT",
            "Вы уже подписаны на рассылку. Ваше действие заблокировано и админы уведомлены."
        )
        return

    # 3) Проверка invite-кода в базе
    cur.execute("SELECT is_used FROM invite_codes WHERE invite_code = ?", (invite_code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        bot.send_message(
            message.chat.id,
            "❗️ Приглашение не найдено. Свяжитесь с администратором."
        )
        log_chat(user_id, "BOT", "❗️ Приглашение не найдено. Свяжитесь с администратором.")
        return
    if row[0] == 1:
        conn.close()
        bot.send_message(
            message.chat.id,
            "⛔️ Эта ссылка уже использована. Пожалуйста, Свяжитесь с администратором."
        )
        log_chat(
            user_id,
            "BOT",
            "⛔️ Эта ссылка уже использована. Пожалуйста, Свяжитесь с администратором."
        )
        return

    # 4) Активируем invite и регистрируем пользователя
    cur.execute(
        "UPDATE invite_codes SET is_used = 1, user_id = ?, username = ? WHERE invite_code = ?",
        (user_id, message.from_user.username, invite_code)
    )
    conn.commit()
    conn.close()
    logger.info("Код %s активирован пользователем %d", invite_code, user_id)

    add_user(user_id, message.from_user.username)

    # 5) Приветственное сообщение
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! Спасибо, что подписались на рассылку билетов. "
        "Скоро вы получите информацию о доступных матчах⚽."
    )
    log_chat(user_id, "BOT", f"Привет, {message.from_user.first_name}! Спасибо, что подписались на рассылку билетов. "
                         "Скоро вы получите информацию о доступных матчах⚽.")

def run_bot():
    logger.info("Бот запущен и готов принимать команды")
    bot.infinity_polling(timeout=30, long_polling_timeout=10)

if __name__ == "__main__":
    run_bot()

@bot.message_handler(content_types=['text', 'document', 'photo', 'audio', 'video', 'voice', 'sticker'])
def handle_any_message(message):
    user_id = message.from_user.id

    if message.text:
        log_chat(user_id, "USER", message.text)
    elif message.document:
        log_chat(user_id, "USER", f"[DOCUMENT] {message.document.file_name}")
    elif message.photo:
        log_chat(user_id, "USER", "[PHOTO]")
    elif message.audio:
        log_chat(user_id, "USER", "[AUDIO]")
    elif message.video:
        log_chat(user_id, "USER", "[VIDEO]")
    elif message.voice:
        log_chat(user_id, "USER", "[VOICE]")
    elif message.sticker:
        log_chat(user_id, "USER", "[STICKER]")
    else:
        log_chat(user_id, "USER", "[UNKNOWN TYPE]")