from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from .utils import load_admins
import time
from database import get_all_user_ids
import logging

logger = logging.getLogger(__name__)

def menu_error_catcher(func):
    def wrapper(message, *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        except Exception as e:
            if "message to be replied not found" in str(e):
                logger.warning(f"[MENU] Ошибка reply_to: {e}")
                bot.send_message(message.chat.id, "⚠️ Не удалось отправить ответ. Просто нажмите на кнопку ещё раз.")
            else:
                logger.error(f"Ошибка в хендлере меню {func.__name__}: {e}", exc_info=True)
                bot.send_message(message.chat.id, "Произошла ошибка. Повторите действие.")
    return wrapper

def register_admin_menu(bot):
    awaiting_args = {}  # user_id: {'cmd': ..., 'step': ...}

    def emulate_command(bot, call, command_text):
        msg_dict = {
            "message_id": call.message.message_id + 1234567,
            "from": {
                "id": call.from_user.id,
                "is_bot": False,
                "first_name": getattr(call.from_user, "first_name", ""),
                "username": getattr(call.from_user, "username", ""),
            },
            "date": call.message.date,
            "chat": {
                "id": call.from_user.id,  # <-- всегда user_id!
                "type": "private",
                "first_name": getattr(call.from_user, "first_name", ""),
                "username": getattr(call.from_user, "username", "")
            },
            "text": command_text
        }
        msg = Message.de_json(msg_dict)
        bot.process_new_messages([msg])
        bot.answer_callback_query(call.id)

    @bot.message_handler(commands=['menu'])
    @menu_error_catcher
    def admin_menu_handler(message):
        logger.info(f"[MENU] Админ {message.from_user.id} открыл меню.")
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.send_message(message.chat.id, "Нет прав для доступа к меню.")
            return

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔑 Админ-команды", callback_data="menu_admin_cmds"),
            InlineKeyboardButton("👥 Пользователи", callback_data="menu_users"),
            InlineKeyboardButton("💬 Логи", callback_data="menu_logs"),
            InlineKeyboardButton("📢 Рассылки", callback_data="menu_broadcast"),
            InlineKeyboardButton("📊 Отчёты", callback_data="menu_reports"),
            InlineKeyboardButton("ℹ️ В случае проблем", callback_data="menu_problems")
        )
        bot.send_message(message.chat.id, "Выберите раздел:", reply_markup=markup)

    def send_main_menu(chat_id):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔑 Админ-команды", callback_data="menu_admin_cmds"),
            InlineKeyboardButton("👥 Пользователи", callback_data="menu_users"),
            InlineKeyboardButton("💬 Логи", callback_data="menu_logs"),
            InlineKeyboardButton("📢 Рассылки", callback_data="menu_broadcast"),
            InlineKeyboardButton("📊 Отчёты", callback_data="menu_reports"),
            InlineKeyboardButton("ℹ️ В случае проблем", callback_data="menu_problems")
        )
        bot.send_message(chat_id, "Выберите раздел:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    @menu_error_catcher
    def back_to_main_handler(call):
        logger.info(f"[MENU] Админ {call.from_user.id} — возврат в главное меню.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        try:
            bot.edit_message_text("Главное меню:", call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception as e:
            logger.warning(f"[MENU] Не удалось изменить сообщение при возврате: {e}")
        send_main_menu(call.message.chat.id)

    # ==== Хендлеры для разделов ====

    @bot.callback_query_handler(func=lambda call: call.data == "menu_admin_cmds")
    @menu_error_catcher
    def menu_admin_cmds(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'Админ-команды'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Новая волна", callback_data="cmd_new_wave"),
            InlineKeyboardButton("Загрузить билеты (ZIP)", callback_data="cmd_upload_zip"),
            InlineKeyboardButton("Дозагрузить билеты (ZIP)", callback_data="cmd_upload_zip_add"),
            InlineKeyboardButton("Подтвердить волну", callback_data="cmd_confirm_wave"),
            InlineKeyboardButton("Массовая рассылка билетов", callback_data="cmd_send_tickets"),
            InlineKeyboardButton("Завершить волну", callback_data="cmd_end_wave"),
            InlineKeyboardButton("Статистика по волне", callback_data="cmd_stats"),
            InlineKeyboardButton("Список билетов", callback_data="cmd_list_tickets"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("🔑 Админ-команды по работе с волнами и билетами:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_users")
    @menu_error_catcher
    def menu_users(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'Пользователи'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Сгенерировать инвайты", callback_data="cmd_gen_invites"),
            InlineKeyboardButton("Экспорт пользователей", callback_data="cmd_export_users"),
            InlineKeyboardButton("Добавить админа", callback_data="cmd_add_admin"),
            InlineKeyboardButton("Удалить админа", callback_data="cmd_remove_admin"),
            InlineKeyboardButton("Удалить пользователя", callback_data="cmd_delete_user"),
            InlineKeyboardButton("Узнать свой user_id", callback_data="cmd_myid"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("👥 Управление пользователями и доступами:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_logs")
    @menu_error_catcher
    def menu_logs(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'Логи'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Получить chatlog", callback_data="cmd_chatlog"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("💬 Логи и аудит переписки:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_broadcast")
    @menu_error_catcher
    def menu_broadcast(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'Рассылки'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Сделать рассылку", callback_data="cmd_broadcast"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("📢 Рассылки и уведомления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_reports")
    @menu_error_catcher
    def menu_reports(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'Отчёты'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Failed-отчёт по рассылке билетов", callback_data="cmd_failed_report"),
            InlineKeyboardButton("Экспорт пользователей", callback_data="cmd_export_users"),
            InlineKeyboardButton("Экспорт билетов", callback_data="cmd_list_tickets"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("📊 Отчёты:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_problems")
    @menu_error_catcher
    def menu_problems(call):
        logger.info(f"[MENU] {call.from_user.id} — раздел 'В случае проблем'.")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Форс-выдача билета", callback_data="cmd_force_give"),
            InlineKeyboardButton("Удалить все билеты", callback_data="cmd_delete_all"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
        )
        bot.edit_message_text("ℹ️ В случае проблем используйте:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    # ==== Универсальный callback для команд ====
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cmd_"))
    @menu_error_catcher
    def command_button_handler(call):
        logger.info(f"[MENU] {call.from_user.id} нажал {call.data}")
        ADMINS = load_admins()
        if call.from_user.id not in ADMINS:
            bot.answer_callback_query(call.id, "Нет прав.")
            return

        data = call.data
        user_id = call.from_user.id

        # Команды, которые требуют аргументов (ожидание ввода)
        arg_cmds = {
            "cmd_broadcast": "broadcast",
            "cmd_gen_invites": "gen_invites",
            "cmd_chatlog": "chatlog",
            "cmd_force_give": "force_give",
            "cmd_delete_user": "delete_user",
            "cmd_add_admin": "add_admin",
            "cmd_remove_admin": "remove_admin",
        }

        # Если команда требует аргумент
        if data in arg_cmds:
            awaiting_args[user_id] = arg_cmds[data]
            prompts = {
                "broadcast": "Введите текст для рассылки или прикрепите медиа с подписью:",
                "gen_invites": "Сколько инвайт-кодов сгенерировать?",
                "chatlog": "Введите user_id или @username для получения chatlog:",
                "force_give": "Введите user_id или @username для ручной выдачи билета:",
                "delete_user": "Введите: user_id и @username через пробел (например, 123456 @user):",
                "add_admin": "Введите @username нового администратора:",
                "remove_admin": "Введите @username администратора для удаления:",
            }
            logger.info(f"[MENU] {call.from_user.id} — ожидание аргументов для команды {arg_cmds[data]}")
            bot.send_message(call.message.chat.id, prompts[arg_cmds[data]])
            bot.answer_callback_query(call.id)
            return

        # Обычные команды (без аргументов)
        commands_map = {
            "cmd_new_wave": "/new_wave",
            "cmd_upload_zip": "/upload_zip",
            "cmd_upload_zip_add": "/upload_zip_add",
            "cmd_confirm_wave": "/confirm_wave",
            "cmd_send_tickets": "/send_tickets",
            "cmd_end_wave": "/end_wave",
            "cmd_stats": "/stats",
            "cmd_list_tickets": "/list_tickets",

            "cmd_export_users": "/export_users",
            "cmd_failed_report": "/failed_report",
            "cmd_delete_all": "/delete_all",
        }
        if data in commands_map:
            logger.info(f"[MENU] {call.from_user.id} — эмуляция команды {commands_map[data]}")
            emulate_command(bot, call, commands_map[data])
        else:
            logger.info(f"[MENU] {call.from_user.id} нажал неизвестную команду {data}")
            bot.answer_callback_query(call.id, "Функция скоро будет реализована.")

    # === Handler для ожидания ввода аргументов ===
    def get_log_value(message):
        if message.content_type == 'document':
            return f"[DOCUMENT] {getattr(message.document, 'file_name', '')}"
        elif message.content_type == 'photo':
            return "[PHOTO]"
        elif message.content_type == 'animation':
            return "[ANIMATION]"
        elif message.content_type == 'video':
            return "[VIDEO]"
        elif message.content_type == 'audio':
            return "[AUDIO]"
        else:
            return getattr(message, 'text', '') or getattr(message, 'caption', '')


    @bot.message_handler(
        func=lambda m: m.from_user.id in awaiting_args,
        content_types=['text', 'photo', 'animation', 'document', 'video', 'audio']
    )
    @menu_error_catcher        
    def handle_argument_input(message):
        user_id = message.from_user.id
        cmd = awaiting_args.get(user_id)
        if not cmd:
            return
        del awaiting_args[user_id]
        logger.info(f"[MENU] {user_id} отправил аргумент для команды {cmd}: {get_log_value(message)}")

        if cmd == "broadcast":
            send_file_to_all(bot, message)
            return

        # остальные команды — как раньше
        elif cmd == "chatlog":
            msg = message
            msg.text = f"/chatlog {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        elif cmd == "gen_invites":
            msg = message
            msg.text = f"/gen_invites {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        elif cmd == "force_give":
            msg = message
            msg.text = f"/force_give {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        elif cmd == "delete_user":
            msg = message
            msg.text = f"/delete_user {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        elif cmd == "add_admin":
            msg = message
            msg.text = f"/add_admin {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        elif cmd == "remove_admin":
            msg = message
            msg.text = f"/remove_admin {message.text.strip()}"
            bot.process_new_messages([msg])
            return

        else:
            msg = message
            bot.process_new_messages([msg])
            return

def send_file_to_all(bot, message):
    user_ids = get_all_user_ids()
    success, fail = 0, 0
    failed_ids = []
    sent_ids = []
    caption = (getattr(message, 'caption', '') or '').strip()

    if message.content_type == 'photo':
        media_id = message.photo[-1].file_id
        for user_id in user_ids:
            try:
                bot.send_photo(user_id, media_id, caption=caption)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"📸 Фото-рассылка завершена!\n✅ {success} / ❌ {fail}")

    elif message.content_type == 'animation':
        media_id = message.animation.file_id
        for user_id in user_ids:
            try:
                bot.send_animation(user_id, media_id, caption=caption)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"🎞 GIF-рассылка завершена!\n✅ {success} / ❌ {fail}")

    elif message.content_type == 'document':
        media_id = message.document.file_id
        file_name = getattr(message.document, 'file_name', 'document')
        for user_id in user_ids:
            try:
                bot.send_document(user_id, media_id, caption=caption)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"📄 Рассылка файла завершена!\n✅ {success} / ❌ {fail}")

    elif message.content_type == 'video':
        media_id = message.video.file_id
        for user_id in user_ids:
            try:
                bot.send_video(user_id, media_id, caption=caption)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"🎬 Видео-рассылка завершена!\n✅ {success} / ❌ {fail}")

    elif message.content_type == 'audio':
        media_id = message.audio.file_id
        for user_id in user_ids:
            try:
                bot.send_audio(user_id, media_id, caption=caption)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"🎵 Аудио-рассылка завершена!\n✅ {success} / ❌ {fail}")

    elif message.content_type == 'text':
        text = message.text.strip()
        if text.startswith("/broadcast"):
            text = text[len("/broadcast"):].strip()
        if not text:
            bot.send_message(message.chat.id, "Используй так: /broadcast текст_сообщения или прикрепи медиа.")
            return
        for user_id in user_ids:
            try:
                bot.send_message(user_id, text)
                success += 1
                sent_ids.append(user_id)
            except Exception as e:
                fail += 1
                failed_ids.append(user_id)
            time.sleep(0.04)
        bot.send_message(message.chat.id, f"💬 Текстовая рассылка завершена!\n✅ {success} / ❌ {fail}")
    else:
        bot.send_message(message.chat.id, "Этот тип файлов пока не поддерживается!")


