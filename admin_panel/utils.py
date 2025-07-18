import os
import logging

ADMINS_FILE = "admins.txt"
FOUNDER_IDS = [781477708, 5477727657]
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

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        # Если файла нет — создаём пустой файл
        with open(ADMINS_FILE, "w") as f:
            pass
    with open(ADMINS_FILE, "r") as f:
        return [int(line.strip()) for line in f if line.strip().isdigit()]

def save_admins(admin_list):
    with open(ADMINS_FILE, "w") as f:
        for admin_id in admin_list:
            f.write(str(admin_id) + "\n")

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
