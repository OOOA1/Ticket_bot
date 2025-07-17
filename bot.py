import telebot
from config import BOT_TOKEN, DEFAULT_TICKET_FOLDER, WAVE_FILE
from database import *
from datetime import datetime
from database import get_latest_wave

bot = telebot.TeleBot(BOT_TOKEN)

import admin_panel
admin_panel.register_admin_handlers(bot)

init_db()
# sync_ticket_folder(DEFAULT_TICKET_FOLDER)



@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username

    add_user(user_id, username)
    last_ticket_time = get_user_last_ticket_time(user_id)
    wave_start = get_latest_wave()
    if not wave_start:
        bot.send_message(user_id, "Волна ещё не началась. Попроси админа запустить /new_wave.")
        return

    if last_ticket_time and last_ticket_time >= wave_start:
        bot.send_message(user_id, "Вы уже получили билет в этой волне.")
        return

    ticket_path = get_free_ticket()
    if not ticket_path:
        bot.send_message(user_id, "Билеты закончились.")
        return

    try:
        with open(ticket_path, 'rb') as pdf:
            bot.send_document(user_id, pdf)
        assign_ticket(ticket_path, user_id)
        bot.send_message(user_id, "Ваш билет отправлен. Удачного просмотра!")
    except Exception as e:
        bot.send_message(user_id, "Ошибка при отправке билета.")
        print(f"Ошибка: {e}")

print("Бот запущен.")
bot.infinity_polling()