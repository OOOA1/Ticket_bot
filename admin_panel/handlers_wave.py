import sqlite3

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
    set_wave_state,
    get_wave_state,
    get_admins,
    archive_all_old_free_tickets,
)

def register_wave_handlers(bot):
    @bot.message_handler(commands=['new_wave'])
    @admin_error_catcher(bot)
    def handle_new_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ У вас нет прав.")
            return

        state = get_wave_state()

        # 🚫 Запрет, если волна ещё активна
        if state["status"] == "active":
            bot.send_message(message.chat.id, "⚠️ Волна уже активна. Завершите её командой /end_wave.")
            return

        # 🚫 Запрет, если волна уже была подготовлена и не завершена
        if state["status"] == "awaiting_confirm":
            bot.send_message(message.chat.id, "⚠️ Подготовка волны уже ведётся. Завершите текущую волну командой /end_wave перед созданием новой.")
            return

        # 🚫 Запрет, если в idle уже загружены билеты без волны
        if state["status"] == "idle":
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE assigned_to IS NULL
                AND archived_unused = 0
                AND lost = 0
                AND wave_id IS NULL
            """)
            pending = cur.fetchone()[0]
            conn.close()

            if pending > 0:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Обнаружено {pending} билетов, загруженных до запуска волны.\n"
                    f"Пожалуйста, удалите их или завершите текущую волну командой /end_wave перед созданием новой."
                )
                return

        # ✅ Всё чисто — запускаем новую волну

        lost_count = archive_missing_tickets()
        archive_all_old_free_tickets()
        clear_failed_deliveries()

        now = datetime.now().isoformat()
        set_wave_state("awaiting_confirm", prepared_at=now)

        msg = (
            f"🛠 Подготовка новой волны завершена.\n"
            f"⏳ Время: {now}\n"
        )
        if lost_count > 0:
            msg += f"⚠️ Помечено как утраченных: {lost_count} билетов.\n"
        msg += "📥 Загрузите билеты и подтвердите волну через /confirm_wave."

        bot.send_message(message.chat.id, msg)


    @bot.message_handler(commands=['confirm_wave'])
    @admin_error_catcher(bot)
    def handle_confirm_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ У вас нет прав.")
            return

        state = get_wave_state()
        if state["status"] != "awaiting_confirm":
            bot.send_message(message.chat.id, "⚠️ Сейчас нельзя подтвердить волну. Сначала выполните /new_wave.")
            return

        prepared_at = datetime.fromisoformat(state["prepared_at"])
        all_users = get_all_user_ids()
        admins = set(get_admins())
        user_count = len([uid for uid in all_users if uid not in admins])

        # 🧹 Проверка на утраченные билеты
        lost_count = archive_missing_tickets()

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM tickets
            WHERE assigned_to IS NULL
            AND archived_unused = 0
            AND lost = 0
            AND uploaded_at > ?
        """, (prepared_at.isoformat(),))
        available_tickets = cur.fetchone()[0]
        conn.close()

        if available_tickets < user_count or available_tickets == 0:
            msg = (
                f"❌ Подтверждение невозможно — недостаточно новых билетов.\n"
                f"👤 Пользователей: {user_count}\n"
                f"🎟 Новых билетов: {available_tickets}\n"
            )
            if lost_count > 0:
                msg += f"⚠️ Также обнаружено {lost_count} утраченных билетов.\n"
            msg += "Для загрузки билетов используйте /upload_zip"
            bot.send_message(message.chat.id, msg)
            return

        wave_start, wave_id = create_new_wave(message.from_user.id)

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("""
            UPDATE tickets
            SET assigned_at = NULL, wave_id = ?
            WHERE assigned_to IS NULL
            AND archived_unused = 0
            AND lost = 0
            AND uploaded_at > ?
        """, (wave_id, prepared_at.isoformat()))
        conn.commit()
        conn.close()

        set_wave_state("active", wave_start=wave_start)

        msg = (
            f"✅ Волна №{wave_id} подтверждена и активирована!\n"
            f"Время начала: {wave_start}\n"
        )
        if lost_count > 0:
            msg += f"⚠️ Также во время запуска обнаружено {lost_count} утраченных билетов.\n"
        msg += "Теперь можно использовать /send_tickets."

        bot.send_message(message.chat.id, msg)

    
    @bot.message_handler(commands=['end_wave'])
    @admin_error_catcher(bot)
    def handle_end_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ У вас нет прав.")
            return

        state = get_wave_state()
        if state["status"] != "active":
            bot.send_message(message.chat.id, "⚠️ Сейчас нет активной волны.")
            return

        # 🧹 Проверяем утраченные билеты
        lost_count = archive_missing_tickets()

        # 🧼 Завершаем волну
        set_wave_state("idle", prepared_at=None, wave_start=None)

        msg = "✅ Текущая волна завершена.\nТеперь вы можете запустить новую с помощью /new_wave."
        if lost_count > 0:
            msg += f"\n⚠️ Обнаружено и помечено как утраченных: {lost_count} билетов."

        bot.send_message(message.chat.id, msg)