import logging
import os
import re
import serial
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# SERIAL_PORT = '/dev/ttyACM0'  # Проверьте актуальный порт Arduino (может быть /dev/ttyUSB0) (Raspberry Pi)
SERIAL_PORT = 'COM4'  # Для Windows
BAUD_RATE = 9600
AUTHORIZED_CHAT_ID = int(os.getenv("AUTHORIZED_CHAT_ID", 0))  # Опционально: ID авторизованного пользователя

# Глобальная переменная для последовательного порта
ser = None

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)

# Инициализация последовательного порта
async def init_serial():
    global ser
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        logging.info(f"Последовательный порт {SERIAL_PORT} успешно открыт")
        return True
    except serial.SerialException as e:
        logging.error(f"Ошибка открытия порта {SERIAL_PORT}: {str(e)}")
        return False

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "✨ *RGB LED Control Bot* ✨\n\n"
        "Отправь команду в формате:\n"
        "`R100 G50 B255`\n\n"
        "Значения должны быть в диапазоне 0-255.\n"
        "Пример: `R255 G0 B128`"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# Основной обработчик команд цвета
async def handle_color_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ser
    
    # Проверка авторизации (опционально)
    if AUTHORIZED_CHAT_ID and update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("❌ У вас нет прав для управления этим устройством.")
        return

    message = update.message.text.strip()
    
    # Проверка формата команды
    pattern = r'^[Rr]\s*(\d{1,3})\s+[Gg]\s*(\d{1,3})\s+[Bb]\s*(\d{1,3})$'
    match = re.match(pattern, message)
    
    if not match:
        error_msg = (
            "⚠️ Неверный формат команды!\n\n"
            "Используйте формат: `Rxxx Gyyy Bzzz`\n"
            "Пример: `R255 G0 B128`"
        )
        await update.message.reply_text(error_msg, parse_mode='Markdown')
        return
    
    try:
        r = int(match.group(1))
        g = int(match.group(2))
        b = int(match.group(3))
        
        # Проверка диапазона значений
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("Значения должны быть в диапазоне 0-255")
            
    except ValueError as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return
    
    # Отправка команды на Arduino
    try:
        if not ser or not ser.is_open:
            if not await init_serial():
                raise Exception("Последовательный порт не доступен")
        
        # Формат команды: "R,G,B" (пример: "255,0,128")
        # command = f"{r},{g},{b}\n"
        command = f"R{r} G{g} B{b}\n"
        ser.write(command.encode())
        logging.info(f"Отправлено на Arduino: {command.strip()}")
        
        # Визуальная индикация (опционально)
        # color_preview = f"🔴`{r:03}` 🔵`{g:03}` 🟢`{b:03}`".replace('0', '·')
        color_preview = f"🔴`{str(r).lstrip('0') or '0'}` 🟢`{str(g).lstrip('0') or '0'}` 🔵`{str(b).lstrip('0') or '0'}`"

        success_msg = (
            "✅ Команда выполнена!\n"
            f"Установлен цвет:\n"
            f"{color_preview}\n\n"
            f"RGB({r}, {g}, {b})"
        )
        await update.message.reply_text(success_msg, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка отправки на Arduino: {str(e)}")
        await update.message.reply_text(
            "❌ Ошибка связи с устройством\n"
            "Проверьте:\n"
            "- Подключение Arduino\n"
            "- Правильность порта в настройках\n"
            "- Питание устройства"
        )

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Произошла ошибка: {context.error}")

# Закрытие соединения при завершении
async def shutdown():
    global ser
    if ser and ser.is_open:
        ser.close()
        logging.info("Последовательный порт закрыт")

if __name__ == '__main__':
    # Проверка критически важных настроек
    if not TELEGRAM_TOKEN:
        logging.error("Отсутствует TELEGRAM_BOT_TOKEN в .env файле!")
        exit(1)
    
    # Инициализация приложения
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_color_command))
    application.add_error_handler(error_handler)
    
    # Запуск бота
    try:
        logging.info("Бот запускается...")
        print("✅ Бот запущен! Нажмите Ctrl+C для остановки")
        
        # Попытка инициализации последовательного порта
        loop = asyncio.get_event_loop()
        if not loop.run_until_complete(init_serial()):
            print("⚠️ Не удалось подключиться к Arduino. Бот запущен в ограниченном режиме.")
        
        # Запуск polling
        application.run_polling()
        
    except KeyboardInterrupt:
        logging.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logging.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
    finally:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(shutdown())
        logging.info("Бот остановлен")
