import sqlite3
import os
from datetime import datetime
from .utils import admin_error_catcher, load_admins, admin_required
from database import (
    create_new_wave,
    get_all_user_ids,
    archive_missing_tickets,
    clear_failed_deliveries,
    set_wave_state,
    get_wave_state,
    get_admins,
    get_current_wave_id,
    archive_all_old_free_tickets,
    DB_PATH,
)

def register_wave_handlers(bot):
    @bot.message_handler(commands=['new_wave'])
    @admin_required(bot)
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

        # Всё чисто — запускаем новую волну

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
        msg += "📥 Загрузите билеты /upload_zip и подтвердите волну через /confirm_wave."

        bot.send_message(message.chat.id, msg)


    @bot.message_handler(commands=['confirm_wave'])
    @admin_required(bot)
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

        if available_tickets < user_count or available_tickets == 0:
            msg = (
                f"❌ Подтверждение невозможно — недостаточно новых билетов.\n"
                f"👤 Пользователей: {user_count}\n"
                f"🎟 Новых билетов: {available_tickets}\n"
            )
            if lost_count > 0:
                msg += f"⚠️ Также обнаружено {lost_count} утраченных билетов.\n"
            msg += "Для загрузки билетов используйте /upload_zip_add"
            bot.send_message(message.chat.id, msg)
            conn.close()
            return

        wave_start, wave_id = create_new_wave(message.from_user.id)

        # Обновим wave_id для всех загруженных файлов, включая lost
        cur.execute("""
            UPDATE tickets
            SET assigned_at = NULL, wave_id = ?
            WHERE wave_id IS NULL AND uploaded_at > ?
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
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_end_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ У вас нет прав.")
            return

        state = get_wave_state()
        status = state["status"]
        if status == "idle":
            bot.send_message(message.chat.id, "⚠️ Сейчас нет активной или подготовленной волны.")
            return

        # Если волна НЕ была подтверждена — удаляем «сирот» и сбрасываем в одном шаге 
        if status == "awaiting_confirm":
            # 1) Собираем сиротские билеты
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT file_path FROM tickets
                WHERE wave_id IS NULL
                AND assigned_to IS NULL
                AND archived_unused = 0
                AND lost = 0
            """)
            orphans = [row[0] for row in cur.fetchall()]

            # 2) Удаляем их из БД
            if orphans:
                cur.execute("""
                    DELETE FROM tickets
                    WHERE wave_id IS NULL
                    AND assigned_to IS NULL
                    AND archived_unused = 0
                    AND lost = 0
                """)
                conn.commit()
            conn.close()

            # 3) Стираем файлы
            removed = 0
            for path in orphans:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass

            # 4) Архивируем пропавшие
            lost_count = archive_missing_tickets()

            # 5) Сброс состояния волны
            set_wave_state("idle", prepared_at=None, wave_start=None)

            # 6) Единственное финальное сообщение
            msg = (
                f"❌ Волна не была подтверждена — статистика не собрана.\n"
                f"Удалено «сиротских» билетов: {removed}.\n\n"
                "✅ Волна сброшена. Теперь можно запустить новую: /new_wave"
            )
            if lost_count > 0:
                msg += f"\n⚠️ Также помечено утраченных файлов: {lost_count}."
            bot.send_message(message.chat.id, msg)
            return

        # Если волна была подтверждена и активна 
        # 1) Архивируем пропавшие билеты
        lost_count = archive_missing_tickets()

        # 2) Сброс состояния
        set_wave_state("idle", prepared_at=None, wave_start=None)

        # 3) Сообщение об успешном завершении
        msg = "✅ Волна завершена и сброшена. Теперь можно: /new_wave"
        if lost_count > 0:
            msg += f"\n⚠️ Помечено утраченных файлов: {lost_count}."
        bot.send_message(message.chat.id, msg)

        # 4) Показать статистику по только что завершённой волне
        wave_id = get_current_wave_id()  # вероятно None сразу после сброса
        if not wave_id:
            bot.send_message(message.chat.id, "📊 Статистика недоступна: волна не запущена.")
            return

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Всего в этой волне
        cur.execute("SELECT COUNT(*) FROM tickets WHERE wave_id = ?", (wave_id,))
        total_tickets = cur.fetchone()[0]

        # Свободные
        cur.execute("""
            SELECT COUNT(*) FROM tickets
            WHERE wave_id = ? AND assigned_to IS NULL AND archived_unused = 0 AND lost = 0
        """, (wave_id,))
        free_tickets = cur.fetchone()[0]

        # Выданные
        cur.execute("""
            SELECT COUNT(*) FROM tickets
            WHERE wave_id = ? AND assigned_to IS NOT NULL AND lost = 0
        """, (wave_id,))
        issued_tickets = cur.fetchone()[0]

        # Утраченные
        cur.execute("SELECT COUNT(*) FROM tickets WHERE wave_id = ? AND lost = 1", (wave_id,))
        lost_tickets = cur.fetchone()[0]

        conn.close()

        # Пользователей (не админов)
        all_users = get_all_user_ids()
        admins_set = set(get_admins())
        user_count = len([u for u in all_users if u not in admins_set])

        stats_msg = (
            f"<b>📊 Статистика прошлой волны (ID {wave_id}):</b>\n\n"
            f"👥 Пользователей: <b>{user_count}</b>\n"
            f"🎟 Всего билетов: <b>{total_tickets}</b>\n"
            f"📬 Выдано: <b>{issued_tickets}</b>\n"
            f"📦 Свободных: <b>{free_tickets}</b>\n"
            f"❌ Утраченных: <b>{lost_tickets}</b>\n"
        )
        bot.send_message(message.chat.id, stats_msg, parse_mode="HTML")

   
    @bot.message_handler(commands=['stats'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_stats(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ У вас нет прав.")
            return

        # 1. Актуализация: проверка файлов на утрату
        lost_count = archive_missing_tickets()

        # 2. Получаем статус волны и ID
        state = get_wave_state()
        wave_status = state["status"]
        wave_id = get_current_wave_id()

        # 3. Получаем список пользователей (без админов)
        all_users = get_all_user_ids()
        admins = set(get_admins())
        user_count = len([uid for uid in all_users if uid not in admins])

        # 4. Подсчёт билетов в зависимости от стадии волны
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        if wave_status == "active":
            cur.execute("SELECT COUNT(*) FROM tickets WHERE wave_id=?", (wave_id,))
            total_tickets = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE wave_id=? AND assigned_to IS NULL AND archived_unused=0 AND lost=0
            """, (wave_id,))
            free_tickets = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE wave_id=? AND assigned_to IS NOT NULL AND lost=0
            """, (wave_id,))
            issued_tickets = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM tickets WHERE wave_id=? AND lost=1", (wave_id,))
            lost_tickets = cur.fetchone()[0]
        else:
            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE wave_id IS NULL AND assigned_to IS NULL AND archived_unused=0 AND lost=0
            """)
            total_tickets = cur.fetchone()[0]
            free_tickets = total_tickets
            issued_tickets = 0

            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE wave_id IS NULL AND lost=1
            """)
            lost_tickets = cur.fetchone()[0]

        conn.close()

        # 5. Формируем отчёт
        msg = (
            f"<b>📊 Актуальная статистика волны:</b>\n\n"
            f"🔄 Статус волны: <code>{wave_status}</code>\n"
            f"👥 Пользователей (без админов): <b>{user_count}</b>\n"
            f"🎟 Всего билетов: <b>{total_tickets}</b>\n"
            f"📬 Выдано: <b>{issued_tickets}</b>\n"
            f"📦 Свободных: <b>{free_tickets}</b>\n"
            f"❌ Утраченных: <b>{lost_tickets}</b>\n"
        )
        if lost_count > 0:
            msg += f"\n⚠️ Дополнительно обнаружено и помечено как утраченных: <b>{lost_count}</b> билетов."

        bot.send_message(message.chat.id, msg, parse_mode="HTML")
