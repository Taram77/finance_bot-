import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dataclasses import dataclass
import sqlite3
from datetime import datetime, time
from typing import List, Tuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация бота
TOKEN = "8071536575:AAFgurEmQuAI3AMALnmbWM7lzODdojvQ4q8"  # Замените на свой токен

# База данных
class Database:
    def __init__(self, db_file):
        self.db_file = db_file

    def create_tables(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            # Удаляем старые таблицы, если они существуют
            cur.execute('DROP TABLE IF EXISTS transactions')
            cur.execute('DROP TABLE IF EXISTS groups')
            cur.execute('DROP TABLE IF EXISTS notification_settings')
            
            # Создаем таблицы заново
            cur.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                joined_date TIMESTAMP
            )''')

            cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                amount REAL,
                type TEXT,
                timestamp TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
            )''')

            cur.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                chat_id INTEGER PRIMARY KEY,
                notification_time TIME,
                notification_day INTEGER
            )''')
            
            conn.commit()
            conn.close()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            if conn:
                conn.close()

    async def add_group(self, chat_id: int, title: str):
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute('''
            INSERT OR REPLACE INTO groups (chat_id, title, joined_date)
            VALUES (?, ?, ?)
            ''', (chat_id, title, datetime.now()))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error adding group: {e}")
            if conn:
                conn.close()
            return False

    async def save_transaction(self, chat_id: int, amount: float, type: str, user_id: int = None, username: str = None):
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            # Проверяем существование группы
            cur.execute('SELECT chat_id FROM groups WHERE chat_id = ?', (chat_id,))
            if not cur.fetchone():
                cur.execute(
                    'INSERT INTO groups (chat_id, joined_date) VALUES (?, ?)',
                    (chat_id, datetime.now())
                )
            
            # Сохраняем транзакцию
            cur.execute('''
            INSERT INTO transactions (chat_id, user_id, username, amount, type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, float(amount), type, datetime.now()))
            
            conn.commit()
            conn.close()
            logging.info(f"Transaction saved: chat_id={chat_id}, amount={amount}, type={type}")
            return True
        except Exception as e:
            logging.error(f"Error saving transaction: {e}")
            if conn:
                conn.close()
            return False

    async def get_balance(self, chat_id: int) -> float:
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute('''
            SELECT 
                COALESCE(
                    SUM(CASE 
                        WHEN type = 'deposit' THEN amount 
                        WHEN type = 'withdrawal' THEN -amount 
                        ELSE 0 
                    END),
                    0
                ) as balance
            FROM transactions 
            WHERE chat_id = ?
            ''', (chat_id,))
            
            result = cur.fetchone()
            balance = float(result[0]) if result else 0.0
            
            conn.close()
            return balance
        except Exception as e:
            logging.error(f"Error getting balance: {e}")
            if conn:
                conn.close()
            return 0.0

    async def get_transactions_history(self, chat_id: int) -> List[Tuple]:
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute('''
            SELECT 
                datetime(timestamp, 'localtime') as local_time,
                type,
                amount,
                username
            FROM transactions
            WHERE chat_id = ?
            ORDER BY timestamp DESC
            LIMIT 50
            ''', (chat_id,))
            
            history = cur.fetchall()
            conn.close()
            return history
        except Exception as e:
            logging.error(f"Error getting history: {e}")
            if conn:
                conn.close()
            return []

    async def save_notification_settings(self, chat_id: int, time_str: str = None, day: int = None):
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            if time_str:
                cur.execute('''
                INSERT OR REPLACE INTO notification_settings (chat_id, notification_time)
                VALUES (?, ?)
                ''', (chat_id, time_str))
            
            if day:
                cur.execute('''
                INSERT OR REPLACE INTO notification_settings (chat_id, notification_day)
                VALUES (?, ?)
                ''', (chat_id, day))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error saving notification settings: {e}")
            if conn:
                conn.close()
            return False

    async def get_notification_settings(self, chat_id: int) -> Tuple[str, int]:
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute('''
            SELECT notification_time, notification_day
            FROM notification_settings
            WHERE chat_id = ?
            ''', (chat_id,))
            
            result = cur.fetchone()
            conn.close()
            
            if result:
                return result
            return None, None
        except Exception as e:
            logging.error(f"Error getting notification settings: {e}")
            if conn:
                conn.close()
            return None, None

    async def get_all_notification_settings(self) -> List[Tuple]:
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute('''
            SELECT chat_id, notification_time, notification_day
            FROM notification_settings
            WHERE notification_time IS NOT NULL AND notification_day IS NOT NULL
            ''')
            
            settings = cur.fetchall()
            conn.close()
            return settings
        except Exception as e:
            logging.error(f"Error getting all notification settings: {e}")
            if conn:
                conn.close()
            return []
