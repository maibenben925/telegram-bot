import logging
import os
import re
import serial
import asyncio
import time
from collections import deque
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SERIAL_PORT = 'COM4'  # <--- ПРОВЕРЬ ПОРТ
# SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 9600
AUTHORIZED_CHAT_ID = int(os.getenv("AUTHORIZED_CHAT_ID", 0))

ser = None

# --- 1. Настройка Красивых и Безопасных Логов ---

class SafeLogFormatter(logging.Formatter):
    def format(self, record):
        original_msg = super().format(record)
        
        # СКРЫВАЕМ ТОКЕН (Заменяем на звездочки)
        if TELEGRAM_TOKEN in original_msg:
            original_msg = original_msg.replace(TELEGRAM_TOKEN, "******")
            
        # Добавляем красоту (Эмодзи) в начало сообщения
        if "Arduino ->" in original_msg:
            return f"📤 {original_msg}" # Исходящие
        elif "LOG:" in original_msg:
            return f"🤖 {original_msg}" # Сообщения от Ардуино
        elif "User:" in original_msg:
            return f"👤 {original_msg}" # Действия пользователя
        elif "ERROR" in original_msg:
            return f"❌ {original_msg}"
        
        return original_msg

class BufferLogHandler(logging.Handler):
    """Хранит последние записи в памяти"""
    def __init__(self, capacity=50):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        try:
            msg = self.format(record)
            # Сохраняем время и сообщение
            self.buffer.append((time.time(), msg))
        except Exception:
            self.handleError(record)

# Настройка логгера
formatter = SafeLogFormatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
memory_handler = BufferLogHandler()
memory_handler.setFormatter(formatter)

# Обычный консольный вывод тоже делаем красивым
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, memory_handler]
)
logger = logging.getLogger(__name__)

# --- 2. Работа с Serial ---

async def init_serial():
    global ser
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) # timeout важен для чтения
        logger.info(f"Порт {SERIAL_PORT} открыт успешно")
        return True
    except serial.SerialException as e:
        logger.error(f"Ошибка порта: {str(e)}")
        return False

async def shutdown():
    if ser and ser.is_open: ser.close()

# --- 3. ФОНОВАЯ ЗАДАЧА: Слушаем Ардуино ---
async def listen_to_arduino():
    """Постоянно читает данные от Arduino в фоне"""
    global ser
    logger.info("Запущен слушатель Arduino...")
    while True:
        try:
            if ser and ser.is_open and ser.in_waiting > 0:
                # Читаем строку от Arduino
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                # Если это наш лог (начинается с LOG:), сохраняем в память
                if line.startswith("LOG:"):
                    logger.info(f"{line}")  # Это попадет в BufferLogHandler
                
            await asyncio.sleep(0.1) # Не грузим процессор
        except Exception as e:
            logger.error(f"Ошибка чтения Serial: {e}")
            await asyncio.sleep(1)

# --- 4. Логика Бота ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["R255 G0 B0", "R0 G255 B0", "R0 G0 B255"],
        ["L0", "L128", "L255"],
        ["📄 Логи (30сек)"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🎮 *Пульт готов!* Жми кнопки.", 
        reply_markup=markup, 
        parse_mode='Markdown'
    )

async def send_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Фильтр прав
    if AUTHORIZED_CHAT_ID and update.effective_chat.id != AUTHORIZED_CHAT_ID:
        return

    now = time.time()
    cutoff = now - 30 # Последние 30 секунд
    
    # Берем логи из памяти
    recent_logs = [msg for t, msg in memory_handler.buffer if t >= cutoff]

    if not recent_logs:
        await update.message.reply_text("📭 Тишина в эфире (нет логов за 30с).")
        return

    log_text = "\n".join(recent_logs)
    
    # Отправляем (обрезаем если слишком длинно)
    if len(log_text) > 4000: log_text = log_text[-4000:]
    
    await update.message.reply_text(f"📄 *Последние события:*\n```\n{log_text}\n```", parse_mode='Markdown')

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ser
    text = update.message.text
    
    if text == "📄 Логи (30сек)":
        await send_logs(update, context)
        return

    # Логируем действие пользователя
    logger.info(f"User: {text}")

    message = text.strip().upper()
    
    # Парсинг команд
    rgb_match = re.match(r'^R\s*(\d+)\s+G\s*(\d+)\s+B\s*(\d+)$', message)
    l_match = re.match(r'^L\s*(\d+)$', message)

    try:
        cmd = ""
        reply = ""
        
        if rgb_match:
            r, g, b = map(int, rgb_match.groups())
            if not (0<=r<=255 and 0<=g<=255 and 0<=b<=255): raise ValueError
            cmd = f"R{r} G{g} B{b}\n"
            reply = f"Установил RGB: {r},{g},{b}"
            
        elif l_match:
            val = int(l_match.group(1))
            if not (0<=val<=255): raise ValueError
            cmd = f"L{val}\n"
            reply = f"Установил Яркость: {val}"
            
        else:
            await update.message.reply_text("⚠️ Не понял команду.")
            return

        if ser and ser.is_open:
            ser.write(cmd.encode())
            logger.info(f"Arduino -> {cmd.strip()}") # Логируем отправку
            await update.message.reply_text(f"✅ {reply}")
        else:
            await update.message.reply_text("❌ Нет соединения с Arduino")

    except ValueError:
        await update.message.reply_text("❌ Числа должны быть от 0 до 255")

# --- 5. Запуск ---

async def post_init(application: ApplicationBuilder):
    """Запускается сразу после старта бота"""
    # Запускаем задачу слушания Serial в фоне
    asyncio.create_task(listen_to_arduino())

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit("Нет токена!")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", send_logs))
    app.add_handler(MessageHandler(filters.TEXT, handle_command))
    
    loop = asyncio.get_event_loop()
    
    # Инициализация порта перед запуском
    if loop.run_until_complete(init_serial()):
        print("✅ Бот запущен. Нажми Ctrl+C для выхода.")
        app.run_polling()
    else:
        print("❌ Ошибка старта: не удалось открыть COM порт.")
    
    loop.run_until_complete(shutdown())
