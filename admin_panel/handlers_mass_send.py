import time
import os
from telebot import types
from database import (
    get_all_user_ids,
    get_user_last_ticket_time,
    get_latest_wave,
    get_free_ticket,
    assign_ticket,
    reserve_ticket_for_user,
    add_failed_delivery,
    remove_failed_delivery,
    get_admins,
    get_all_failed_deliveries,
    clear_failed_deliveries,
)
from .utils import load_admins, logger

MASS_SEND_TEXT = "Разослать билеты"
RETRY_SEND_TEXT = "Отправить оставшиеся билеты"

def register_mass_send_handler(bot):
    @bot.message_handler(commands=['send_tickets'])
    def handle_send_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав.")
            logger.warning(f"User {message.from_user.id} попытался разослать билеты без прав.")
            return

        # Берём всех пользователей и исключаем админов
        all_users = get_all_user_ids()
        admins    = set(get_admins())
        user_ids  = [uid for uid in all_users if uid not in admins]
        wave_start = get_latest_wave()
        if not wave_start:
            bot.reply_to(message, "Волна ещё не началась.")
            logger.warning("Попытка рассылки билетов без начатой волны.")
            return

        clear_failed_deliveries()

        sent_count = 0
        failed_count = 0
        already_count = 0
        start_time = time.time()
        failed_this_time = []

        failed_dict = dict(get_all_failed_deliveries())

        for idx, user_id in enumerate(user_ids, 1):
            last_ticket = get_user_last_ticket_time(user_id)
            if last_ticket and last_ticket >= wave_start:
                already_count += 1
                continue  # Уже получил билет

            # 1. Проверяем, был ли уже закреплён билет
            ticket_path = failed_dict.get(user_id)
            if not ticket_path:
                ticket_path = get_free_ticket()
                if not ticket_path:
                    bot.send_message(message.chat.id, f"Билеты закончились! Рассылка завершена.\n"
                                                    f"Успешно: {sent_count}, ошибок: {failed_count}, уже получали: {already_count}")
                    logger.info(f"Рассылка завершена: билеты закончились. Успешно: {sent_count}, ошибок: {failed_count}, уже было: {already_count}")
                    break
                reserve_ticket_for_user(ticket_path, user_id)
                add_failed_delivery(user_id, ticket_path)

            if not os.path.isfile(ticket_path):
                failed_count += 1
                err_msg = f"Файл билета не найден: {ticket_path}. Пропускаем пользователя {user_id}."
                bot.send_message(message.chat.id, err_msg)
                logger.error(err_msg)
                failed_this_time.append(user_id)
                continue

            # 2. Пробуем отправить с 1 ретраем
            try:
                with open(ticket_path, 'rb') as pdf:
                    bot.send_document(user_id, pdf)
                assign_ticket(ticket_path, user_id)  # отмечаем время отправки
                remove_failed_delivery(user_id)      # удаляем из "ожидающих"
                sent_count += 1
                logger.info(f"Билет отправлен user_id={user_id} [{idx}/{len(user_ids)}]")
            except Exception as e:
                logger.warning(f"Первая попытка неудачна для user_id={user_id}, пробую еще раз...")
                time.sleep(5)
                try:
                    with open(ticket_path, 'rb') as pdf:
                        bot.send_document(user_id, pdf)
                    assign_ticket(ticket_path, user_id)
                    remove_failed_delivery(user_id)
                    sent_count += 1
                    logger.info(f"Билет отправлен со второй попытки user_id={user_id} [{idx}/{len(user_ids)}]")
                except Exception as e2:
                    failed_count += 1
                    err_msg = f"Ошибка при повторной отправке для user_id={user_id}: {e2}"
                    bot.send_message(message.chat.id, err_msg)
                    logger.error(err_msg, exc_info=True)
                    failed_this_time.append(user_id)
                    continue

            time.sleep(5)

        total_time = int(time.time() - start_time)
        pending_after = get_all_failed_deliveries()
        pending_count = len(pending_after)
        result_msg = (
            f"✅ Рассылка завершена!\n"
            f"Всего пользователей: {len(user_ids)}\n"
            f"Отправлено билетов: {sent_count}\n"
            f"Ошибок: {failed_count}\n"
            f"Пропущено (уже получали): {already_count}\n"
            f"Ожидают доставки: {pending_count}\n"
            f"Время: {total_time} сек."
        )
        bot.send_message(message.chat.id, result_msg)
        logger.info(result_msg)

        # Если остались те, кому не дошло — сообщить админу
        if pending_count > 0:
            bot.send_message(
                message.chat.id,
                "⚠️ Есть пользователи, которым не удалось доставить билет. Используйте /retry_send_tickets чтобы попробовать ещё раз."
            )

    @bot.message_handler(commands=['retry_send_tickets'])
    def handle_retry_send_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав.")
            logger.warning(f"User {message.from_user.id} попытался дослать билеты без прав.")
            return

        failed_deliveries = get_all_failed_deliveries()
        if not failed_deliveries:
            bot.send_message(message.chat.id, "Нет пользователей, ожидающих получения билета.")
            return

        sent_count = 0
        failed_count = 0
        start_time = time.time()

        for user_id, ticket_path in failed_deliveries:
            if not os.path.isfile(ticket_path):
                failed_count += 1
                err_msg = f"Файл билета не найден: {ticket_path}. Пропускаем пользователя {user_id}."
                bot.send_message(message.chat.id, err_msg)
                logger.error(err_msg)
                continue

            try:
                with open(ticket_path, 'rb') as pdf:
                    bot.send_document(user_id, pdf)
                assign_ticket(ticket_path, user_id)
                remove_failed_delivery(user_id)
                sent_count += 1
                logger.info(f"[RETRY] Билет отправлен user_id={user_id}")
            except Exception as e:
                failed_count += 1
                err_msg = f"[RETRY] Ошибка при отправке для user_id={user_id}: {e}"
                bot.send_message(message.chat.id, err_msg)
                logger.error(err_msg, exc_info=True)
                continue

            time.sleep(5)

        total_time = int(time.time() - start_time)
        pending_after = get_all_failed_deliveries()
        pending_count = len(pending_after)
        result_msg = (
            f"♻️ Повторная рассылка завершена!\n"
            f"Отправлено билетов: {sent_count}\n"
            f"Ошибок: {failed_count}\n"
            f"Ожидают доставки: {pending_count}\n"
            f"Время: {total_time} сек."
        )
        bot.send_message(message.chat.id, result_msg)
        logger.info(result_msg)
        if pending_count > 0:
            bot.send_message(
                message.chat.id,
                "⚠️ Некоторые пользователи всё ещё не получили билеты. Можно повторить /retry_send_tickets позже."
            )
