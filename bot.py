import telebot
from config import BOT_TOKEN, DEFAULT_TICKET_FOLDER, WAVE_FILE
from database import *
from datetime import datetime

bot = telebot.TeleBot(BOT_TOKEN)

init_db()
sync_ticket_folder(DEFAULT_TICKET_FOLDER)

def get_wave_start():
    with open(WAVE_FILE, "r") as f:
        return datetime.fromisoformat(f.read().strip())

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username

    add_user(user_id, username)
    last_ticket_time = get_user_last_ticket_time(user_id)
    wave_start = get_wave_start()  # <-- нужно добавить это!

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


@bot.message_handler(commands=['new_wave'])
def handle_new_wave(message):
    admin_ids = [781477708]  # <-- сюда добавь свой user_id
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "У вас нет прав запускать новую волну.")
        return

    now = datetime.now().replace(microsecond=0)
    with open(WAVE_FILE, "w") as f:
        f.write(now.isoformat(" "))
    bot.send_message(message.chat.id, f"Новая волна началась! Время: {now}")

@bot.message_handler(commands=['myid'])
def handle_myid(message):
    bot.reply_to(message, f"Ваш user_id: {message.from_user.id}")


print("Бот запущен.")
bot.infinity_polling()
