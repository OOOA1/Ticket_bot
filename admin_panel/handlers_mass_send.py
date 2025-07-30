import time
import os
import re
import random
import sqlite3
import tempfile
import xlsxwriter

from database import (
    get_all_user_ids,
    get_user_last_ticket_time,
    get_free_ticket,
    assign_ticket,
    reserve_ticket_for_user,
    add_failed_delivery,
    remove_failed_delivery,
    get_admins,
    get_all_failed_deliveries,
    clear_failed_deliveries,
    get_wave_state,
    get_current_wave_id,
    mark_ticket_lost,
    release_ticket,
    clear_user_assignments,
    resolve_user_id,
)
from .utils import load_admins, logger, admin_required, admin_error_catcher, log_chat
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# === Telegram 429 обработка ===
def try_send_with_telegram_limit(send_func, *args, **kwargs):
    """
    Пытается отправить сообщение/документ, обрабатывает лимит 429 Too Many Requests.
    send_func — функция отправки (например, bot.send_document)
    *args, **kwargs — её параметры
    """
    for attempt in range(2):  # максимум 2 попытки (основная + одна после ожидания)
        try:
            return send_func(*args, **kwargs)
        except Exception as e:
            err = str(e)
            # Ищем retry after в ошибке (TelegramAPIError: Too Many Requests: retry after 27)
            if "retry after" in err:
                try:
                    retry_after = int(re.search(r'retry after (\d+)', err).group(1))
                    time.sleep(retry_after + 1)
                except Exception:
                    time.sleep(5)
            else:
                if attempt == 0:
                    time.sleep(5)  # стандартная пауза если это не лимит
                else:
                    raise  # на второй раз просто пробрасываем ошибку дальше

