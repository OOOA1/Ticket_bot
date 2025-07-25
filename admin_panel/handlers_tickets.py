import os
import sqlite3
import tempfile
import xlsxwriter
from zipfile import ZipFile
import shutil
import hashlib
from uuid import uuid4
from datetime import datetime
from database import mark_ticket_archived_unused, mark_ticket_lost, archive_missing_tickets, archive_all_old_free_tickets, get_current_wave_id
from .utils import (
    admin_error_catcher, load_admins, upload_waiting, logger, admin_required,
    upload_files_received, upload_files_time
)
import time  # понадобится для таймаута
from config import DEFAULT_TICKET_FOLDER
from database import (
    get_free_ticket_count,
    is_duplicate_hash,
    insert_ticket,
    get_wave_state,
    resolve_user_id,
    get_user_last_ticket_time,
    get_latest_wave,
    get_current_wave_id,
    get_free_ticket,
    assign_ticket,
    is_registered,
    get_wave_state,
    DB_PATH,
    archive_missing_tickets
)

def register_tickets_handlers(bot):
    @bot.message_handler(commands=['delete_all'])
    @admin_required(bot)
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
    @admin_required(bot)
    @admin_error_catcher(bot)
    def list_tickets(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        # Актуализируем: помечаем в базе как LOST все отсутствующие файлы
        archive_missing_tickets()
        # 1) Получаем все записи из таблицы tickets
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT file_path, original_name, assigned_to, assigned_at, archived_unused, lost, wave_id
            FROM tickets
        """)
        rows = cur.fetchall()
        conn.close()  
        if not rows:
            bot.send_message(message.chat.id, "Нет загруженных билетов.")
            return
        # 2) Генерируем Excel-файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            wb = xlsxwriter.Workbook(tmp.name)
            ws = wb.add_worksheet("Tickets Status")
            # Заголовки
            headers = ["File Path", "Original Name", "Status", "Assigned To", "Assigned At", "Wave ID"]
            for col, hdr in enumerate(headers):
                ws.write(0, col, hdr) 
            # Данные
            for i, (path, orig, assigned_to, assigned_at, archived_unused, lost, wave_id) in enumerate(rows, start=1):
                if lost:
                    status = "LOST"
                elif assigned_to is not None:
                    status = "SENT"
                elif archived_unused:
                    status = "ARCHIVED"
                else:
                    status = "AVAILABLE"  
                ws.write(i, 0, path)
                ws.write(i, 1, orig)
                ws.write(i, 2, status)
                ws.write(i, 3, assigned_to or "")
                ws.write(i, 4, assigned_at or "")
                ws.write(i, 5, wave_id or "") 
            wb.close()
            report_path = tmp.name
        # 3) Отправляем отчёт администратору
        with open(report_path, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption="📊 Список билетов с их статусами")
        os.remove(report_path)

    @bot.message_handler(commands=['upload_zip'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def start_upload(message):
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            return
        
        state = get_wave_state()

        # ⛔️ Запрещаем повторную загрузку в рамках одной волны
        if state["status"] == "awaiting_confirm":
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM tickets
                WHERE assigned_to IS NULL
                AND archived_unused = 0
                AND lost = 0
                AND wave_id IS NULL
            """)
            existing = cur.fetchone()[0]
            conn.close()

            if existing > 0:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Вы уже загружали {existing} билетов для этой волны.\n"
                    f"Чтобы дозагрузить билеты без удаления старых, используйте команду /upload_zip_add.\n"
                    f"Если хотите начать заново — выполните /end_wave и /new_wave."
                )
                return
            
        if state["status"] != "awaiting_confirm":
            bot.send_message(
                message.chat.id,
                "⚠️ Сейчас нельзя загружать билеты — сначала выполните /new_wave."
            )
            return
        
        # ✅ Всё в порядке — активируем режим загрузки
        upload_waiting[message.from_user.id] = True
        upload_files_received[message.from_user.id] = 0
        upload_files_time[message.from_user.id] = None
        bot.send_message(message.chat.id, "Пришли ZIP-файл с билетами.")

    @bot.message_handler(content_types=['document'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_document(message):
        ADMINS = load_admins()
        user_id = message.from_user.id

        # --- Новое: если вне режима ожидания — молчим, ничего не пишем! ---
        if user_id not in upload_files_received or not upload_waiting.get(user_id):
            return

        mode = upload_waiting.get(user_id)
        state = get_wave_state()
        # Только админы, только когда действительно ждём загрузку
        if user_id not in ADMINS or not mode:
            upload_files_received.pop(user_id, None)
            upload_files_time.pop(user_id, None)
            return
        # Проверяем, разрешено ли в текущем статусе
        if mode == 'add':
            if state["status"] not in ("awaiting_confirm", "active"):
                bot.reply_to(
                    message,
                    "⚠️ Дозагрузка билетов возможна только во время подготовки (/new_wave) "
                    "или во время активной волны."
                )
                upload_waiting[user_id] = False
                return
        else:  # первичная загрузка
            if state["status"] != "awaiting_confirm":
                bot.reply_to(
                    message,
                    "⚠️ Первичная загрузка билетов возможна только во время подготовки волны (/new_wave)."
                )
                upload_waiting[user_id] = False
                return


            if upload_files_received.get(user_id, 0) == 0:
                upload_files_time[user_id] = time.time()
            upload_files_received[user_id] = upload_files_received.get(user_id, 0) + 1

            # --- Главная защита: если больше одного файла — только один раз шлём ошибку, дальше молчим ---
            if upload_files_received[user_id] > 1:
                bot.reply_to(message, "❌ Ты не можешь прикрепить несколько zip-файлов, пришли только 1!")
                logger.info(f"User {user_id} пытался отправить больше одного zip-файла — отказано без ошибок.")
                # Сбросили состояния — больше ничего не делаем!
                upload_waiting[user_id] = False
                upload_files_received.pop(user_id, None)
                upload_files_time.pop(user_id, None)
                return

            time_passed = time.time() - upload_files_time[user_id]
            if time_passed < 2:
                time.sleep(2 - time_passed)
                
            # После ожидания — финальная проверка!
            if upload_files_received.get(user_id, 0) > 1 or not upload_waiting.get(user_id):
                # Ничего не делаем, ошибку уже отправили, состояния сброшены
                return


            # после всех проверок — принимаем ZIP-файл
            doc = message.document
            if not doc.file_name.endswith('.zip'):
                bot.reply_to(message, "Пожалуйста, пришлите ZIP-архив (.zip).")
                upload_waiting[user_id] = False
                return
                        
            try:
                file_info = bot.get_file(doc.file_id)
                downloaded = bot.download_file(file_info.file_path)
                zip_path = f"temp_upload_{user_id}.zip"
                with open(zip_path, 'wb') as f:
                    f.write(downloaded)
        
                if mode is True:
                    report_path = process_zip(zip_path, uploaded_by=user_id, bot=bot)
                else:
                    report_path = process_zip_add(zip_path, uploaded_by=user_id, bot=bot)

                # Отправляем отчёт, если он есть
                if report_path:
                    with open(report_path, 'rb') as rep:
                        bot.send_document(message.chat.id, rep, caption="📄 Отчёт о загрузке билетов")
                    os.remove(report_path)

                # Удаляем сам ZIP
                os.remove(zip_path)

            except Exception as e:
                bot.send_message(message.chat.id, "❗️ Ошибка при обработке архива.")
                logger.error(f"Ошибка при обработке архива для user_id={user_id}: {e}", exc_info=True)
            finally:

                upload_waiting[user_id] = False
                upload_files_received.pop(user_id, None)
                upload_files_time.pop(user_id, None)

    @bot.message_handler(commands=['upload_zip_add'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def start_upload_add(message):
        ADMINS = load_admins()
        state = get_wave_state()
        if message.from_user.id not in ADMINS:
            return
        
        if state["status"] == "idle":
            bot.reply_to(
                message,
                "⚠️ Дозагрузка билетов доступна только после /new_wave (в режимах подготовки и активной волны)."
            )
        upload_waiting[message.from_user.id] = 'add'
        upload_files_received[message.from_user.id] = 0
        upload_files_time[message.from_user.id] = None
        bot.send_message(message.chat.id, "Пришли ZIP-файл для ДОЗАГРУЗКИ билетов (старые останутся).")

    @bot.message_handler(commands=['force_give'])
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_force_give(message):
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "Используйте: /force_give @username или /force_give user_id")
            return

        user_ref = args[1]
        user_id = resolve_user_id(user_ref)
        if not user_id or not is_registered(user_id):
            bot.reply_to(message, "Пользователь не найден в базе.")
            return

        wave_start = get_latest_wave()
        wave_id = get_current_wave_id()
        if not wave_id or not wave_start:
            bot.reply_to(message, "Нет активной волны.")
            return

        last_ticket = get_user_last_ticket_time(user_id)
        if last_ticket and last_ticket >= wave_start:
            bot.reply_to(message, "Пользователь уже получил билет в этой волне.")
            return

        ticket_path = get_free_ticket(wave_id)
        if not ticket_path:
            bot.reply_to(message, "Нет доступных билетов для выдачи.")
            return

        try:
            with open(ticket_path, "rb") as pdf:
                bot.send_document(user_id, pdf, caption="🎟 Ваш билет выдан вручную администратором.")
            assign_ticket(ticket_path, user_id)
            bot.reply_to(message, f"✅ Билет отправлен пользователю {user_ref}.")
            logger.info(f"Админ {message.from_user.id} выдал билет пользователю {user_id} через /force_give.")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при отправке билета: {e}")
            logger.error(f"Ошибка выдачи билета через /force_give: {e}", exc_info=True)



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
            # Привязываем новый билет к текущей активной волне
            wave_id = get_current_wave_id()
            conn = sqlite3.connect("users.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE tickets SET wave_id = ? WHERE file_path = ?",
                (wave_id, full_path)
            )
            conn.commit()
            conn.close()
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
