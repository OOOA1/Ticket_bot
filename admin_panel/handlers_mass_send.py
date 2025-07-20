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
)
from .utils import load_admins, logger
from datetime import datetime
import time
import os

def register_mass_send_handler(bot):
    @bot.message_handler(commands=['send_tickets'])
    def handle_send_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ Нет прав.")
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
                reserve_ticket_for_user(ticket_path, user_id)
                add_failed_delivery(user_id, ticket_path)

            if not os.path.isfile(ticket_path):
                failed_count += 1
                err_msg = f"❌ Файл билета не найден: {ticket_path}. Пропускаем {user_id}."
                bot.send_message(message.chat.id, err_msg)
                logger.error(err_msg)
                failed_this_time.append(user_id)
                continue

            # 4. Пытаемся отправить (с ретраем)
            try:
                with open(ticket_path, 'rb') as pdf:
                    bot.send_document(user_id, pdf)
                assign_ticket(ticket_path, user_id)
                remove_failed_delivery(user_id)
                sent_count += 1
                logger.info(f"✅ Билет отправлен user_id={user_id} [{idx}/{len(user_ids)}]")
            except Exception as e:
                logger.warning(f"Первая попытка неудачна для user_id={user_id}")
                time.sleep(5)
                try:
                    with open(ticket_path, 'rb') as pdf:
                        bot.send_document(user_id, pdf)
                    assign_ticket(ticket_path, user_id)
                    remove_failed_delivery(user_id)
                    sent_count += 1
                    logger.info(f"✅ Повторно отправлен user_id={user_id} [{idx}/{len(user_ids)}]")
                except Exception as e2:
                    failed_count += 1
                    err_msg = f"❌ Ошибка при повторной отправке user_id={user_id}: {e2}"
                    bot.send_message(message.chat.id, err_msg)
                    logger.error(err_msg, exc_info=True)
                    failed_this_time.append(user_id)
                    continue

            time.sleep(5)

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

        # --- Автоматическая повторная рассылка ---
        if pending_count > 0:
            bot.send_message(message.chat.id, "♻️ Пробую автоматически отправить недоставленные билеты...")
            retry_sent = 0
            retry_failed = 0
            start_time_retry = time.time()
            for user_id, ticket_path in get_all_failed_deliveries():
                if not os.path.isfile(ticket_path):
                    retry_failed += 1
                    err_msg = f"Файл билета не найден: {ticket_path}. Пропускаем пользователя {user_id}."
                    bot.send_message(message.chat.id, err_msg)
                    logger.error(err_msg)
                    continue

                try:
                    with open(ticket_path, 'rb') as pdf:
                        bot.send_document(user_id, pdf)
                    assign_ticket(ticket_path, user_id)
                    remove_failed_delivery(user_id)
                    retry_sent += 1
                    logger.info(f"[AUTO-RETRY] Билет отправлен user_id={user_id}")
                except Exception as e:
                    retry_failed += 1
                    err_msg = f"[AUTO-RETRY] Ошибка при отправке для user_id={user_id}: {e}"
                    bot.send_message(message.chat.id, err_msg)
                    logger.error(err_msg, exc_info=True)
                    continue

                time.sleep(5)

            total_time_retry = int(time.time() - start_time_retry)
            pending_after_retry = get_all_failed_deliveries()
            bot.send_message(
                message.chat.id,
                f"♻️ Автоматическая повторная рассылка завершена!\n"
                f"Дополнительно отправлено: {retry_sent}\n"
                f"Ошибок при повторе: {retry_failed}\n"
                f"Ожидают доставки после автоповтора: {len(pending_after_retry)}\n"
                f"Время автоповтора: {total_time_retry} сек."
            )
            logger.info(
                f"Автоматическая повторная рассылка завершена: отправлено={retry_sent}, ошибок={retry_failed}, осталось={len(pending_after_retry)}"
            )
