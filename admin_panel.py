import os
import time
from invite_admin import generate_invites, export_invites_xlsx
from database import get_wave_stats
from datetime import datetime
from telebot import types
from database import get_all_user_ids
from config import WAVE_FILE, DEFAULT_TICKET_FOLDER
#from database import sync_ticket_folder
from database import get_user_id_by_username, get_user_last_ticket_time, get_free_ticket, assign_ticket, insert_ticket, is_duplicate_hash, get_free_ticket_count
from zipfile import ZipFile
import tempfile
import logging
from database import create_new_wave
from uuid import uuid4
import hashlib
import shutil

ADMINS_FILE = "admins.txt"
FOUNDER_IDS = [781477708, 5477727657]
LOG_FILE = "bot_errors.log"
awaiting_invite_count = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()  # чтобы видеть ошибки и в консоли тоже
    ]
)
logger = logging.getLogger("admin_panel")

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        # Если файла нет — создаём пустой файл, чтобы ты сам туда добавил id
        with open(ADMINS_FILE, "w") as f:
            pass
    with open(ADMINS_FILE, "r") as f:
        return [int(line.strip()) for line in f if line.strip().isdigit()]

def save_admins(admin_list):
    with open(ADMINS_FILE, "w") as f:
        for admin_id in admin_list:
            f.write(str(admin_id) + "\n")

# Простое хранилище состояния (вместо FSM)
upload_waiting = {}

def admin_error_catcher(bot):
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

