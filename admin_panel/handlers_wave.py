from datetime import datetime
from .utils import admin_error_catcher, load_admins

from database import (
    create_new_wave,
    get_all_user_ids,
    archive_missing_tickets,
    clear_failed_deliveries,
    get_stats_statuses,
    get_wave_count,
    get_latest_wave,
    get_all_failed_deliveries,
)

def register_wave_handlers(bot):
    @bot.message_handler(commands=['new_wave'])
    @admin_error_catcher(bot)
    def handle_new_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет прав запускать новую волну.")
            return

        # 1. Чистим "битые" билеты (утраченные — удалённые вручную)
        archive_missing_tickets()


        # 3. Считаем только реально доступные билеты
        free_tickets, _, _ = get_stats_statuses()
        user_count = len(get_all_user_ids())

        if free_tickets < user_count:
            bot.send_message(
                message.chat.id,
                f"❌ Недостаточно билетов для всех пользователей!\n"
                f"Свободных билетов: {free_tickets}\n"
                f"Пользователей: {user_count}\n"
                "Загрузите дополнительные билеты через /upload_zip_add."
            )
            return

        # 4. Стартуем волну, очищаем pending-доставки
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

        wave_start = get_latest_wave()
        if not wave_start:
            bot.send_message(message.chat.id, "Волна ещё не начиналась.")
            return

        free, issued, lost = get_stats_statuses()
        total_waves = get_wave_count()
        pending = len(get_all_failed_deliveries())

        text = (
            f"📊 Статистика по текущей волне:\n"
            f"— Свободных билетов: {free}\n"
            f"— Выданных билетов: {issued}\n"
            f"— Утраченных билетов: {lost}\n"
            f"— Ожидают доставки: {pending}\n"
            f"— Всего волн было: {total_waves}"
        )
        bot.send_message(message.chat.id, text)
