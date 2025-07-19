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
            "/new_wave — начать новую волну раздачи билетов\n"
            "/send_tickets — начать массовую рассылку билетов всем пользователям в текущей волне\n"
            "/retry_send_tickets — повторить рассылку для тех, кому не дошло\n"
            # остальные команды, как были
            "/stats — статистика по билетам и пользователям\n"
            "/upload_zip — загрузить ZIP-архив с билетами (старые будут архивированы)\n"
            "/upload_zip_add — дозагрузить билеты к уже имеющимся (без архивирования)\n"
            "/list_tickets — получить список всех билетов\n"
            "/delete_all — удалить все билеты из папки\n"
            "/broadcast текст/медиа — массовая рассылка сообщения/файла\n"
            "/gen_invites — сгенерировать excel-файл с инвайт-кодами\n"
            "/add_admin @username — добавить нового админа\n"
            "/remove_admin @username — удалить админа\n"
            "/myid — узнать свой user_id\n"
            "/force_give @username — вручную выдать билет пользователю\n"
            "/help — вывести это меню\n"
            "\n🟢 После /new_wave используйте /send_tickets для выдачи билетов всем пользователям.\n"
            "🟢 Если кому-то не удалось выдать билет, используйте /retry_send_tickets для повторной попытки.\n"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")
