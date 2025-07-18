import os

from datetime import datetime
from .utils import admin_error_catcher, load_admins
from telebot import types

from config import WAVE_FILE, DEFAULT_TICKET_FOLDER
from database import (
    get_wave_stats,
    create_new_wave,
    get_free_ticket_count,
    get_latest_wave,
    get_wave_count,
    clear_failed_deliveries,        # <<< добавь импорт
    get_all_failed_deliveries,      # <<< для статистики
)
from .utils import admin_error_catcher, load_admins
from .handlers_mass_send import register_mass_send_handler

from database import (
    get_wave_stats,
    create_new_wave,
    get_free_ticket_count,
    get_latest_wave,
    get_wave_count,
)

def register_wave_handlers(bot):
    send_mass_send_keyboard = register_mass_send_handler(bot)

    @bot.message_handler(commands=['new_wave'])
    @admin_error_catcher(bot)
    def handle_new_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет прав запускать новую волну.")
            return

        if get_free_ticket_count() == 0:
            bot.send_message(
                message.chat.id,
                "❌ Нельзя начать волну — нет доступных билетов. Сначала загрузите билеты через /upload_zip."
            )
            return

        # создаём запись в БД и получаем время старта
        now = create_new_wave(message.from_user.id)
        with open(WAVE_FILE, "w") as f:
            f.write(now)
        clear_failed_deliveries()     # <<< очищаем "ожидающих доставки"
        bot.send_message(message.chat.id, f"Новая волна началась! Время: {now}")
        send_mass_send_keyboard(message.chat.id)

    @bot.message_handler(commands=['stats'])
    @admin_error_catcher(bot)
    def handle_stats(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        
        wave_start = get_latest_wave()
        if not wave_start:
            bot.send_message(message.chat.id, "Волна ещё не начиналась.")
            return

        # теперь передаём в get_wave_stats актуальный datetime
        users_with_ticket, free_tickets, all_users = get_wave_stats(wave_start)
        total_waves = get_wave_count()

        pending = len(get_all_failed_deliveries())   # <<< число ожидающих доставки

        text = (
            f"📊 Статистика по текущей волне:\n"
            f"— Пользователей с билетом: {users_with_ticket}\n"
            f"— Свободных билетов: {free_tickets}\n"
            f"— Всего пользователей: {all_users}\n"
            f"— Ожидают доставки: {pending}\n"
            f"— Всего волн было: {total_waves}"
        )
        bot.send_message(message.chat.id, text)