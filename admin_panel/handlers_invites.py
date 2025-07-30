import os
from admin_panel.invite_admin import export_users_xlsx
from .utils import admin_error_catcher, admin_required, logger
from database import get_admins, is_admin, delete_user_everywhere
from admin_panel.invite_admin import generate_invites, export_invites_xlsx
import logging
logger = logging.getLogger(__name__)

# Временное состояние для подтверждения удаления
awaiting_delete_confirm = {}  # {admin_id: (user_id, username)}

def register_invites_handlers(bot):
    @bot.message_handler(commands=['gen_invites'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_gen_invites(message):
        logger.info("Команда /gen_invites вызвана пользователем %d", message.from_user.id)
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            return

        args = message.text.strip().split()
        if len(args) == 2 and args[1].isdigit():
            count = int(args[1])
            if not (1 <= count <= 5000):
                bot.send_message(message.chat.id, "Можно создать от 1 до 5000 приглашений за раз.")
                return

            codes = generate_invites(count)
            temp_path = export_invites_xlsx(codes)

            with open(temp_path, "rb") as doc:
                bot.send_document(message.chat.id, doc, caption=f"Готово! {count} создано приглашений.")
            os.remove(temp_path)

            logger.info(f"Пользователь {message.from_user.id} сгенерировал {count} инвайт-кодов, файл: {temp_path}")

            for admin_id in ADMINS:
                try:
                    admin_id = int(admin_id)
                    if admin_id == message.from_user.id:
                        continue
                    if admin_id <= 0:
                        continue
                    bot.send_message(
                        admin_id,
                        f"🔑 @{message.from_user.username} создал {count} новых приглашений."
                    )
                except Exception as e:
                    print(f"❌ Ошибка отправки админу {admin_id}: {e}")

        else:
            bot.send_message(
                message.chat.id,
                "Используйте: /gen_invites <количество> (от 1 до 5000)\n\n"
                "Пример: /gen_invites 10"
            )



    @bot.message_handler(commands=['export_users'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def export_users_handler(message):
        logger.info("Команда /export_users вызвана пользователем %d", message.from_user.id)
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return

        # Генерируем файл и получаем число пользователей и админов
        path, user_count, admin_count = export_users_xlsx()
        logger.info("Экспорт пользователей: всего=%d, админов=%d, файл=%s", user_count, admin_count, path)

        # Если нет пользователей — сразу информируем и выходим
        if user_count == 0:
            bot.send_message(
                message.chat.id,
                "⚠️ Нет зарегистрированных пользователей — нечего экспортировать."
            )
            # Удаляем файл, если он был создан
            try:
                os.remove(path)
            except OSError:
                pass
            return

        # Иначе отправляем документ с данными
        with open(path, "rb") as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption=f"👥 Пользователей: {user_count}\n🔑 Админов: {admin_count}"
            )

        # Чистим временный файл
        try:
            os.remove(path)
        except OSError:
            pass

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
