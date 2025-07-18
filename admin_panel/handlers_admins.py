from .utils import admin_error_catcher, load_admins, save_admins, FOUNDER_IDS
from database import get_user_id_by_username

def register_admins_handlers(bot):
    @bot.message_handler(commands=['add_admin'])
    @admin_error_catcher(bot)
    def handle_add_admin(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        args = message.text.strip().split()
        if len(args) < 2 or not args[1].startswith("@"):
            bot.reply_to(message, "Используй так: /add_admin @username")
            return

        username = args[1][1:]
        user_id = get_user_id_by_username(username)
        if not user_id:
            bot.reply_to(message, f"Пользователь @{username} не найден в базе.")
            return

        if user_id in ADMINS:
            bot.reply_to(message, f"Пользователь @{username} уже админ.")
            return

        ADMINS.append(user_id)
        save_admins(ADMINS)
        bot.reply_to(message, f"Пользователь @{username} (id {user_id}) теперь администратор.")

    @bot.message_handler(commands=['remove_admin'])
    @admin_error_catcher(bot)
    def handle_remove_admin(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        args = message.text.strip().split()
        if len(args) < 2 or not args[1].startswith("@"):
            bot.reply_to(message, "Используй так: /remove_admin @username")
            return

        username = args[1][1:]
        user_id = get_user_id_by_username(username)
        if not user_id:
            bot.reply_to(message, f"Пользователь @{username} не найден в базе.")
            return

        if user_id not in ADMINS:
            bot.reply_to(message, f"Пользователь @{username} не был админом.")
            return

        if user_id in FOUNDER_IDS:
            bot.reply_to(message, "Этого админа нельзя удалить, он основатель!")
            return

        if user_id == message.from_user.id:
            bot.reply_to(message, "Нельзя удалить самого себя через эту команду.")
            return

        ADMINS.remove(user_id)
        save_admins(ADMINS)
        bot.reply_to(message, f"Пользователь @{username} (id {user_id}) больше не админ.")

    @bot.message_handler(commands=['myid'])
    @admin_error_catcher(bot)
    def handle_myid(message):
        bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")
