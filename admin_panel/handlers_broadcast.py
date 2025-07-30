import time
from .utils import admin_error_catcher, load_admins, admin_required, log_chat
from database import get_all_user_ids
import logging
logger = logging.getLogger(__name__)

def is_broadcast_command(m):
    # Ручной ввод (текст)
    if m.text and m.text.startswith('/broadcast'):
        return True
    # Ручной ввод или пересылка с caption
    if m.caption and m.caption.startswith('/broadcast'):
        return True
    # Вызов через меню: text подставлен как "/broadcast"
    if m.content_type in ['document', 'photo', 'animation', 'video'] and (hasattr(m, 'text') and m.text == '/broadcast'):
        return True
    return False

def register_broadcast_handlers(bot):
    @bot.message_handler(
        func=is_broadcast_command,
        content_types=['text', 'photo', 'animation', 'document', 'video']
    )
    @admin_required(bot)
    @admin_error_catcher(bot)
    def handle_broadcast(message):
        logger.info("Команда /broadcast вызвана пользователем %d", message.from_user.id)
        ADMINS = load_admins()
        if message.from_user.id not in ADMINS:
            bot.send_message(message.chat.id, "У вас нет доступа к этой функции.")
            return

        user_ids = get_all_user_ids()
        success, fail = 0, 0
        failed_ids = []
        sent_ids = []

        # Выделяем текст рассылки (caption для медиа, text для текста)
        if message.content_type in ['photo', 'animation', 'document', 'video']:
            if message.caption and message.caption.startswith('/broadcast'):
                caption = message.caption.replace('/broadcast', '', 1).strip()
            else:
                caption = (message.caption or '').strip()
        else:
            caption = message.text.replace('/broadcast', '', 1).strip() if message.text else ""

        # Для фото
        if message.content_type == 'photo':
            media_id = message.photo[-1].file_id
            for user_id in user_ids:
                try:
                    bot.send_photo(user_id, media_id, caption=caption)
                    log_chat(user_id, "BOT", f"[PHOTO]{' ' + caption if caption else ''}")
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"Ошибка send_photo для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.send_message(message.chat.id, f"📸 Фото-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для GIF/animation
        elif message.content_type == 'animation':
            media_id = message.animation.file_id
            for user_id in user_ids:
                try:
                    bot.send_animation(user_id, media_id, caption=caption)
                    log_chat(user_id, "BOT", f"[ANIMATION]{' ' + caption if caption else ''}")
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_animation для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.send_message(message.chat.id, f"🎞 GIF-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для документов (pdf, zip, png, jpg как файл и т.д.)
        elif message.content_type == 'document':
            media_id = message.document.file_id
            file_name = getattr(message.document, 'file_name', 'document')
            # ВНИМАНИЕ: не проверяем caption, можно рассылать даже если он пустой!
            for user_id in user_ids:
                try:
                    bot.send_document(user_id, media_id, caption=caption)
                    log_chat(user_id, "BOT", f"[DOCUMENT] {file_name}{' ' + caption if caption else ''}")
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_document для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.send_message(message.chat.id, f"📄 Рассылка файла завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

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
            bot.send_message(message.chat.id, f"🎬 Видео-рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Для текста
        elif message.content_type == 'text':
            if not caption:
                bot.send_message(message.chat.id, "Используй так: /broadcast текст_сообщения или прикрепи медиа с подписью.")
                return
            for user_id in user_ids:
                try:
                    bot.send_message(user_id, caption)
                    log_chat(user_id, "BOT", caption)
                    success += 1
                    sent_ids.append(user_id)
                except Exception as e:
                    print(f"❌ Ошибка send_message для {user_id}: {e}")
                    fail += 1
                    failed_ids.append(user_id)
                time.sleep(0.04)
            bot.send_message(message.chat.id, f"💬 Текстовая рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {fail}")

        # Вывод итоговых id в консоль (отладка)
        print(f"===[РАССЫЛКА /broadcast]===")
        print(f"Отправлено {success} из {len(user_ids)}")
        print(f"Ошибки были для id: {failed_ids}")
        print(f"Успешно: {sent_ids}")
        print("===")
