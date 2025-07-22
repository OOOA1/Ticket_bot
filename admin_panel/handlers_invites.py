import os
from admin_panel.invite_admin import export_users_xlsx
from .utils import admin_error_catcher, awaiting_invite_count, admin_required, logger
from database import get_admins, is_admin, delete_user_everywhere
from admin_panel.invite_admin import generate_invites, export_invites_xlsx

# Временное состояние для подтверждения удаления
awaiting_delete_confirm = {}  # {admin_id: (user_id, username)}

def register_invites_handlers(bot):
    @bot.message_handler(commands=['gen_invites'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def ask_invite_count(message):
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            return
        bot.send_message(message.chat.id, "Сколько инвайт-кодов сгенерировать?")
        awaiting_invite_count[message.from_user.id] = True

    @bot.message_handler(func=lambda m: awaiting_invite_count.get(m.from_user.id))
    @admin_required(bot)
    @admin_error_catcher(bot)
    def generate_and_send_invites(message):
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            return

        try:
            count = int(message.text)
            if not (1 <= count <= 5000):
                bot.send_message(message.chat.id, "Можно генерировать от 1 до 5000 кодов за раз.")
                return
        except ValueError:
            bot.send_message(message.chat.id, "Введи число — сколько кодов нужно сгенерировать.")
            return

        awaiting_invite_count.pop(message.from_user.id, None)

        codes = generate_invites(count)
        temp_path = export_invites_xlsx(codes)

        # Отправляем файл инициатору
        with open(temp_path, "rb") as doc:
            bot.send_document(message.chat.id, doc, caption=f"Готово! {count} инвайтов сгенерировано.")
        os.remove(temp_path)

        # Уведомляем остальных админов
        for admin_id in ADMINS:
            if admin_id != message.from_user.id:
                bot.send_message(
                    admin_id,
                    f"🔑 @{message.from_user.username} сгенерировал {count} новых invite-кодов."
                )

    @bot.message_handler(commands=['export_users'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def export_users_handler(message):
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав.")
            return

        path, user_count, admin_count = export_users_xlsx()
        with open(path, "rb") as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption=f"Пользователей: {user_count}\nАдминов: {admin_count}"
            )
        os.remove(path)

    @bot.message_handler(commands=['delete_user'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_delete_user(message):
        args = message.text.split()
        admin_id = message.from_user.id

        # Валидация: должно быть ровно два аргумента — user_id (цифры) и @username
        if len(args) != 3 or not args[1].isdigit() or not args[2].startswith("@"):
            bot.reply_to(
                message,
                "Используйте: /delete_user user_id @username (user_id — только цифры, @username — с @)"
            )
            return

        user_id_str = args[1]
        username = args[2]

        if not user_id_str.isdigit():
            bot.reply_to(message, "user_id должен быть числом. Пример: /delete_user 123456789 @username")
            return

        user_id = int(user_id_str)

        if is_admin(user_id):
            bot.reply_to(message, "❗️ Нельзя удалить администратора.")
            return

        awaiting_delete_confirm[admin_id] = (user_id, username)
        bot.send_message(
            message.chat.id,
            f"Вы точно хотите удалить пользователя {username}? Ответьте 'Да' или 'Нет'."
        )

    @bot.message_handler(func=lambda m: m.text and m.text.strip().lower() in ["да", "нет"])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_delete_confirm(message):
        admin_id = message.from_user.id

        if admin_id not in awaiting_delete_confirm:
            return  # Нет ожидающего подтверждения

        user_id, username = awaiting_delete_confirm[admin_id]
        answer = message.text.strip().lower()

        if answer == "нет":
            bot.send_message(message.chat.id, "Операция отменена.")
            del awaiting_delete_confirm[admin_id]
            return

        if answer == "да":
            success = delete_user_everywhere(user_id, username)
            if success:
                bot.send_message(message.chat.id, f"✅ Пользователь {username} успешно удалён из всех таблиц.")
                logger.info(f"Админ {admin_id} удалил пользователя {user_id} ({username}) через /delete_user")
            else:
                bot.send_message(message.chat.id, f"❗️ Пользователь {username} не найден или уже удалён.")
            del awaiting_delete_confirm[admin_id]
            return