# Вспомогательные функции
async def is_group_admin(message: types.Message) -> bool:
    """Проверка, является ли пользователь администратором группы"""
    try:
        if message.chat.type in ['group', 'supergroup']:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.is_chat_admin()
    except Exception as e:
        logging.error(f"Error checking admin rights: {e}")
    return False

async def check_group(message: types.Message) -> bool:
    """Проверка, является ли чат группой"""
    return message.chat.type in ['group', 'supergroup']

# Состояния FSM
class PaymentState(StatesGroup):
    WAITING_FOR_AMOUNT = State()
    CONFIRMING = State()

class WithdrawalState(StatesGroup):
    WAITING_FOR_AMOUNT = State()
    CONFIRMING = State()

class SettingsState(StatesGroup):
    WAITING_FOR_NOTIFICATION_TIME = State()
    WAITING_FOR_NOTIFICATION_DAY = State()

# Клавиатуры
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("💰 Я оплатил"))
    keyboard.add(types.KeyboardButton("📊 Баланс"), types.KeyboardButton("📝 История"))
    keyboard.add(types.KeyboardButton("💸 Списать"), types.KeyboardButton("⚙️ Настройки"))
    return keyboard

def get_cancel_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("❌ Отмена"))
    return keyboard

def get_confirm_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("✅ Подтвердить"), types.KeyboardButton("❌ Отмена"))
    return keyboard

def get_settings_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("⏰ Время уведомлений"))
    keyboard.add(types.KeyboardButton("📅 День уведомлений"))
    keyboard.add(types.KeyboardButton("↩️ Назад в меню"))
    return keyboard

# Инициализация бота и базы данных
bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database("finance_bot.db")
scheduler = AsyncIOScheduler()

# Функция отправки уведомлений
async def send_notification(chat_id: int):
    try:
        balance = await db.get_balance(chat_id)
        await bot.send_message(
            chat_id,
            f"🔔 Напоминание о внесении платежа!\n"
            f"💰 Текущий баланс группы: {balance:.2f} руб."
        )
    except Exception as e:
        logging.error(f"Error sending notification to {chat_id}: {e}")