def register_mass_send_handler(bot):
    @bot.message_handler(commands=['send_tickets'])
    def handle_send_tickets(message):
        logger.info("Команда /send_tickets вызвана пользователем %d", message.from_user.id)
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return

        # 1. Проверяем статус волны
        state = get_wave_state()
        if state["status"] != "active":
            bot.reply_to(message, "⚠️ Волна ещё не активирована. Сначала выполните /confirm_wave.")
            return

        wave_start = datetime.fromisoformat(state["wave_start"])
        wave_id = get_current_wave_id()
        if not wave_id:
            bot.reply_to(message, "❗️ Текущая волна не найдена.")
            return

        # 2. Подготовка списка пользователей
        all_users = get_all_user_ids()
        admins = set(get_admins())
        user_ids = [uid for uid in all_users if uid not in admins]

        clear_failed_deliveries()
        failed_dict = dict(get_all_failed_deliveries())

        sent_count = 0
        failed_count = 0
        already_count = 0
        start_time = time.time()
        failed_this_time = []
        logger.info("Начало рассылки: волна %d, всего пользователей %d", wave_id, len(user_ids))

        for idx, user_id in enumerate(user_ids, 1):
            last_ticket = get_user_last_ticket_time(user_id)
            if last_ticket and last_ticket >= wave_start:
                already_count += 1
                continue 

            # 3. Получаем зарезервированный билет или берём новый из текущей волны
            ticket_path = failed_dict.get(user_id)
            if not ticket_path:
                ticket_path = get_free_ticket(wave_id)
                if not ticket_path:
                    bot.send_message(
                        message.chat.id,
                        f"🎟 Билеты закончились! Рассылка завершена.\n"
                        f"Успешно: {sent_count}, ошибок: {failed_count}, уже получали: {already_count}"
                    )
                    logger.info("Рассылка завершена: билеты закончились.")
                    break
                clear_user_assignments(user_id, current_wave_id=wave_id)
                reserve_ticket_for_user(ticket_path, user_id)
                add_failed_delivery(user_id, ticket_path)

            if not os.path.isfile(ticket_path):
                # Шаг 1: файл не найден – регистрируем неудачную доставку и уведомляем админов
                        logger.error("Файл билета не найден: %s для user_id=%d", ticket_path, user_id)
                        add_failed_delivery(user_id, ticket_path)
                        for admin_id in get_admins():
                            try:
                                bot.send_message(
                                    admin_id,
                                    f"❌ Файл билета для user_id={user_id} не найден: {ticket_path}.\n"
                                    "Пользователь добавлен в failed_deliveries."
                                )
                            except:
                                pass
                        bot.send_message(
                            message.chat.id,
                            "Извините, билет не найден. Администраторы уведомлены."
                        )
                        failed_count += 1
                        logger.error(f"❌ Файл билета не найден: {ticket_path} для user_id={user_id}")
                        failed_this_time.append(user_id)
                        continue

            # 4. Отправка с 3 попытками и экспоненциальным бэкоффом
            max_retries = 3
            delay = 5
            for attempt in range(1, max_retries + 1):
                try:
                    with open(ticket_path, 'rb') as pdf:
                        try_send_with_telegram_limit(bot.send_document, user_id, pdf)
                    assign_ticket(ticket_path, user_id)
                    remove_failed_delivery(user_id)
                    log_chat(user_id, "BOT", f"[DOCUMENT] {os.path.basename(ticket_path)}")
                    sent_count += 1

                    if sent_count == 1 or sent_count % 20 == 0:
                        bot.send_message(
                            message.chat.id,
                            f"Рассылка: успешно отправлено {sent_count} из {len(user_ids)} билетов."
                        )
                    logger.info(f"✅ Билет отправлен user_id={user_id} [{idx}/{len(user_ids)}], попытка {attempt}")
                    time.sleep(random.uniform(3.5, 5.0))
                    break
                except Exception as e:
                    err = str(e).lower()
                    # 1) если заблокирован бот или 403 — не повторяем
                    if "403" in err or "bot was blocked" in err:
                        add_failed_delivery(user_id, ticket_path)
                        # пользователь заблокировал бота — возвращаем билет в пул
                        release_ticket(ticket_path)
                        bot.send_message(
                            message.chat.id,
                            f"❌ user_id={user_id} заблокировал бота. Билет возвращён в пул."
                        )
                        logger.error(f"Бот заблокирован user_id={user_id}: {e}")
                        failed_count += 1
                        failed_this_time.append(user_id)
                        break
                    
                    # 2) проверяем retry-after для 429
                    m = re.search(r'retry after (\d+)', err)
                    wait = (int(m.group(1)) + 1) if m else delay
                    # 3) если ещё есть попытки — ждём и удваиваем delay
                    if attempt < max_retries:
                        logger.warning(f"Попытка {attempt} не удалась для user_id={user_id}: {e}. Ждём {wait} сек.")
                        time.sleep(wait)
                        delay *= 2
                        continue
                    
                    # 4) все попытки исчерпаны — решаем по наличию файла
                    if not os.path.isfile(ticket_path):
                        add_failed_delivery(user_id, ticket_path)
                        mark_ticket_lost(ticket_path)
                        bot.send_message(
                            message.chat.id,
                            f"❌ Файл не найден: {ticket_path}. Билет помечен LOST."
                        )
                    else:
                        add_failed_delivery(user_id, ticket_path)
                        release_ticket(ticket_path)
                        bot.send_message(
                            message.chat.id,
                            f"❌ Не удалось доставить ticket для user_id={user_id} после {max_retries} попыток. Билет возвращён в пул."
                        )
                    
            # после цикла, если не break, loop пойдет дальше

        total_time = int(time.time() - start_time)
        pending_after = get_all_failed_deliveries()
        pending_count = len(pending_after)

        result_msg = (
            f"📦 Рассылка завершена!\n"
            f"Всего пользователей: {len(user_ids)}\n"
            f"✅ Отправлено: {sent_count}\n"
            f"❌ Ошибок: {failed_count}\n"
            f"⏭ Пропущено (уже получали): {already_count}\n"
            f"🕓 Время: {total_time} сек.\n"
            f"📭 Ожидают доставки: {pending_count}"
        )
        bot.send_message(message.chat.id, result_msg)
        logger.info(result_msg)

        # Автоматическая повторная рассылка с 3 попытками и экспоненциальным бэкоффом
        if pending_count > 0:
            bot.send_message(message.chat.id, "♻️ Авторассылка недоставленных билетов...")
            retry_sent = retry_failed = 0
            start_time_retry = time.time()

            for user_id, ticket_path in get_all_failed_deliveries():
                # Если файл полностью отсутствует — помечаем как LOST и пропускаем
                if not os.path.isfile(ticket_path):
                    release_ticket(ticket_path)
                    mark_ticket_lost(ticket_path)
                    add_failed_delivery(user_id, ticket_path)
                    bot.send_message(message.chat.id,
                        f"❌ Файл не найден: {ticket_path}. Билет помечен LOST для user_id={user_id}."
                    )
                    logger.error(f"[AUTO-RETRY] Файл не найден: {ticket_path} для user_id={user_id}")
                    retry_failed += 1
                    continue

                # Пытаемся отправить до 3 раз
                max_retries = 3
                delay = 5
                sent = False
                for attempt in range(1, max_retries + 1):
                    try:
                        with open(ticket_path, 'rb') as pdf:
                            try_send_with_telegram_limit(bot.send_document, user_id, pdf)
                        assign_ticket(ticket_path, user_id)
                        remove_failed_delivery(user_id)
                        log_chat(user_id, "BOT", f"[DOCUMENT] {os.path.basename(ticket_path)}")
                        retry_sent += 1
                        logger.info(f"[AUTO-RETRY] Успешно для user_id={user_id}, попытка {attempt}")
                        sent = True
                        break
                    except Exception as e:
                        err = str(e).lower()
                        # Критические ошибки — сразу помечаем LOST
                        
                        if any(k in err for k in ["403", "bot was blocked"]):
                            add_failed_delivery(user_id, ticket_path)
                            release_ticket(ticket_path)
                            bot.send_message(
                                message.chat.id,
                                f"❌ user_id={user_id} заблокировал бота. Билет возвращён в пул."
                            )
                            logger.error(f"[AUTO-RETRY] Критическая ошибка для {user_id}: {e}")
                            retry_failed += 1
                            sent = True
                            break
                        # Обработка 429 Retry-After
                        m = re.search(r"retry after (\d+)", err)
                        wait = (int(m.group(1)) + 1) if m else delay
                        if attempt < max_retries:
                            logger.warning(f"[AUTO-RETRY] Попытка {attempt} не удалась для {user_id}: {e}. Ждём {wait}s.")
                            time.sleep(wait)
                            delay *= 2
                            continue
                        # Все попытки исчерпаны
                        if not os.path.isfile(ticket_path):
                            release_ticket(ticket_path)
                            mark_ticket_lost(ticket_path)
                            add_failed_delivery(user_id, ticket_path)
                            bot.send_message(
                                message.chat.id,
                                f"❌ Файл не найден: {ticket_path}. Билет помечен LOST."
                            )
                        else:
                            add_failed_delivery(user_id, ticket_path)
                            release_ticket(ticket_path)
                            bot.send_message(
                                message.chat.id,
                                f"❌ Не удалось доставить ticket для user_id={user_id}. Билет возвращён в пул."
                            )
                    
                        logger.error(f"[AUTO-RETRY] Потерян билет {ticket_path} для {user_id}")
                        retry_failed += 1
                        # конец цикла попыток
                time.sleep(5)

            total_time_retry = int(time.time() - start_time_retry)
            pending_after_retry = get_all_failed_deliveries()
            bot.send_message(message.chat.id,
                f"♻️ Авторассылка завершена!\n"
                f"Доп. отправлено: {retry_sent}\n"
                f"Ошибок: {retry_failed}\n"
                f"Осталось: {len(pending_after_retry)}\n"
                f"Время: {total_time_retry}s"
            )
            logger.info(
                "Рассылка завершена: отправлено=%d, ошибок=%d, скипнуто=%d, общее время=%ds",
                sent_count, failed_count, already_count, int(time.time() - start_time)
            )

    @bot.message_handler(commands=['failed_report'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_failed_report(message):
        failed = dict(get_all_failed_deliveries())  # {user_id: ticket_path}

        if not failed:
            bot.send_message(message.chat.id, "✅ Нет пользователей с неудачной доставкой билетов.")
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            workbook = xlsxwriter.Workbook(tmp.name)
            worksheet = workbook.add_worksheet("Failed Deliveries")

            worksheet.write_row(0, 0, [
                "user_id", "username", "ticket_path", "original_name", "статус", "Не доставлено"
            ])

            for idx, (user_id, ticket_path) in enumerate(failed.items(), 1):
                cur.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
                row = cur.fetchone()
                username = f"@{row[0]}" if row and row[0] else ""

                cur.execute("""
                    SELECT original_name, lost, archived_unused, assigned_to
                    FROM tickets
                    WHERE file_path=?
                """, (ticket_path,))
                row = cur.fetchone()

                if row:
                    original_name, lost, archived, assigned = row
                    if lost:
                        status = "Утраченный"
                    elif archived:
                        status = "Архивный"
                    elif assigned:
                        status = "Выдан"
                    else:
                        status = "Активный"
                else:
                    original_name = "❓ не найден"
                    status = "❌ нет данных"

                worksheet.write_row(idx, 0, [
                    user_id,
                    username,
                    ticket_path,
                    original_name,
                    status,
                    "Да"  # раз запись есть в failed_deliveries — значит не доставлено
                ])

            worksheet.set_column(0, 0, 14)
            worksheet.set_column(1, 1, 20)
            worksheet.set_column(2, 2, 60)
            worksheet.set_column(3, 3, 30)
            worksheet.set_column(4, 4, 20)
            worksheet.set_column(5, 5, 18)

            workbook.close()

            doc = open(tmp.name, "rb")
            bot.send_document(message.chat.id, doc, caption="📄 Отчёт о неудачных доставках билетов")
            doc.close()

        os.remove(tmp.name)        

    @bot.message_handler(commands=['chatlog'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_chatlog(message):
        args = message.text.strip().split()
        if len(args) != 2:
            bot.reply_to(message, "Использование: /chatlog user_id или /chatlog @username")
            return

        user_ref = args[1]
        user_id = resolve_user_id(user_ref)
        if not user_id:
            bot.reply_to(message, "Пользователь не найден.")
            return

        log_path = os.path.join("logs", f"{user_id}.txt")
        if not os.path.isfile(log_path):
            bot.reply_to(message, "Для этого пользователя ещё нет переписки.")
            return

        with open(log_path, "rb") as f:
            bot.send_document(message.chat.id, f, caption=f"📄 Переписка с user_id {user_id}")