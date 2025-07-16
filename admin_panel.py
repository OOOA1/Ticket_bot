# admin_panel.py

import os
from datetime import datetime
from telebot import types
from config import WAVE_FILE, DEFAULT_TICKET_FOLDER
from database import sync_ticket_folder
from zipfile import ZipFile
import tempfile

ADMINS = [5477727657]  # 🔁 Замените на свой user_id

# Простое хранилище состояния (вместо FSM)
upload_waiting = {}

def register_admin_handlers(bot):

    @bot.message_handler(commands=['new_wave'])
    def handle_new_wave(message):
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "У вас нет прав запускать новую волну.")
            return

        now = datetime.now().replace(microsecond=0)
        with open(WAVE_FILE, "w") as f:
            f.write(now.isoformat(" "))
        bot.send_message(message.chat.id, f"Новая волна началась! Время: {now}")

    @bot.message_handler(commands=['delete_all'])
    def delete_all_tickets(message):
        if message.from_user.id not in ADMINS:
            return
        count = 0
        for f in os.listdir(DEFAULT_TICKET_FOLDER):
            path = os.path.join(DEFAULT_TICKET_FOLDER, f)
            if os.path.isfile(path):
                os.remove(path)
                count += 1
        bot.send_message(message.chat.id, f"Удалено файлов: {count}")
        sync_ticket_folder(DEFAULT_TICKET_FOLDER)

    @bot.message_handler(commands=['list_tickets'])
    def list_tickets(message):
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
    def start_upload(message):
        if message.from_user.id not in ADMINS:
            return
        upload_waiting[message.from_user.id] = True
        bot.send_message(message.chat.id, "Пришли ZIP-файл с билетами.")

    @bot.message_handler(content_types=['document'])
    def handle_document(message):
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

                with ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(DEFAULT_TICKET_FOLDER)

                os.remove(zip_path)
                sync_ticket_folder(DEFAULT_TICKET_FOLDER)
                bot.send_message(message.chat.id, "Билеты успешно загружены.")
            except Exception as e:
                bot.send_message(message.chat.id, "Ошибка при загрузке архива.")
                print(f"Ошибка при обработке архива: {e}")

            upload_waiting[user_id] = False

    @bot.message_handler(commands=['myid'])
    def handle_myid(message):
        bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")