# Обработчики команд
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer(
                "❌ Этот бот предназначен для работы в группах.\n"
                "Пожалуйста, добавьте его в групповой чат."
            )
            return

        await db.add_group(
            message.chat.id,
            message.chat.title
        )
        
        await message.answer(
            "👋 Бот для учета финансов ДПП успешно добавлен в группу!\n\n"
            "🔹 Используйте кнопку 'Я оплатил' для внесения платежа\n"
            "🔹 'Баланс' покажет текущий остаток\n"
            "🔹 'История' отобразит все операции\n"
            "🔹 'Списать' для списания средств (только админы)\n"
            "🔹 'Настройки' для установки уведомлений (только админы)\n\n"
            "⚠️ Настраивать уведомления и списывать средства могут только администраторы группы",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in start command: {e}")
        await message.answer("❌ Произошла ошибка при запуске бота")

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = """
📌 Доступные команды:
/start - Начать работу с ботом
/help - Показать это сообщение
/pay - Внести платеж
/withdraw - Списать средства (только админы)
/balance - Показать баланс
/history - История операций
/settings - Настройки уведомлений (только админы)
/status - Проверить статус бота

💡 Советы:
- Используйте кнопки меню для удобной навигации
- В настройках можно установить день и время ежемесячных уведомлений
- При внесении платежа указывайте сумму числом
- История транзакций показывает, кто и когда вносил средства
    """
    await message.answer(help_text, reply_markup=get_main_keyboard())

@dp.message_handler(commands=['status'])
async def cmd_status(message: types.Message):
    try:
        # Проверяем подключение к БД
        conn = sqlite3.connect("finance_bot.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        trans_count = cur.fetchone()[0]
        conn.close()
        
        # Проверяем права бота
        bot_member = await message.chat.get_member(bot.id)
        
        status_text = (
            "📊 Статус бота:\n\n"
            f"✅ Бот активен\n"
            f"✅ База данных доступна\n"
            f"📝 Количество транзакций: {trans_count}\n"
            f"👤 Права бота: {'Администратор' if bot_member.is_chat_admin() else 'Участник'}\n"
        )
        
        await message.reply(status_text)
    except Exception as e:
        logging.error(f"Status check error: {e}")
        await message.reply("❌ Ошибка при проверке статуса бота")

@dp.message_handler(commands=['reset_db'])
async def cmd_reset_db(message: types.Message):
    try:
        if not await is_group_admin(message):
            await message.answer("❌ Только администраторы могут использовать эту команду!")
            return
            
        db.create_tables()
        await message.answer("✅ База данных успешно пересоздана")
    except Exception as e:
        logging.error(f"Error resetting database: {e}")
        await message.answer("❌ Ошибка при сбросе базы данных")

@dp.message_handler(commands=['pay'])
@dp.message_handler(text="💰 Я оплатил")
async def cmd_pay(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer("❌ Бот работает только в группах!")
            return

        await PaymentState.WAITING_FOR_AMOUNT.set()
        await message.answer(
            "Введите сумму платежа:",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in pay command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@dp.message_handler(state=PaymentState.WAITING_FOR_AMOUNT)
async def process_payment_amount(message: types.Message, state: FSMContext):
    try:
        if message.text == "❌ Отмена":
            await state.finish()
            await message.answer(
                "Операция отменена",
                reply_markup=get_main_keyboard()
            )
            return

        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("Сумма должна быть положительной. Попробуйте снова:")
            return

        await state.update_data(amount=amount)
        await PaymentState.CONFIRMING.set()
        await message.answer(
            f"Подтвердите внесение {amount:.2f} руб.",
            reply_markup=get_confirm_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректную сумму (например: 100 или 100.50)"
        )
    except Exception as e:
        logging.error(f"Error processing payment amount: {e}")
        await state.finish()
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

@dp.message_handler(state=PaymentState.CONFIRMING)
async def process_payment_confirm(message: types.Message, state: FSMContext):
    try:
        if message.text == "✅ Подтвердить":
            data = await state.get_data()
            amount = data['amount']
            
            # Сохраняем информацию о платеже
            success = await db.save_transaction(
                message.chat.id,
                amount,
                "deposit",
                message.from_user.id,
                message.from_user.full_name
            )
            
            if success:
                balance = await db.get_balance(message.chat.id)
                await message.answer(
                    f"✅ Платеж на сумму {amount:.2f} руб. внесен!\n"
                    f"👤 Внес: {message.from_user.full_name}\n"
                    f"💰 Текущий баланс группы: {balance:.2f} руб.",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.answer(
                    "❌ Ошибка при сохранении платежа. Попробуйте позже.",
                    reply_markup=get_main_keyboard()
                )
        else:
            await message.answer(
                "Операция отменена",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logging.error(f"Error confirming payment: {e}")
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    finally:
        await state.finish()

@dp.message_handler(commands=['withdraw'])
@dp.message_handler(text="💸 Списать")
async def cmd_withdraw(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer("❌ Бот работает только в группах!")
            return

        if not await is_group_admin(message):
            await message.answer("❌ Только администраторы группы могут списывать средства!")
            return

        await WithdrawalState.WAITING_FOR_AMOUNT.set()
        await message.answer(
            "Введите сумму списания:",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in withdraw command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@dp.message_handler(state=WithdrawalState.WAITING_FOR_AMOUNT)
async def process_withdrawal_amount(message: types.Message, state: FSMContext):
    try:
        if message.text == "❌ Отмена":
            await state.finish()
            await message.answer(
                "Операция отменена",
                reply_markup=get_main_keyboard()
            )
            return

        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("Сумма должна быть положительной. Попробуйте снова:")
            return

        current_balance = await db.get_balance(message.chat.id)
        if amount > current_balance:
            await message.answer(
                f"❌ Недостаточно средств. Доступно: {current_balance:.2f} руб.",
                reply_markup=get_main_keyboard()
            )
            await state.finish()
            return

        await state.update_data(amount=amount)
        await WithdrawalState.CONFIRMING.set()
        await message.answer(
            f"Подтвердите списание {amount:.2f} руб.",
            reply_markup=get_confirm_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректную сумму (например: 100 или 100.50)"
        )
    except Exception as e:
        logging.error(f"Error processing withdrawal amount: {e}")
        await state.finish()
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

@dp.message_handler(state=WithdrawalState.CONFIRMING)
async def process_withdrawal_confirm(message: types.Message, state: FSMContext):
    try:
        if message.text == "✅ Подтвердить":
            data = await state.get_data()
            amount = data['amount']
            
            success = await db.save_transaction(
                message.chat.id,
                amount,
                "withdrawal",
                message.from_user.id,
                message.from_user.full_name
            )
            
            if success:
                balance = await db.get_balance(message.chat.id)
                await message.answer(
                    f"✅ Списание на сумму {amount:.2f} руб. выполнено!\n"
                    f"👤 Выполнил: {message.from_user.full_name}\n"
                    f"💰 Текущий баланс группы: {balance:.2f} руб.",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.answer(
                    "❌ Ошибка при выполнении списания. Попробуйте позже.",
                    reply_markup=get_main_keyboard()
                )
        else:
            await message.answer(
                "Операция отменена",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logging.error(f"Error confirming withdrawal: {e}")
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    finally:
        await state.finish()

@dp.message_handler(commands=['balance'])
@dp.message_handler(text="📊 Баланс")
async def cmd_balance(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer("❌ Бот работает только в группах!")
            return

        balance = await db.get_balance(message.chat.id)
        await message.answer(
            f"💰 Текущий баланс группы: {balance:.2f} руб.",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in balance command: {e}")
        await message.answer(
            "❌ Ошибка при получении баланса. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
@dp.message_handler(commands=['history'])
@dp.message_handler(text="📝 История")
async def cmd_history(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer("❌ Бот работает только в группах!")
            return

        history = await db.get_transactions_history(message.chat.id)
        
        if not history:
            await message.answer(
                "📝 История транзакций пуста",
                reply_markup=get_main_keyboard()
            )
            return

        text = "📝 История последних транзакций:\n\n"
        for timestamp, type, amount, username in history:
            operation = "➕ Пополнение" if type == "deposit" else "➖ Списание"
            user_info = f" от {username}" if username else ""
            text += f"{timestamp}: {operation}{user_info} на {amount:.2f} руб.\n"

        # Разбиваем длинное сообщение на части
        if len(text) > 4096:
            for x in range(0, len(text), 4096):
                await message.answer(text[x:x+4096])
        else:
            await message.answer(text, reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"Error in history command: {e}")
        await message.answer(
            "❌ Ошибка при получении истории. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

@dp.message_handler(commands=['settings'])
@dp.message_handler(text="⚙️ Настройки")
async def cmd_settings(message: types.Message):
    try:
        if not await check_group(message):
            await message.answer("❌ Бот работает только в группах!")
            return

        if not await is_group_admin(message):
            await message.answer("❌ Только администраторы группы могут менять настройки!")
            return

        time_str, day = await db.get_notification_settings(message.chat.id)
        settings_text = "⚙️ Текущие настройки уведомлений:\n\n"
        
        if time_str and day:
            settings_text += f"🕒 Время: {time_str}\n📅 День: {day}\n\n"
        else:
            settings_text += "Уведомления не настроены\n\n"
        
        settings_text += "Выберите, что хотите настроить:"
        
        await message.answer(settings_text, reply_markup=get_settings_keyboard())
    except Exception as e:
        logging.error(f"Error in settings command: {e}")
        await message.answer(
            "❌ Ошибка при получении настроек. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

@dp.message_handler(text="⏰ Время уведомлений")
async def cmd_set_notification_time(message: types.Message):
    try:
        if not await is_group_admin(message):
            await message.answer("❌ Только администраторы группы могут менять настройки!")
            return

        await SettingsState.WAITING_FOR_NOTIFICATION_TIME.set()
        await message.answer(
            "Введите время для уведомлений в формате ЧЧ:ММ (например, 10:00)",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logging.error(f"Error setting notification time: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@dp.message_handler(text="📅 День уведомлений")
async def cmd_set_notification_day(message: types.Message):
    try:
        if not await is_group_admin(message):
            await message.answer("❌ Только администраторы группы могут менять настройки!")
            return

        await SettingsState.WAITING_FOR_NOTIFICATION_DAY.set()
        await message.answer(
            "Введите день месяца для уведомлений (1-31)",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logging.error(f"Error setting notification day: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@dp.message_handler(text="↩️ Назад в меню")
async def cmd_back_to_menu(message: types.Message):
    await message.answer(
        "Вы вернулись в главное меню",
        reply_markup=get_main_keyboard()
    )

@dp.message_handler(state=SettingsState.WAITING_FOR_NOTIFICATION_TIME)
async def process_notification_time(message: types.Message, state: FSMContext):
    try:
        if message.text == "❌ Отмена":
            await state.finish()
            await message.answer(
                "Настройка времени отменена",
                reply_markup=get_settings_keyboard()
            )
            return

        # Проверяем формат времени
        hours, minutes = map(int, message.text.split(':'))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError
        
        await db.save_notification_settings(message.chat.id, time_str=message.text)
        await setup_notifications()
        
        await state.finish()
        await message.answer(
            f"✅ Время уведомлений установлено на {message.text}",
            reply_markup=get_settings_keyboard()
        )
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат времени. Пожалуйста, используйте формат ЧЧ:ММ (например, 10:00)"
        )
    except Exception as e:
        logging.error(f"Error processing notification time: {e}")
        await state.finish()
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_settings_keyboard()
        )

@dp.message_handler(state=SettingsState.WAITING_FOR_NOTIFICATION_DAY)
async def process_notification_day(message: types.Message, state: FSMContext):
    try:
        if message.text == "❌ Отмена":
            await state.finish()
            await message.answer(
                "Настройка дня отменена",
                reply_markup=get_settings_keyboard()
            )
            return

        day = int(message.text)
        if not (1 <= day <= 31):
            raise ValueError
        
        await db.save_notification_settings(message.chat.id, day=day)
        await setup_notifications()
        
        await state.finish()
        await message.answer(
            f"✅ День уведомлений установлен на {day} число каждого месяца",
            reply_markup=get_settings_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число от 1 до 31"
        )
    except Exception as e:
        logging.error(f"Error processing notification day: {e}")
        await state.finish()
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_settings_keyboard()
        )

async def setup_notifications():
    try:
        # Очищаем все существующие задачи
        scheduler.remove_all_jobs()
        
        # Получаем все настройки уведомлений
        settings = await db.get_all_notification_settings()
        
        # Создаем новые задачи для каждой группы
        for chat_id, time_str, day in settings:
            if time_str and day:
                hours, minutes = map(int, time_str.split(':'))
                scheduler.add_job(
                    send_notification,
                    trigger=CronTrigger(
                        day=day,
                        hour=hours,
                        minute=minutes
                    ),
                    args=[chat_id],
                    id=f"notification_{chat_id}"
                )
        logging.info("Notifications setup completed")
    except Exception as e:
        logging.error(f"Error setting up notifications: {e}")

async def on_startup(_):
    try:
        # Проверяем базу данных
        db.create_tables()
        
        # Настраиваем уведомления
        await setup_notifications()
        
        # Запускаем планировщик
        scheduler.start()
        
        logging.info("Bot started successfully")
    except Exception as e:
        logging.error(f"Startup error: {e}")
        raise e

# Обработчик ошибок
@dp.errors_handler()
async def errors_handler(update: types.Update, exception: Exception):
    try:
        logging.error(f"Exception: {exception}")
        logging.error(f"Update: {update}")
        
        if update.message:
            await update.message.answer(
                "❌ Произошла ошибка при обработке команды.\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
    except Exception as e:
        logging.error(f"Error in error handler: {e}")
    return True

if __name__ == '__main__':
    # Настройка для Windows
    try:
        if sys.platform.startswith('win'):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception as e:
        logging.error(f"Error setting event loop policy: {e}")
    
    # Запускаем бота
    executor.start_polling(
        dp,
        on_startup=on_startup,
        skip_updates=True
    )
