import os
import tempfile
from zipfile import ZipFile
import shutil
import hashlib
from uuid import uuid4
from datetime import datetime
from database import mark_ticket_archived_unused, mark_ticket_lost, archive_missing_tickets, archive_all_old_free_tickets
from .utils import admin_error_catcher, load_admins
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
                # Отметить билет как утраченный
                mark_ticket_lost(path)
                count += 1
        # На всякий случай чистим и все битые билеты, если что-то осталось
        archive_missing_tickets()
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
        mode = upload_waiting.get(user_id)
        if user_id in ADMINS and mode:
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

                if mode == True:
                    # СТАРАЯ ЛОГИКА — архивировать старые, добавить новые
                    report_path = process_zip(zip_path, uploaded_by=user_id, bot=bot)
                elif mode == 'add':
                    # ДОЗАГРУЗКА: только добавить новые файлы, ничего не архивировать
                    report_path = process_zip_add(zip_path, uploaded_by=user_id, bot=bot)
                else:
                    report_path = None

                if report_path:
                    with open(report_path, 'rb') as rep:
                        bot.send_document(message.chat.id, rep, caption="📄 Отчёт о загрузке билетов")
                    os.remove(report_path)
                os.remove(zip_path)
            except Exception as e:
                bot.send_message(message.chat.id, "Ошибка при загрузке архива.")
                logger.error(f"Ошибка при обработке архива: {e}", exc_info=True)

            upload_waiting[user_id] = False

    
    @bot.message_handler(commands=['upload_zip_add'])
    @admin_error_catcher(bot)
    def start_upload_add(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        upload_waiting[message.from_user.id] = 'add'
        bot.send_message(message.chat.id, "Пришли ZIP-файл для ДОЗАГРУЗКИ билетов (старые останутся).")



# ==== Вспомогательные функции, используются только внутри tickets ====

def archive_old_tickets():
    # 1) Находим все PDF в папке
    pdf_files = [
        f for f in os.listdir(DEFAULT_TICKET_FOLDER)
        if f.lower().endswith('.pdf')
    ]
    if not pdf_files:
        return None  # нечего архивировать

    # 2) Формируем уникальное имя с микросекундами
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    archive_dir = "archive"
    temp_folder = os.path.join(archive_dir, f"_temp_{now}")
    zip_name = f"{now}.zip"
    zip_path = os.path.join(archive_dir, zip_name)

    os.makedirs(temp_folder, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # 3) Перемещаем PDF во временную папку
    for file_name in pdf_files:
        src = os.path.join(DEFAULT_TICKET_FOLDER, file_name)
        dst = os.path.join(temp_folder, file_name)
        # --- вот здесь!
        mark_ticket_archived_unused(src)
        os.rename(src, dst)

    # 4) Запаковываем в новый ZIP
    with ZipFile(zip_path, 'w') as zipf:
        for file_name in os.listdir(temp_folder):
            zipf.write(os.path.join(temp_folder, file_name), arcname=file_name)

    # 5) Удаляем временную папку
    shutil.rmtree(temp_folder)

    # 6) RETENTION — оставляем только 3 последних архива
    max_archives = 3
    archives = sorted(
        f for f in os.listdir(archive_dir)
        if f.lower().endswith('.zip')
    )
    if len(archives) > max_archives:
        for old in archives[:-max_archives]:
            try:
                os.remove(os.path.join(archive_dir, old))
            except OSError:
                pass

    return zip_path

def process_zip(zip_path, uploaded_by, bot):
    added, duplicates, not_pdf = [], [], []
    seen_hashes = set()  # для уникальности внутри одного архива
    temp_store = []

    # 1) Сканируем архив, собираем только новые и уникальные файлы
    with ZipFile(zip_path, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            original_name = file_info.filename
            if not original_name.lower().endswith(".pdf"):
                not_pdf.append(original_name)
                continue

            content = zip_ref.read(file_info)
            file_hash = hashlib.sha256(content).hexdigest()

            # пропускаем, если в базе уже есть
            if is_duplicate_hash(file_hash):
                duplicates.append(original_name)
                continue

            # пропускаем, если уже встретили такой же файл в этом же архиве
            if file_hash in seen_hashes:
                duplicates.append(original_name)
                continue

            seen_hashes.add(file_hash)
            uuid_name = f"{uuid4()}.pdf"
            full_path = os.path.join(DEFAULT_TICKET_FOLDER, uuid_name)
            temp_store.append((content, file_hash, original_name, full_path, uuid_name))

    # 2) Если нет новых PDF — отменяем весь процесс
    if not temp_store:
        bot.send_message(
            uploaded_by,
            "⛔️ В архиве нет новых PDF-файлов (все либо дубликаты, либо не PDF).",
            parse_mode="HTML"
        )
        return None

    # 3) Архивируем старые билеты (только раз, перед добавлением новых)
    archive_result = archive_old_tickets()
    if archive_result:
        bot.send_message(
            uploaded_by,
            f"📦 Старые билеты перемещены в архив:\n<code>{archive_result}</code>",
            parse_mode="HTML"
        )
        logger.info(f"Архив старых билетов создан: {archive_result}")

    # 4) Сохраняем новые файлы и вносим запись в БД
    for content, file_hash, original_name, full_path, uuid_name in temp_store:
        try:
            with open(full_path, "wb") as f:
                f.write(content)
            insert_ticket(full_path, file_hash, original_name, uploaded_by)
            added.append((original_name, uuid_name))
        except sqlite3.IntegrityError:
            # на всякий случай — если вдруг hash успел появиться в параллельном процессе
            duplicates.append(original_name)

    # 5) Формируем и возвращаем отчёт
    report_lines = [
        "=== Отчёт по загрузке билетов ===",
        f"Добавлено новых файлов: {len(added)}",
        f"Пропущено дубликатов: {len(duplicates)}",
        f"Пропущено не PDF: {len(not_pdf)}",
        ""
    ]
    if added:
        report_lines.append("✅ Добавлены:")
        report_lines += [f"- {orig} → {new}" for orig, new in added]
    if duplicates:
        report_lines.append("\n♻️ Дубликаты:")
        report_lines += [f"- {name}" for name in duplicates]
    if not_pdf:
        report_lines.append("\n❌ Не PDF:")
        report_lines += [f"- {name}" for name in not_pdf]

    report_text = "\n".join(report_lines)
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
        temp_file.write(report_text)
        return temp_file.name
    

def process_zip_add(zip_path, uploaded_by, bot):
    added, duplicates, not_pdf = [], [], []
    seen_hashes = set()

    from database import is_duplicate_hash, insert_ticket

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
            if file_hash in seen_hashes:
                duplicates.append(original_name)
                continue
            seen_hashes.add(file_hash)
            uuid_name = f"{uuid4()}.pdf"
            full_path = os.path.join(DEFAULT_TICKET_FOLDER, uuid_name)
            with open(full_path, "wb") as f:
                f.write(content)
            insert_ticket(full_path, file_hash, original_name, uploaded_by)
            added.append((original_name, uuid_name))

    report_lines = [
        "=== Отчёт по ДОЗАГРУЗКЕ билетов ===",
        f"Добавлено новых файлов: {len(added)}",
        f"Пропущено дубликатов: {len(duplicates)}",
        f"Пропущено не PDF: {len(not_pdf)}",
        ""
    ]
    if added:
        report_lines.append("✅ Добавлены:")
        report_lines += [f"- {orig} → {new}" for orig, new in added]
    if duplicates:
        report_lines.append("\n♻️ Дубликаты:")
        report_lines += [f"- {name}" for name in duplicates]
    if not_pdf:
        report_lines.append("\n❌ Не PDF:")
        report_lines += [f"- {name}" for name in not_pdf]

    report_text = "\n".join(report_lines)
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
        temp_file.write(report_text)
        return temp_file.name
