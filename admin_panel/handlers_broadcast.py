import time
from .utils import admin_error_catcher, load_admins, admin_required
from database import get_all_user_ids

def register_broadcast_handlers(bot):
    @bot.message_handler(
        func=lambda m: (m.text and m.text.startswith('/broadcast')) or (m.caption and m.caption.startswith('/broadcast')),
        content_types=['text', 'photo', 'animation', 'document', 'video']
    )
    @admin_required(bot)
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
                time.sleep(0.04)
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

        # Для особо внимательных админов — вывод итоговых id в консоль (отладка)
        print(f"===[РАССЫЛКА /broadcast]===")
        print(f"Отправлено {success} из {len(user_ids)}")
        print(f"Ошибки были для id: {failed_ids}")
        print(f"Успешно: {sent_ids}")
        print("===")