def register_admin_handlers(bot):

    @bot.message_handler(commands=['new_wave'])
    @admin_error_catcher(bot)
    def handle_new_wave(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет прав запускать новую волну.")
            return
        if get_free_ticket_count() == 0:
            bot.send_message(message.chat.id, "🚫 Нельзя начать волну — нет доступных билетов. Сначала загрузите билеты через /upload_zip.")
            return

        now = create_new_wave(message.from_user.id)
        # === добавляем обновление файла!
        with open(WAVE_FILE, "w") as f:
            f.write(now)
        bot.send_message(message.chat.id, f"Новая волна началась! Время: {now}")

    @bot.message_handler(commands=['delete_all'])
    @admin_error_catcher(bot)
    def delete_all_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        count = 0
        for f in os.listdir(DEFAULT_TICKET_FOLDER):
            path = os.path.join(DEFAULT_TICKET_FOLDER, f)
            if os.path.isfile(path):
                os.remove(path)
                count += 1
        bot.send_message(message.chat.id, f"Удалено файлов: {count}")
        #sync_ticket_folder(DEFAULT_TICKET_FOLDER)

    @bot.message_handler(commands=['list_tickets'])
    @admin_error_catcher(bot)
    def list_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return

        files = os.listdir(DEFAULT_TICKET_FOLDER)
        if not files:
            bot.send_message(message.chat.id, "Нет загруженных билетов.")
            return

        # Создаём временный .txt файл с именами
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            file_list = "\n".join(files)
            temp_file.write(file_list)
            temp_file_path = temp_file.name

        # Отправляем файл как документ
        with open(temp_file_path, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption="Список загруженных билетов")

        # Удаляем временный файл
        os.remove(temp_file_path)

    @bot.message_handler(commands=['upload_zip'])
    @admin_error_catcher(bot)
    def start_upload(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        upload_waiting[message.from_user.id] = True
        bot.send_message(message.chat.id, "Пришли ZIP-файл с билетами.")

    @bot.message_handler(content_types=['document'])
    @admin_error_catcher(bot)
    def handle_document(message):
        ADMINS = load_admins()
        user_id = message.from_user.id
        if user_id in ADMINS and upload_waiting.get(user_id):
            doc = message.document
            if not doc.file_name.endswith('.zip'):
                bot.reply_to(message, "Пожалуйста, пришли .zip архив.")
                return
            try:
                file_info = bot.get_file(doc.file_id)
                downloaded = bot.download_file(file_info.file_path)
                zip_path = f"temp_upload_{user_id}.zip"
                with open(zip_path, 'wb') as f:
                    f.write(downloaded)
                report_path = process_zip(zip_path, uploaded_by=user_id, bot=bot)
                with open(report_path, 'rb') as rep:
                    bot.send_document(message.chat.id, rep, caption="📄 Отчёт о загрузке билетов")
                os.remove(report_path)
                os.remove(zip_path)
            except Exception as e:
                bot.send_message(message.chat.id, "Ошибка при загрузке архива.")
                logger.error(f"Ошибка при обработке архива: {e}", exc_info=True)
            upload_waiting[user_id] = False


    @bot.message_handler(commands=['myid'])
    @admin_error_catcher(bot)
    def handle_myid(message):
        bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")

    @bot.message_handler(commands=['stats'])
    @admin_error_catcher(bot)
    def handle_stats(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        # === Проверка на существование файла ===
        import os
        if not os.path.exists(WAVE_FILE):
            bot.send_message(message.chat.id, "Волна ещё не начиналась.")
            return

        with open(WAVE_FILE, "r") as f:
            wave_start = datetime.fromisoformat(f.read().strip())

        users_with_ticket, free_tickets, all_users = get_wave_stats(wave_start)

        # Подсчёт числа волн
        if os.path.exists("waves.txt"):
            with open("waves.txt", "r") as wf:
                total_waves = len([line for line in wf if line.strip()])
        else:
            total_waves = 1

        text = (
            f"📊 Статистика по текущей волне:\n"
            f"— Пользователей с билетом: {users_with_ticket}\n"
            f"— Свободных билетов: {free_tickets}\n"
            f"— Всего пользователей: {all_users}\n"
            f"— Всего волн было: {total_waves}"
        )
        bot.send_message(message.chat.id, text)
    
    @bot.message_handler(commands=['force_give'])
    @admin_error_catcher(bot)
    def handle_force_give(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        # Проверяем, есть ли аргумент username
        args = message.text.strip().split()
        if len(args) < 2 or not args[1].startswith("@"):
            bot.reply_to(message, "Используй так: /force_give @username")
            return

        username = args[1][1:]  # убираем @

        user_id = get_user_id_by_username(username)
        if not user_id:
            bot.reply_to(message, f"Пользователь с username @{username} не найден в базе.")
            return

        # Проверяем, получал ли он уже билет в текущей волне
        with open(WAVE_FILE, "r") as f:
            wave_start = datetime.fromisoformat(f.read().strip())
        last_ticket_time = get_user_last_ticket_time(user_id)
        if last_ticket_time and last_ticket_time >= wave_start:
            bot.reply_to(message, f"Пользователь @{username} уже получил билет в этой волне.")
            return

        ticket_path = get_free_ticket()
        if not ticket_path:
            bot.reply_to(message, "Билеты закончились.")
            return

        try:
            with open(ticket_path, 'rb') as pdf:
                bot.send_document(user_id, pdf)
            assign_ticket(ticket_path, user_id)
            bot.reply_to(message, f"Билет отправлен пользователю @{username}!")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при отправке билета: {e}")
    
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

    @bot.message_handler(
    func=lambda m: (m.text and m.text.startswith('/broadcast')) or (m.caption and m.caption.startswith('/broadcast')),
    content_types=['text', 'photo', 'animation', 'document', 'video']
    )
    @admin_error_catcher(bot)
    def handle_broadcast(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "Нет прав для этой команды.")
            return

        user_ids = get_all_user_ids()
        success, fail = 0, 0
        failed_ids = []
        sent_ids = []

        # Выделяем текст рассылки (для caption/text)
        if message.content_type in ['photo', 'animation', 'document', 'video']:
            caption = (message.caption or '').replace('/broadcast', '', 1).strip()
        else:
            caption = message.text.replace('/broadcast', '', 1).strip()

        # Для фото
        if message.content_type == 'photo':
            media_id = message.photo[-1].file_id
            for user_id in user_ids:
                try:
                    bot.send_photo(user_id, media_id, caption=caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_photo для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)  # пауза, чтобы не спамить

            bot.reply_to(message, f"📸 Фото-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для GIF/animation
        elif message.content_type == 'animation':
            media_id = message.animation.file_id
            for user_id in user_ids:
                try:
                    bot.send_animation(user_id, media_id, caption=caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_animation для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.reply_to(message, f"🎞 GIF-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для документов (pdf, png, jpg как файл и т.д.)
        elif message.content_type == 'document':
            media_id = message.document.file_id
            for user_id in user_ids:
                try:
                    bot.send_document(user_id, media_id, caption=caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_document для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.reply_to(message, f"📄 Рассылка файла завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для видео
        elif message.content_type == 'video':
            media_id = message.video.file_id
            for user_id in user_ids:
                try:
                    bot.send_video(user_id, media_id, caption=caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_video для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.reply_to(message, f"🎬 Видео-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для текста
        elif message.content_type == 'text':
            if not caption:
                bot.reply_to(message, "Используй так: /broadcast текст_сообщения или прикрепи медиа с подписью.")
                return
            for user_id in user_ids:
                try:
                    bot.send_message(user_id, caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_message для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.reply_to(message, f"💬 Текстовая рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для особо внимательных админов — в консоль выводим итоговые id для отладки
        print(f"===[РАССЫЛКА /broadcast]===")
        print(f"Отправлено {success} из {len(user_ids)}")
        print(f"Ошибки были для id: {failed_ids}")
        print(f"Успешно: {sent_ids}")
        print("===")

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
        os.remove(temp_path)
    

    def archive_old_tickets():
        pdf_files = [f for f in os.listdir(DEFAULT_TICKET_FOLDER) if f.lower().endswith('.pdf')]
        if not pdf_files:
            return None  # Нечего архивировать

        now = datetime.now().strftime("%Y-%m-%d_%H-%M")
        temp_folder = os.path.join("archive", f"_temp_{now}")
        zip_path = os.path.join("archive", f"{now}.zip")

        os.makedirs(temp_folder, exist_ok=True)

        # Перемещаем PDF-файлы во временную папку
        for file_name in pdf_files:
            src = os.path.join(DEFAULT_TICKET_FOLDER, file_name)
            dst = os.path.join(temp_folder, file_name)
            os.rename(src, dst)

        # Упаковываем во .zip
        with ZipFile(zip_path, 'w') as zipf:
            for file_name in os.listdir(temp_folder):
                file_path = os.path.join(temp_folder, file_name)
                zipf.write(file_path, arcname=file_name)

        # Удаляем временную папку
        shutil.rmtree(temp_folder)

        return zip_path

    def process_zip(zip_path, uploaded_by, bot):
        archive_result = archive_old_tickets()
        if archive_result:
            bot.send_message(
                uploaded_by,
                f"📦 Старые билеты были перемещены в архив:\n<code>{archive_result}</code>",
                parse_mode="HTML"
            )
            logger.info(f"Архив старых билетов создан: {archive_result}")
        if archive_result:
            print(f"🎒 Сохранён архив старых билетов: {archive_result}")

        added, duplicates, not_pdf = [], [], []
        with ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                original_name = file_info.filename
                if not original_name.lower().endswith(".pdf"):
                    not_pdf.append(original_name)
                    continue
                content = zip_ref.read(file_info)
                file_hash = hashlib.sha256(content).hexdigest()
                if is_duplicate_hash(file_hash):
                    duplicates.append(original_name)
                    continue
                uuid_name = str(uuid4()) + ".pdf"
                full_path = os.path.join(DEFAULT_TICKET_FOLDER, uuid_name)
                with open(full_path, "wb") as f:
                    f.write(content)
                insert_ticket(full_path, file_hash, original_name, uploaded_by)
                added.append((original_name, uuid_name))

        report_lines = ["=== Отчёт по загрузке билетов ===", f"Добавлено новых файлов: {len(added)}", f"Пропущено дубликатов: {len(duplicates)}", f"Пропущено не PDF: {len(not_pdf)}", ""]
        if added:
            report_lines.append("✅ Добавлены:")
            report_lines.extend([f"- {orig} → {new}" for orig, new in added])
        if duplicates:
            report_lines.append("\n♻️ Дубликаты:")
            report_lines.extend([f"- {name}" for name in duplicates])
        if not_pdf:
            report_lines.append("\n❌ Не PDF:")
            report_lines.extend([f"- {name}" for name in not_pdf])

        report_text = "\n".join(report_lines)
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            temp_file.write(report_text)
            return temp_file.name

    upload_waiting = {}
