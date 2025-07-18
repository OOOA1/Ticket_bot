import os
import tempfile
from zipfile import ZipFile
import shutil
import hashlib
from uuid import uuid4
from datetime import datetime

from config import DEFAULT_TICKET_FOLDER
from .utils import admin_error_catcher, load_admins, upload_waiting, logger
from database import (
    get_free_ticket_count,
    is_duplicate_hash,
    insert_ticket,
)

def register_tickets_handlers(bot):
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

# ==== Вспомогательные функции, используются только внутри tickets ====

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

    report_lines = [
        "=== Отчёт по загрузке билетов ===",
        f"Добавлено новых файлов: {len(added)}",
        f"Пропущено дубликатов: {len(duplicates)}",
        f"Пропущено не PDF: {len(not_pdf)}",
        ""
    ]
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
