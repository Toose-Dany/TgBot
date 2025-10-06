import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import schedule
import threading
from datetime import datetime
import re

# Инициализация бота
bot = telebot.TeleBot('8406426014:AAHSvck3eXH6p8J34q7HID2A-ZoPXfaHbag')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('yandex_market.db')
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
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

# Упрощенный парсер Яндекс Маркета
class SimpleYandexMarketParser:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }
    
    def search_products(self, query, max_results=5):
        """
        Упрощенный поиск товаров на Яндекс Маркете
        """
        try:
            # Кодируем запрос для URL
            encoded_query = requests.utils.quote(query)
            url = f"https://market.yandex.ru/"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            # Используем встроенный html.parser вместо lxml
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Демо-данные (в реальном боте нужно настроить правильные селекторы)
            return self.get_demo_products(query, max_results)
            
        except Exception as e:
            print(f"Ошибка поиска товаров: {e}")
            return self.get_demo_products(query, max_results)
    
    def get_demo_products(self, query, max_results):
        """Демо-данные для тестирования"""
        demo_products = []
        base_price = 1000
        
        for i in range(max_results):
            demo_products.append({
                'name': f'{query} - Модель {i+1}',
                'price': base_price * (i + 1),
                'rating': round(4.0 + i * 0.2, 1),
                'reviews': (i + 1) * 10,
                'link': f'https://market.yandex.ru/product/demo-{i+1}',
                'image': ''
            })
        
        return demo_products
    
    def get_product_price(self, product_url):
        """
        Получение текущей цены товара (демо-версия)
        """
        try:
            # В реальном боте здесь должен быть парсинг
            # Для демо возвращаем случайную цену
            import random
            return random.randint(500, 5000)
            
        except Exception as e:
            print(f"Ошибка получения цены: {e}")
            return 0

# Создаем парсер
parser = SimpleYandexMarketParser()

# Команда /start
@bot.message_handler(commands=['start', 'main', 'hello'])
def send_welcome(message):
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""
🎉 Привет, {user.first_name}!

Я бот для мониторинга цен на Яндекс Маркете.

📊 Что я умею:
• Искать товары на Яндекс Маркете
• Отслеживать изменение цен
• Уведомлять о скидках
• Показывать историю цен

🎯 Основные команды:
/search - Найти товар
/add - Добавить товар для отслеживания
/my_products - Мои товары
/check - Проверить цены
/help - Помощь

💡 Начните с команды /search чтобы найти товар!

⚠️ Сейчас работает демо-режим с тестовыми данными.
    """
    
    bot.send_message(message.chat.id, welcome_text)
    show_main_menu(message)

def show_main_menu(message):
    """Показать главное меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('🔍 Поиск товара')
    btn2 = types.KeyboardButton('📊 Мои товары')
    btn3 = types.KeyboardButton('🔄 Проверить цены')
    btn4 = types.KeyboardButton('ℹ️ Помощь')
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

# Команда /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
📋 Доступные команды:

🔍 /search - Поиск товаров на Яндекс Маркете
📝 /add - Добавить товар для отслеживания
📊 /my_products - Показать отслеживаемые товары
🔄 /check - Проверить актуальные цены

🔎 Как использовать:
1. Используйте /search для поиска товара
2. Скопируйте ссылку на понравившийся товар
3. Используйте /add чтобы добавить товар для отслеживания
4. Укажите желаемую цену
5. Получайте уведомления при изменении цены!

⏰ Бот проверяет цены автоматически каждые 6 часов.

⚠️ Внимание: Сейчас работает демо-режим с тестовыми данными.
    """
    
    bot.send_message(message.chat.id, help_text)

# Обработка текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == '🔍 Поиск товара':
        bot.send_message(message.chat.id, "Введите название товара для поиска:")
        bot.register_next_step_handler(message, process_search_query)
    
    elif message.text == '📊 Мои товары':
        show_user_products(message)
    
    elif message.text == '🔄 Проверить цены':
        check_prices_now(message)
    
    elif message.text == 'ℹ️ Помощь':
        send_help(message)
    
    else:
        bot.send_message(message.chat.id, "Используйте кнопки меню или команды")

# Поиск товаров
@bot.message_handler(commands=['search'])
def search_products(message):
    bot.send_message(message.chat.id, "🔍 Введите название товара для поиска на Яндекс Маркете:")
    bot.register_next_step_handler(message, process_search_query)

def process_search_query(message):
    query = message.text
    if len(query) < 2:
        bot.send_message(message.chat.id, "❌ Слишком короткий запрос. Попробуйте еще раз.")
        return
    
    bot.send_message(message.chat.id, "🔎 Ищу товары...")
    
    products = parser.search_products(query, max_results=5)
    
    if not products:
        bot.send_message(message.chat.id, "❌ Товары не найдены. Попробуйте другой запрос.")
        return
    
    # Отправляем найденные товары
    for i, product in enumerate(products, 1):
        product_text = format_product_info(product, i)
        bot.send_message(message.chat.id, product_text, parse_mode='HTML')
    
    bot.send_message(message.chat.id, 
                    "💡 Чтобы отслеживать товар, используйте команду /add")

def format_product_info(product, number=1):
    """Форматирование информации о товаре"""
    rating_text = f"⭐ {product['rating']}" if product['rating'] > 0 else "⭐ Нет оценок"
    reviews_text = f"📝 {product['reviews']} отзывов" if product['reviews'] > 0 else "📝 Нет отзывов"
    
    return f"""
