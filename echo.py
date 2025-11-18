import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем токен из переменных окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Настраиваем логирование для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Функция для обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение при команде /start."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Привет! Я простой эхо-бот. Отправь мне любое сообщение, и я повторю его."
    )

# Функция для обработки текстовых сообщений (эхо)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторяет текстовое сообщение пользователя."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=update.message.text
    )

if __name__ == '__main__':
    # Создаем объект Application
    application = ApplicationBuilder().token(TOKEN).build()

    # Создаем обработчик для команды /start
    start_handler = CommandHandler('start', start)
    # Создаем обработчик для всех текстовых сообщений
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)

    # Регистрируем обработчики в приложении
    application.add_handler(start_handler)
    application.add_handler(echo_handler)

    # Запускаем бота (он будет работать, пока вы не остановите его вручную)
    print("Бот запущен...")
    application.run_polling()
