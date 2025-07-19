import os

from .utils import admin_error_catcher, awaiting_invite_count
from database import get_admins
from admin_panel.invite_admin import generate_invites, export_invites_xlsx

def register_invites_handlers(bot):
    @bot.message_handler(commands=['gen_invites'])
    @admin_error_catcher(bot)
    def ask_invite_count(message):
        ADMINS = get_admins()
        if message.from_user.id not in ADMINS:
            return
        bot.send_message(message.chat.id, "Сколько инвайт-кодов сгенерировать?")
        awaiting_invite_count[message.from_user.id] = True

    @bot.message_handler(func=lambda m: awaiting_invite_count.get(m.from_user.id))
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