<b>Товар #{number}</b>
🏷️ <b>{product['name']}</b>
💰 <b>Цена: {product['price']:,} ₽</b>
{rating_text} | {reviews_text}
🔗 <a href="{product['link']}">Ссылка на товар</a>
    """.replace(',', ' ')

# Добавление товара для отслеживания
@bot.message_handler(commands=['add'])
def add_product(message):
    bot.send_message(message.chat.id, 
                    "🔗 Пришлите ссылку на товар с Яндекс Маркета\n\n"
                    "Пример:\n"
                    "https://market.yandex.ru/product/123456789\n\n"
                    "Или название товара для демо:")
    bot.register_next_step_handler(message, process_product_url)

def process_product_url(message):
    user_input = message.text.strip()
    
    # Если это ссылка
    if 'market.yandex.ru' in user_input:
        url = user_input
        product_name = "Товар с Яндекс Маркета"
    else:
        # Если это название товара (демо-режим)
        url = f"https://market.yandex.ru/product/demo-{hash(user_input) % 1000}"
        product_name = user_input
    
    # Сохраняем URL и запрашиваем целевую цену
    bot.send_message(message.chat.id, "💰 Укажите целевую цену (в рублях):\nПример: 5000")
    bot.register_next_step_handler(message, process_target_price, url, product_name)

def process_target_price(message, product_url, product_name):
    try:
        target_price = float(message.text.replace(' ', '').replace(',', '.'))
        
        if target_price <= 0:
            bot.send_message(message.chat.id, "❌ Цена должна быть положительной. Попробуйте еще раз.")
            return
        
        # Получаем текущую цену (демо)
        current_price = parser.get_product_price(product_url)
        
        # Сохраняем в базу данных
        conn = sqlite3.connect('yandex_market.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO products (user_id, product_name, product_url, target_price, current_price, last_check)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, product_name, product_url, target_price, current_price, datetime.now()))
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id,
                        f"✅ Товар добавлен для отслеживания!\n\n"
                        f"🏷️ {product_name}\n"
                        f"🎯 Целевая цена: {target_price} ₽\n"
                        f"💰 Текущая цена: {current_price} ₽\n"
                        f"🔗 {product_url}\n\n"
                        f"📊 Бот будет уведомлять вас при изменении цены!")
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат цены. Введите число (например: 5000)")

# Показать товары пользователя
@bot.message_handler(commands=['my_products'])
def show_user_products(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect('yandex_market.db')
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
        bot.send_message(message.chat.id, 
                        "📭 У вас нет отслеживаемых товаров.\n"
                        "Используйте команду /add чтобы добавить товар.")
        return
    
    for product in products:
        product_id, name, url, target_price, current_price, last_check = product
        
        status = "🎉 Цена достигнута!" if current_price <= target_price else "⏳ Ожидание"
        
        product_info = f"""
