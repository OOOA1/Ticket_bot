from telebot import types
from .utils import admin_error_catcher, admin_required
from database import (
    add_admin,
    remove_admin,
    get_admins,
    get_user_id_by_username,
    FOUNDER_IDS
)
import logging
logger = logging.getLogger(__name__)

# === Исправление: приводим FOUNDER_IDS к списку чисел (int) ===
if isinstance(FOUNDER_IDS, str):
    FOUNDER_IDS = [int(x) for x in FOUNDER_IDS.replace(' ', '').split(',') if x]

def register_admins_handlers(bot):
    @bot.message_handler(commands=['add_admin'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_add_admin(message):
        logger.info("Команда /add_admin вызвана пользователем %d", message.from_user.id)
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ Нет прав для этой команды.")
            return

        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].startswith('@'):
            bot.reply_to(message, "Использование: /add_admin @username")
            return

        username = parts[1][1:]
        user_id = get_user_id_by_username(username)
        if not user_id:
            bot.reply_to(message, f"❌ Пользователь @{username} не найден.")
            return

        if user_id in ADMINS:
            bot.reply_to(message, f"❌ Пользователь @{username} уже является админом.")
            return

        add_admin(user_id)
        bot.reply_to(
            message,
            f"✅ Пользователь @{username} (ID {user_id}) добавлен в админы."
        )

    @bot.message_handler(commands=['remove_admin'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_remove_admin(message):
        logger.info("Команда /remove_admin вызвана пользователем %d", message.from_user.id)
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ Нет прав для этой команды.")
            return

        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].startswith('@'):
            bot.reply_to(message, "Использование: /remove_admin @username")
            return

        username = parts[1][1:]
        user_id = get_user_id_by_username(username)
        logger.info(f"Удаление админа: @{username} найден user_id={user_id}")

        if not user_id:
            bot.reply_to(message, f"❌ Пользователь @{username} не найден.")
            return

        try:
            user_id = int(user_id)
        except Exception:
            bot.reply_to(message, f"❌ Ошибка user_id для @{username}: {user_id}")
            return

        if user_id not in ADMINS:
            bot.reply_to(message, f"❌ Пользователь @{username} не является админом.")
            return

        if user_id in FOUNDER_IDS:
            bot.reply_to(message, "❌ Нельзя удалить этого администратора.")
            return

        if user_id == message.from_user.id:
            bot.reply_to(message, "❌ Нельзя удалить самого себя.")
            return

        remove_admin(user_id)
        bot.reply_to(
            message,
            f"✅ Пользователь @{username} (ID {user_id}) удалён из админов."
        )

    @bot.message_handler(commands=['myid'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_myid(message):
        bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")
