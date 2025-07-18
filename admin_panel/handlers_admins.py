# handlers_admins.py

from telebot import types
from .utils import admin_error_catcher     # теперь обёртка ошибок берётся из utils
from database import (
    add_admin,
    remove_admin,
    get_admins,
    get_user_id_by_username,
    FOUNDER_IDS
)

def register_admins_handlers(bot):
    @bot.message_handler(commands=['add_admin'])
    @admin_error_catcher(bot)
    def handle_add_admin(message):
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
    @admin_error_catcher(bot)
    def handle_remove_admin(message):
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
        if not user_id:
            bot.reply_to(message, f"❌ Пользователь @{username} не найден.")
            return

        if user_id not in ADMINS:
            bot.reply_to(message, f"❌ Пользователь @{username} не является админом.")
            return

        if user_id in FOUNDER_IDS:
            bot.reply_to(message, "❌ Нельзя удалить основателя из админов.")
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
    @admin_error_catcher(bot)
    def handle_myid(message):
        bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")
