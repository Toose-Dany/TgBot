import logging
import sqlite3
import requests
import schedule
import time
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
GGSELL_API_KEY = "YOUR_GGSELL_API_KEY"

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('ggsell_monitor.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_name TEXT,
            product_url TEXT,
            product_id TEXT,
            target_price REAL,
            current_price REAL,
            last_check TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            price REAL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Регистрация пользователя
def register_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect('ggsell_monitor.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

# Получение информации о товаре с GGSell
def get_ggsell_product_info(product_url):
    """
    Функция для получения информации о товаре с GGSell
    """
    try:
        # Извлекаем ID товара из URL
        product_id = extract_product_id_from_url(product_url)
        
        if not product_id:
            return None
        
        # Здесь должен быть запрос к API GGSell
        # Пример структуры API запроса (замените на реальный эндпоинт)
        headers = {
            'Authorization': f'Bearer {GGSELL_API_KEY}',
            'User-Agent': 'PriceMonitorBot/1.0'
        }
        
        # Предполагаемый формат API GGSell (нужно уточнить у разработчиков)
        api_url = f"https://api.ggsell.com/v1/products/{product_id}"
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            return {
                'name': data.get('name', 'Неизвестный товар'),
                'price': float(data.get('price', 0)),
                'original_price': float(data.get('original_price', 0)),
                'discount': data.get('discount', 0),
                'available': data.get('in_stock', False),
                'rating': data.get('rating', 0),
                'image_url': data.get('image', ''),
                'category': data.get('category', '')
            }
        else:
            # Если API недоступно, используем парсинг страницы
            return parse_ggsell_page(product_url)
            
    except Exception as e:
        logger.error(f"Ошибка получения информации о товаре с GGSell: {e}")
        return None

def extract_product_id_from_url(url):
    """
    Извлекает ID товара из URL GGSell
    Примеры URL:
    - https://ggsell.ru/product/12345
    - https://ggsell.com/game/abc-def-123
    """
    try:
        # Убираем параметры запроса
        url = url.split('?')[0]
        
        # Разделяем URL по слешам
        parts = url.rstrip('/').split('/')
        
        # ID товара обычно последняя часть URL
        product_id = parts[-1]
        
        return product_id if product_id else None
    except Exception as e:
        logger.error(f"Ошибка извлечения ID из URL: {e}")
        return None

def parse_ggsell_page(url):
    """
    Парсинг страницы товара GGSell (запасной метод)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Здесь нужно добавить парсинг конкретных элементов страницы
            # Это пример - нужно адаптировать под реальную структуру GGSell
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Пример поиска элементов (нужно уточнить селекторы)
            name_elem = soup.find('h1') or soup.find('title')
            price_elem = soup.find('span', class_='price') or soup.find('meta', itemprop='price')
            
            name = name_elem.get_text().strip() if name_elem else 'Товар GGSell'
            
            # Извлекаем цену
            price = 0
            if price_elem:
                price_text = price_elem.get('content') or price_elem.get_text()
                # Убираем все нечисловые символы кроме точки
                import re
                price_match = re.search(r'(\d+[.,]?\d*)', price_text)
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))
            
            return {
                'name': name,
                'price': price,
                'available': True,
                'rating': 0
            }
        else:
            return None
            
    except Exception as e:
        logger.error(f"Ошибка парсинга страницы GGSell: {e}")
        return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""
🎮 Привет, {user.first_name}!

Я бот для мониторинга цен на GGSell - магазине игр и софта.

📊 Возможности:
• Отслеживание цен на игры и программы
• Уведомления при изменении цены
• Слежение за скидками
• История цен
• Настройка целевой цены

📝 Команды:
/start - Начало работы
/add_product - Добавить товар для отслеживания
/my_products - Мои товары
/check_prices - Проверить цены сейчас
/help - Помощь

🎯 Добавьте первую игру командой /add_product
    """
    
    await update.message.reply_text(welcome_text)

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 Доступные команды:

/add_product - Добавить товар для отслеживания
/my_products - Показать мои товары
/check_prices - Проверить цены сейчас
/settings - Настройки уведомлений
/help - Эта справка

🔍 Как добавить товар:
1. Найти игру/программу на GGSell
2. Скопировать ссылку на товар
3. Использовать команду /add_product
4. Вставить ссылку и указать желаемую цену

🕐 Бот проверяет цены каждые 4 часа и уведомит вас, когда цена достигнет целевой.

🎮 Поддерживаемые товары:
• Игры для PC, PlayStation, Xbox
• Игровые ключи
• Программное обеспечение
• Подписки
    """
    await update.message.reply_text(help_text)

# Команда /add_product
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 Пришлите мне ссылку на товар с GGSell\n\n"
        "Примеры:\n"
        "• https://ggsell.ru/product/cyberpunk-2077\n"
        "• https://ggsell.com/game/gta-v-premium\n"
        "• https://ggsell.ru/software/windows-11-pro"
    )
    context.user_data['awaiting_url'] = True

# Обработка сообщений с ссылками
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_url'):
        url = update.message.text
        
        if 'ggsell' not in url:
            await update.message.reply_text("❌ Это не ссылка на GGSell. Попробуйте еще раз.")
            return
        
        # Проверяем доступность товара
        await update.message.reply_text("🔍 Проверяю товар...")
        
        product_info = get_ggsell_product_info(url)
        
        if not product_info:
            await update.message.reply_text(
                "❌ Не удалось получить информацию о товаре.\n"
                "Проверьте ссылку или попробуйте позже."
            )
            context.user_data.clear()
            return
        
        # Сохраняем информацию и запрашиваем целевую цену
        context.user_data['product_url'] = url
        context.user_data['product_info'] = product_info
        context.user_data['awaiting_url'] = False
        context.user_data['awaiting_price'] = True
        
        discount_text = ""
        if product_info.get('original_price') and product_info['original_price'] > product_info['price']:
            discount = ((product_info['original_price'] - product_info['price']) / product_info['original_price']) * 100
            discount_text = f"\n🏷️ Скидка: {discount:.0f}% (было {product_info['original_price']} руб.)"
        
        availability = "✅ В наличии" if product_info.get('available', True) else "❌ Нет в наличии"
        
        await update.message.reply_text(
            f"📦 Название: {product_info['name']}\n"
            f"💰 Текущая цена: {product_info['price']} руб.{discount_text}\n"
            f"📊 {availability}\n\n"
            f"🎯 Укажите целевую цену (в рублях):\n"
            f"Пример: 500 или 1499.99"
        )

# Обработка целевой цены
async def handle_target_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_price'):
        try:
            target_price = float(update.message.text)
            
            if target_price <= 0:
                await update.message.reply_text("❌ Цена должна быть положительным числом. Попробуйте еще раз.")
                return
            
            product_info = context.user_data['product_info']
            product_url = context.user_data['product_url']
            
            # Сохраняем товар в базу данных
            conn = sqlite3.connect('ggsell_monitor.db')
            cursor = conn.cursor()
            
            product_id = extract_product_id_from_url(product_url)
            
            cursor.execute('''
                INSERT INTO products (user_id, product_name, product_url, product_id, target_price, current_price, last_check)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                update.effective_user.id,
                product_info['name'],
                product_url,
                product_id,
                target_price,
                product_info['price'],
                datetime.now()
            ))
            
            conn.commit()
            conn.close()
            
            # Очищаем временные данные
            context.user_data.clear()
            
            await update.message.reply_text(
                f"✅ Товар успешно добавлен для отслеживания!\n\n"
                f"🎮 {product_info['name']}\n"
                f"💰 Текущая цена: {product_info['price']} руб.\n"
                f"🎯 Целевая цена: {target_price} руб.\n\n"
                f"📊 Бот будет уведомлять вас при изменении цены.\n"
                f"Следующая проверка через 4 часа."
            )
            
        except ValueError:
            await update.message.reply_text("❌ Неверный формат цены. Введите число (например: 500 или 1499.99)")

# Команда /my_products
async def my_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('ggsell_monitor.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, product_name, product_url, target_price, current_price, last_check
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
        ORDER BY last_check DESC
    ''', (user_id,))
    
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await update.message.reply_text(
            "📭 У вас нет отслеживаемых товаров.\n"
            "Используйте /add_product чтобы добавить игру или программу."
        )
        return
    
    message = "🎮 Ваши отслеживаемые товары:\n\n"
    
    for product in products:
        product_id, name, url, target_price, current_price, last_check = product
        
        status = "🎉 Цена достигнута!" if current_price <= target_price else "⏳ Ожидание"
        price_diff = current_price - target_price
        
        message += f"🆔 ID: {product_id}\n"
        message += f"🎮 {name}\n"
        message += f"💰 Текущая: {current_price} руб.\n"
        message += f"🎯 Целевая: {target_price} руб.\n"
        
        if current_price > target_price:
            message += f"📈 Осталось: {price_diff:.0f} руб.\n"
        
        message += f"📅 Последняя проверка: {last_check}\n"
        message += f"📊 Статус: {status}\n"
        message += "─" * 30 + "\n"
    
    # Добавляем кнопки управления
    keyboard = [
        [InlineKeyboardButton("🔄 Проверить цены сейчас", callback_data="check_prices")],
        [InlineKeyboardButton("❌ Удалить товар", callback_data="delete_product")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup)

# Команда /check_prices
async def check_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Проверяю актуальные цены...")
    await check_user_prices(user_id, context)
    await update.message.reply_text("✅ Цены обновлены!")

# Обработка callback запросов
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "check_prices":
        await query.edit_message_text("🔍 Проверяю цены...")
        await check_user_prices(user_id, context)
        await query.edit_message_text("✅ Цены проверены и обновлены!")
    
    elif data == "delete_product":
        await query.edit_message_text("Введите ID товара для удаления:")
        context.user_data['awaiting_delete_id'] = True
    
    elif data == "stats":
        await show_stats(query, user_id)

# Показать статистику
async def show_stats(query, user_id):
    conn = sqlite3.connect('ggsell_monitor.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*), 
               SUM(CASE WHEN current_price <= target_price THEN 1 ELSE 0 END)
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))
    
    total, reached = cursor.fetchone()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT DATE(last_check)) 
        FROM products 
        WHERE user_id = ?
    ''', (user_id,))
    
    days_active = cursor.fetchone()[0]
    
    conn.close()
    
    stats_text = f"""
📊 Ваша статистика:

🎮 Всего товаров: {total}
🎯 Цен достигнуто: {reached}
📅 Дней активности: {days_active}

💡 Совет: Добавляйте больше товаров для лучшего отслеживания!
    """
    
    await query.edit_message_text(stats_text)

# Проверка цен для конкретного пользователя
async def check_user_prices(user_id, context):
    conn = sqlite3.connect('ggsell_monitor.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, product_url, product_name, target_price, current_price 
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))
    
    products = cursor.fetchall()
    
    updates = []
    
    for product in products:
        product_id, url, name, target_price, old_price = product
        
        # Получаем актуальную цену
        product_info = get_ggsell_product_info(url)
        
        if product_info:
            new_price = product_info['price']
            
            # Обновляем текущую цену
            cursor.execute('''
                UPDATE products 
                SET current_price = ?, last_check = ?
                WHERE id = ?
            ''', (new_price, datetime.now(), product_id))
            
            # Сохраняем в историю
            cursor.execute('''
                INSERT INTO price_history (product_id, price)
                VALUES (?, ?)
            ''', (product_id, new_price))
            
            # Проверяем изменение цены
            price_changed = abs(new_price - old_price) > 0.01
            
            # Проверяем, достигнута ли целевая цена
            target_reached = new_price <= target_price and old_price > target_price
            
            if price_changed or target_reached:
                updates.append({
                    'name': name,
                    'old_price': old_price,
                    'new_price': new_price,
                    'target_price': target_price,
                    'target_reached': target_reached,
                    'url': url
                })
    
    conn.commit()
    conn.close()
    
    # Отправляем уведомления об изменениях
    for update_info in updates:
        try:
            if update_info['target_reached']:
                message = f"""
🎉 ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!

🎮 {update_info['name']}
💰 Новая цена: {update_info['new_price']} руб.
🎯 Ваша цель: {update_info['target_price']} руб.

🛒 Скорее покупайте: {update_info['url']}
                """
            else:
                message = f"""
📈 ИЗМЕНЕНИЕ ЦЕНЫ

🎮 {update_info['name']}
📉 Было: {update_info['old_price']} руб.
📈 Стало: {update_info['new_price']} руб.
🎯 Цель: {update_info['target_price']} руб.

🔗 {update_info['url']}
                """
            
            await context.bot.send_message(chat_id=user_id, text=message)
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

# Фоновая задача для проверки цен
def background_price_checker(app):
    def job():
        conn = sqlite3.connect('ggsell_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT user_id FROM products WHERE is_active = TRUE')
        users = cursor.fetchall()
        conn.close()
        
        for user in users:
            user_id = user[0]
            asyncio.run_coroutine_threadsafe(
                check_user_prices(user_id, app),
                app._loop
            )
    
    # Запускаем проверку каждые 4 часа
    schedule.every(4).hours.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Основная функция
def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add_product", add_product))
    application.add_handler(CommandHandler("my_products", my_products))
    application.add_handler(CommandHandler("check_prices", check_prices))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target_price))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск фоновой задачи для проверки цен
    price_checker_thread = threading.Thread(
        target=background_price_checker, 
        args=(application,),
        daemon=True
    )
    price_checker_thread.start()
    
    # Запуск бота
    logger.info("GGSell Price Monitor Bot запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()