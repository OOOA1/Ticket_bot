from .utils import admin_error_catcher, load_admins, awaiting_invite_count
from invite_admin import generate_invites, export_invites_xlsx

def register_invites_handlers(bot):
    @bot.message_handler(commands=['gen_invites'])
    @admin_error_catcher(bot)
    def ask_invite_count(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        bot.send_message(message.chat.id, "Сколько инвайт-кодов сгенерировать?")
        awaiting_invite_count[message.from_user.id] = True

    @bot.message_handler(func=lambda message: awaiting_invite_count.get(message.from_user.id))
    @admin_error_catcher(bot)
    def generate_and_send_invites(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return

        try:
            count = int(message.text)
            if not (1 <= count <= 5000):
                bot.send_message(message.chat.id, "Можно генерировать от 1 до 5000 кодов за раз.")
                return
        except Exception:
            bot.send_message(message.chat.id, "Введи число — сколько кодов нужно сгенерировать.")
            return

        awaiting_invite_count.pop(message.from_user.id, None)

        codes = generate_invites(count)
        temp_path = export_invites_xlsx(codes)

        with open(temp_path, "rb") as doc:
            bot.send_document(message.chat.id, doc, caption=f"Готово! {count} инвайтов сгенерировано.")
        # Не забываем удалить временный файл
        import os
        os.remove(temp_path)
