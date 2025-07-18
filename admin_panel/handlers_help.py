from .utils import admin_error_catcher, load_admins

def register_help_handlers(bot):
    @bot.message_handler(commands=['help'])
    @admin_error_catcher(bot)
    def handle_help(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        text = (
            "<b>🔑 Доступные админ-команды:</b>\n\n"
            "/start — запустить (или перезапустить) бота\n"
            "/new_wave — начать новую волну\n"
            "/stats — статистика по билетам и пользователям\n"
            "/force_give @username — выдать билет вручную пользователю\n"
            "/add_admin @username — добавить нового админа\n"
            "/remove_admin @username — удалить админа\n"
            "/list_tickets — получить список всех билетов\n"
            "/delete_all — удалить все билеты из папки\n"
            "/upload_zip — загрузить ZIP-архив с билетами\n"
            "/myid — узнать свой user_id\n"
            "/broadcast текст/медиа — массовая рассылка\n"
            "/gen_invites — сгенерировать excel-файл с инвайтами\n"
            "/help — вывести это меню\n"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")