<b>Товар #{product_id}</b>
🏷️ {name}
💰 Текущая цена: <b>{current_price:,} ₽</b>
🎯 Целевая цена: <b>{target_price:,} ₽</b>
📊 Статус: {status}
📅 Последняя проверка: {last_check}
🔗 <a href="{url}">Ссылка</a>
        """.replace(',', ' ')
        
        # Создаем inline кнопки для управления
        markup = types.InlineKeyboardMarkup()
        btn_check = types.InlineKeyboardButton('🔄 Проверить сейчас', callback_data=f'check_{product_id}')
        btn_delete = types.InlineKeyboardButton('❌ Удалить', callback_data=f'delete_{product_id}')
        markup.add(btn_check, btn_delete)
        
        bot.send_message(message.chat.id, product_info, parse_mode='HTML', reply_markup=markup)

# Обработка callback запросов
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith('check_'):
        product_id = int(call.data.split('_')[1])
        check_single_product(call.message, product_id)
    
    elif call.data.startswith('delete_'):
        product_id = int(call.data.split('_')[1])
        delete_product(call.message, product_id)

def check_single_product(message, product_id):
    """Проверка одного товара"""
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT product_url, current_price, product_name FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if product:
        product_url, old_price, product_name = product
        new_price = parser.get_product_price(product_url)
        
        # Обновляем цену в базе
        cursor.execute('''
            UPDATE products 
            SET current_price = ?, last_check = ?
            WHERE id = ?
        ''', (new_price, datetime.now(), product_id))
        
        conn.commit()
        
        bot.send_message(message.chat.id, 
                        f"🏷️ {product_name}\n"
                        f"💰 Цена обновлена!\n"
                        f"📊 Было: {old_price} ₽\n"
                        f"📈 Стало: {new_price} ₽")
    
    conn.close()

def delete_product(message, product_id):
    """Удаление товара из отслеживания"""
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE products SET is_active = FALSE WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "✅ Товар удален из отслеживания")

# Проверка всех цен
@bot.message_handler(commands=['check'])
def check_prices_now(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, "🔍 Проверяю цены всех товаров...")
    
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, product_url, product_name, current_price, target_price
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))
    
    products = cursor.fetchall()
    
    updated_count = 0
    for product in products:
        product_id, url, name, old_price, target_price = product
        new_price = parser.get_product_price(url)
        
        if new_price > 0 and new_price != old_price:
            # Обновляем цену
            cursor.execute('''
                UPDATE products 
                SET current_price = ?, last_check = ?
                WHERE id = ?
            ''', (new_price, datetime.now(), product_id))
            
            updated_count += 1
            
            # Отправляем уведомление об изменении цены
            if new_price <= target_price:
                bot.send_message(message.chat.id,
                                f"🎉 ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                f"🏷️ {name}\n"
                                f"💰 Новая цена: {new_price} ₽\n"
                                f"🎯 Цель: {target_price} ₽")
            else:
                bot.send_message(message.chat.id,
                                f"📈 ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                f"🏷️ {name}\n"
                                f"📉 Было: {old_price} ₽\n"
                                f"📈 Стало: {new_price} ₽")
    
    conn.commit()
    conn.close()
    
    if updated_count == 0:
        bot.send_message(message.chat.id, "✅ Все цены актуальны!")
    else:
        bot.send_message(message.chat.id, f"✅ Проверка завершена! Обновлено {updated_count} цен.")

# Фоновая задача для автоматической проверки цен
def background_price_checker():
    def job():
        try:
            conn = sqlite3.connect('yandex_market.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT DISTINCT user_id FROM products WHERE is_active = TRUE')
            users = cursor.fetchall()
            
            for user in users:
                user_id = user[0]
                
                cursor.execute('''
                    SELECT id, product_url, product_name, current_price, target_price
                    FROM products 
                    WHERE user_id = ? AND is_active = TRUE
                ''', (user_id,))
                
                products = cursor.fetchall()
                
                for product in products:
                    product_id, url, name, old_price, target_price = product
                    new_price = parser.get_product_price(url)
                    
                    if new_price > 0 and new_price != old_price:
                        # Обновляем цену
                        cursor.execute('''
                            UPDATE products 
                            SET current_price = ?, last_check = ?
                            WHERE id = ?
                        ''', (new_price, datetime.now(), product_id))
                        
                        # Отправляем уведомление
                        if new_price <= target_price:
                            bot.send_message(user_id,
                                            f"🎉 ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                            f"🏷️ {name}\n"
                                            f"💰 Новая цена: {new_price} ₽\n"
                                            f"🎯 Цель: {target_price} ₽")
                        else:
                            bot.send_message(user_id,
                                            f"📈 ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                            f"🏷️ {name}\n"
                                            f"📉 Было: {old_price} ₽\n"
                                            f"📈 Стало: {new_price} ₽")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")
    
    # Запускаем проверку каждые 2 часа
    schedule.every(2).hours.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Запуск фоновой задачи
def start_background_jobs():
    thread = threading.Thread(target=background_price_checker, daemon=True)
    thread.start()

# Главная функция
if __name__ == '__main__':
    print("🤖 Запуск бота мониторинга Яндекс Маркета...")
    init_db()
    start_background_jobs()
    print("✅ Бот запущен! (Демо-режим)")
    bot.infinity_polling()