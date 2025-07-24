import os
import logging
from datetime import datetime
from database import get_admins, is_registered

LOG_FILE = "bot_errors.log"

# Состояния для загрузки и генерации инвайтов
upload_waiting = {}
awaiting_invite_count = {}

# --- Новое: состояния загрузки файлов ---
upload_files_received = {}   # сколько файлов прислал каждый админ после upload-команды
upload_files_time = {}       # время первого файла (для таймаута)
upload_files_buffer = {}     # сами документы, если нужно буферизовать их (опционально)


# Логгер для админских команд
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()  # вывод ошибок в консоль
    ]
)
logger = logging.getLogger("admin_panel")

def load_admins() -> list[int]:
    """Возвращает список ID админов из БД."""
    return get_admins()

def admin_required(bot):
    """
    Декоратор для проверки прав администратора.
    - Если user_id в admins: разрешаем.
    - Если user_id не в admins, но есть в users: пишем 'Нет прав', логируем и уведомляем.
    - Если user_id нет нигде: просто молчим.
    """
    def decorator(func):
        def wrapper(message, *args, **kwargs):
            ADMINS = get_admins()
            user_id = message.from_user.id
            username = getattr(message.from_user, "username", None)
            command = message.text.split()[0] if message.text else ""
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if user_id in ADMINS:
                # Всё ок, админ — пускаем дальше
                return func(message, *args, **kwargs)
            elif is_registered(user_id):
                # Не админ, но зарегистрированный пользователь — логируем и отвечаем
                logger.info(
                    f"[SECURITY] User {user_id} (@{username}) попытался вызвать команду {command} "
                    f"в {now} — прав нет"
                )

                # Сообщение всем админам
                for admin_id in ADMINS:
                    try:
                        bot.send_message(
                            admin_id,
                            f"⚠️ User <b>{user_id}</b> (@{username}) попытался использовать админ-команду <b>{command}</b> "
                            f"\nВремя: {now}",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                try:
                    bot.reply_to(message, "Нет прав для этой команды.")
                except Exception:
                    pass
                return
            else:
                # Вообще не авторизован — просто молчим!
                return
        return wrapper
    return decorator


def admin_error_catcher(bot):
    """
    Декоратор для красивого логирования ошибок в админских командах.
    """
    def decorator(func):
        def wrapper(message, *args, **kwargs):
            try:
                return func(message, *args, **kwargs)
            except Exception as e:
                logger.error(f"Ошибка в команде {func.__name__}: {e}", exc_info=True)
                try:
                    bot.reply_to(message, "❗️ Внутренняя ошибка. Она уже отправлена в лог.")
                except Exception:
                    pass
        return wrapper
    return decorator
