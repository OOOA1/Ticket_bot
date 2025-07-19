from datetime import datetime
from .utils import admin_error_catcher, load_admins
from telebot import types
import os
from config import DEFAULT_TICKET_FOLDER
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
    pending_wave_confirm = {}

    @bot.message_handler(commands=['new_wave'])
    @admin_error_catcher(bot)
    def handle_new_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет прав запускать новую волну.")
            return

        from database import get_free_ticket_count, get_all_user_ids
        free_tickets = get_free_ticket_count()
        user_count = len(get_all_user_ids())

        if free_tickets < user_count:
            bot.send_message(
                message.chat.id,
                f"⚠️ Недостаточно билетов для всех пользователей!\n"
                f"Свободных билетов: {free_tickets}\n"
                f"Пользователей: {user_count}\n"
                "Продолжить новую волну? (Да/Нет)"
            )
            # Ждём ответ от админа
            pending_wave_confirm[message.from_user.id] = True
            return

        # Если хватает билетов, сразу запускаем волну
        start_wave(message)

    @bot.message_handler(func=lambda m: pending_wave_confirm.get(m.from_user.id, False) and m.text.lower() in ["да", "нет"])
    def confirm_wave_start(message):
        if message.text.lower() == "да":
            start_wave(message)
        else:
            bot.send_message(message.chat.id, "Запуск новой волны отменён. Вы можете дозагрузить билеты через /upload_zip_add.")
        pending_wave_confirm.pop(message.from_user.id, None)

    def start_wave(message):
        from database import create_new_wave, clear_failed_deliveries
        now = create_new_wave(message.from_user.id)
        clear_failed_deliveries()
        bot.send_message(message.chat.id, f"Новая волна началась! Время: {now}")

    @bot.message_handler(commands=['stats'])
    @admin_error_catcher(bot)
    def handle_stats(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        from database import get_latest_wave
        wave_start = get_latest_wave()
        if not wave_start:
            bot.send_message(message.chat.id, "Волна ещё не начиналась.")
            return

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