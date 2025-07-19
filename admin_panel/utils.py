import os
import logging
from database import get_admins

LOG_FILE = "bot_errors.log"

# Состояния для загрузки и генерации инвайтов
upload_waiting = {}
awaiting_invite_count = {}

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
