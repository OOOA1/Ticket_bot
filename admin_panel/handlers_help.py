from .utils import admin_error_catcher, load_admins, admin_required
import logging
logger = logging.getLogger(__name__)

def register_help_handlers(bot):
    @bot.message_handler(commands=['help'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_help(message):
        logger.info("Команда /help вызвана пользователем %d", message.from_user.id)
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        text = (
            "<b>🔑 Админ-команды по работе с волнами и билетами:</b>\n\n"
            "/start — запустить (или перезапустить) бота\n"
            "/new_wave — начать подготовку новой волны раздачи билетов\n"
            "/upload_zip — загрузить ZIP-архив с билетами (старые архивируются)\n"
            "/upload_zip_add — дозагрузить новые билеты (старые остаются)\n"
            "/confirm_wave — подтвердить запуск волны после загрузки билетов\n"
            "/send_tickets — массовая рассылка билетов всем пользователям (бот автоматически повторяет попытки тем, кому не удалось отправить с первого раза)\n"
            "/failed_report — Excel-отчет о пользователях, которым не удалось доставить билеты (контроль неудачных рассылок)\n"
            "/force_give @username — вручную выдать билет пользователю по username (обходит общую рассылку)\n"
            "/force_give user_id — вручную выдать билет по user_id\n"
            "/delete_all — удалить все билеты из папки и пометить их как утраченные\n"
            "/list_tickets — Excel-отчет со всеми билетами и их статусами\n"
            "/stats — статистика по билетам и пользователям (по текущей или неактивной волне)\n"
            "/end_wave — завершить или сбросить текущую волну\n"
            "\n"
            "<b>👥 Управление пользователями и доступами:</b>\n"
            "/gen_invites — сгенерировать excel-файл с инвайт-кодами для приглашения\n"
            "/export_users — получить excel-файл со всеми пользователями и администраторами\n"
            "/add_admin @username — добавить нового администратора\n"
            "/remove_admin @username — удалить администратора\n"
            "/delete_user user_id @username — полностью удалить пользователя из системы и аннулировать все его билеты\n"
            "/myid — узнать свой user_id (например, для назначения админа)\n"
            "\n"
            "<b>💬 Логи и аудит переписки:</b>\n"
            "/chatlog user_id — получить txt-файл всей переписки с пользователем\n"
            "/chatlog @username — то же самое по username\n"
            "\n"
            "<b>📢 Рассылки и уведомления:</b>\n"
            "/broadcast текст/медиа — массовая рассылка сообщения/файла всем пользователям\n"
            "\n"
            "🟢 <b>Рекомендуемый порядок работы:</b>\n"
            "1️⃣ /new_wave — подготовка новой волны\n"
            "2️⃣ /upload_zip — загрузка билетов (или /upload_zip_add для дозагрузки)\n"
            "3️⃣ /confirm_wave — подтверждение волны\n"
            "4️⃣ /send_tickets — массовая выдача билетов\n"
            "\n"
            "ℹ️ В случае проблем используйте:\n"
            "• /failed_report — контроль неудачных доставок\n"
            "• /force_give — ручная выдача билета\n"
            "• /delete_user — полное удаление пользователя\n"
            "\n"
            "<i>⚠️ Команды <b>/force_give</b> и <b>/delete_user</b> использовать только в ручных/форс-мажорных случаях!</i>\n"
        )

        bot.send_message(message.chat.id, text, parse_mode="HTML")