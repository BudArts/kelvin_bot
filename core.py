import os
import logging
import sqlite3
from datetime import datetime
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext, CallbackQueryHandler
from gg_int import GigaChatIntegration
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла (только для локальной разработки)
if os.path.exists('.env'):
    load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
FIO, CLASS, CONSENT = range(3)

# Получаем токены из переменных окружения
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Проверяем наличие токенов
if not TOKEN:
    logger.error("BOT_TOKEN не установлен в переменных окружения!")
    exit(1)

if not ADMIN_ID:
    logger.error("ADMIN_ID не установлен в переменных окружения!")
    exit(1)

# Инициализируем GigaChat
GG = GigaChatIntegration()

class Database:
    def __init__(self):
        # Определяем путь к базе данных в зависимости от ОС
        if os.name == 'nt':  # Windows
            if not os.path.exists('data'):
                os.makedirs('data')
            db_path = os.path.join('data', 'bot_database.db')
        else:  # Linux/Unix (Render)
            db_path = '/tmp/bot_database.db'
        
        logger.info(f"Используется путь к БД: {db_path}")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                fio TEXT,
                class_name TEXT,
                consent_given BOOLEAN,
                consent_date TIMESTAMP,
                registration_date TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                request_text TEXT,
                response_text TEXT,
                request_time TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, chat_id, fio, class_name):
        self.cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, chat_id, fio, class_name, consent_given, consent_date, registration_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, chat_id, fio, class_name, False, None, datetime.now()))
        self.conn.commit()
    
    def update_consent(self, user_id, consent):
        self.cursor.execute('''
            UPDATE users 
            SET consent_given = ?, consent_date = ?
            WHERE user_id = ?
        ''', (consent, datetime.now() if consent else None, user_id))
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def user_has_consent(self, user_id):
        self.cursor.execute(
            'SELECT consent_given FROM users WHERE user_id = ?', 
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0] if result else False
    
    def add_request(self, user_id, chat_id, request_text, response_text):
        self.cursor.execute('''
            INSERT INTO requests (user_id, chat_id, request_text, response_text, request_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, chat_id, request_text, response_text, datetime.now()))
        self.conn.commit()
    
    def get_user_stats(self, user_id=None):
        if user_id:
            self.cursor.execute('''
                SELECT COUNT(*) FROM requests WHERE user_id = ?
            ''', (user_id,))
        else:
            self.cursor.execute('SELECT COUNT(*) FROM requests')
        return self.cursor.fetchone()[0]
    
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

# Инициализация базы данных
db = Database()

def require_registration(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        user = db.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "Пожалуйста, сначала зарегистрируйтесь.\n"
                "Используйте команду /start для начала регистрации."
            )
            return
        
        if not user[4]:
            await update.message.reply_text(
                "Пожалуйста, дайте согласие на обработку персональных данных.\n"
                "Используйте команду /start для продолжения."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user and user[4]:
        await update.message.reply_text(
            "Вы уже зарегистрированы! Отправьте мне ваш вопрос и я постараюсь помочь вам с ответом."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Добро пожаловать! Для использования бота необходимо зарегистрироваться.\n\n"
        "Введите ваше ФИО (Фамилия Имя Отчество):"
    )
    return FIO

async def get_fio(update: Update, context: CallbackContext) -> int:
    fio = update.message.text
    context.user_data['fio'] = fio
    
    await update.message.reply_text(
        "Введите ваш класс (например: 11А, 9Б):"
    )
    return CLASS

async def get_class(update: Update, context: CallbackContext) -> int:
    class_name = update.message.text
    context.user_data['class'] = class_name
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Согласен", callback_data='consent_yes'),
            InlineKeyboardButton("❌ Не согласен", callback_data='consent_no')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    consent_text = (
        "Для использования бота необходимо ваше согласие на обработку персональных данных.\n\n"
        "📝 Согласие на обработку персональных данных:\n"
        "• ФИО\n"
        "• Класс\n"
        "• ID чата\n"
        "• История запросов и время их отправки\n\n"
        "Данные собираются для улучшения работы бота и анализа запросов.\n"
        "Вы можете отозвать согласие в любой момент, обратившись к администратору.\n\n"
        "Вы согласны на обработку ваших персональных данных?"
    )
    
    await update.message.reply_text(consent_text, reply_markup=reply_markup)
    return CONSENT

async def consent_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if query.data == 'consent_yes':
        db.add_user(
            user_id=user_id,
            chat_id=chat_id,
            fio=context.user_data['fio'],
            class_name=context.user_data['class']
        )
        db.update_consent(user_id, True)
        
        await query.edit_message_text(
            "✅ Спасибо! Регистрация успешно завершена.\n\n"
            "Теперь вы можете отправлять запросы для обработки."
        )
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            "❌ Вы не дали согласие на обработку персональных данных.\n"
            "К сожалению, без этого использование бота невозможно.\n\n"
            "Если вы передумаете, нажмите /start для повторной регистрации."
        )
        return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Регистрация отменена. Если захотите зарегистрироваться позже, нажмите /start"
    )
    return ConversationHandler.END

@require_registration
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    await update.message.reply_text("🔄 Обрабатываю ваш запрос...")
    
    try:
        response = GG.get_response(user_message)
        db.add_request(user_id, chat_id, user_message, response)
        await update.message.reply_text(f"📝 Результат:\n\n{response}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
        )

async def stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет прав для просмотра статистики.")
        return
    
    db.cursor.execute('SELECT COUNT(*) FROM users')
    users_count = db.cursor.fetchone()[0]
    
    db.cursor.execute('SELECT COUNT(*) FROM requests')
    total_requests = db.cursor.fetchone()[0]
    
    db.cursor.execute('''
        SELECT COUNT(*) FROM requests 
        WHERE DATE(request_time) = DATE('now')
    ''')
    today_requests = db.cursor.fetchone()[0]
    
    stats_text = (
        f"📊 **Статистика бота:**\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"📝 Всего запросов: {total_requests}\n"
        f"📅 Запросов сегодня: {today_requests}"
    )
    
    await update.message.reply_text(stats_text)

async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "🤖 Доступные команды:\n\n"
        "/start - Начать регистрацию\n"
        "/help - Показать это сообщение\n"
        "После регистрации просто отправьте мне ваш запрос, и я обработаю его с помощью нейросети."
    )
    await update.message.reply_text(help_text)

def main():
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fio)],
            CLASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class)],
            CONSENT: [CallbackQueryHandler(consent_callback)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()