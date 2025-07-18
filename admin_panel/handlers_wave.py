from datetime import datetime
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

        import os
        if not os.path.exists(WAVE_FILE):
            bot.send_message(message.chat.id, "Волна ещё не начиналась.")
            return

        with open(WAVE_FILE, "r") as f:
            wave_start = datetime.fromisoformat(f.read().strip())

        users_with_ticket, free_tickets, all_users = get_wave_stats(wave_start)

        # Подсчёт числа волн
        if os.path.exists("waves.txt"):
            with open("waves.txt", "r") as wf:
                total_waves = len([line for line in wf if line.strip()])
        else:
            total_waves = 1

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
