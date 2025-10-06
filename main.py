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
import json
import urllib.parse

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

# Реальный парсер Яндекс Маркета
class YandexMarketParser:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def search_products(self, query, max_results=5):
        """
        Реальный поиск товаров на Яндекс Маркете
        """
        try:
            # Кодируем запрос для URL
            encoded_query = urllib.parse.quote(query)
            url = f"https://market.yandex.ru/search?text={encoded_query}"
            
            print(f" Ищу: {query}")
            print(f" URL: {url}")
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            products = []
            
            # Поиск карточек товаров - основные селекторы Яндекс Маркета
            product_selectors = [
                '[data-zone-name="snippet"]',
                '.snippet-cell',
                '[data-autotest-id="product-snippet"]',
                '.snippet-horizontal'
            ]
            
            product_cards = []
            for selector in product_selectors:
                product_cards = soup.select(selector)
                if product_cards:
                    print(f" Найдено карточек с селектором {selector}: {len(product_cards)}")
                    break
            
            if not product_cards:
                # Альтернативный поиск по классам
                product_cards = soup.find_all('div', class_=lambda x: x and any(word in str(x).lower() for word in ['snippet', 'product', 'item']))
                print(f" Альтернативный поиск: {len(product_cards)} карточек")
            
            for card in product_cards[:max_results]:
                product = self.parse_product_card(card)
                if product and product['name'] and product['price'] > 0:
                    products.append(product)
                    print(f" Добавлен товар: {product['name']} - {product['price']} руб.")
            
            return products
            
        except Exception as e:
            print(f" Ошибка поиска товаров: {e}")
            return []
    
    def parse_product_card(self, card):
        """Парсим реальную карточку товара"""
        try:
            product = {
                'name': '',
                'price': 0,
                'rating': 0,
                'reviews': 0,
                'link': '',
                'image': '',
                'shop': ''
            }
            
            # Название товара
            name_selectors = [
                'h3 a',
                '.snippet-title a',
                '[data-zone-name="title"]',
                '.snippet-cell__title a',
                'a[data-zone-name="title"]'
            ]
            
            for selector in name_selectors:
                name_elem = card.select_one(selector)
                if name_elem:
                    product['name'] = name_elem.get_text(strip=True)
                    # Получаем ссылку из элемента названия
                    href = name_elem.get('href')
                    if href:
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = 'https://market.yandex.ru' + href
                        product['link'] = href
                    break
            
            # Если название не нашли, попробуем другие селекторы
            if not product['name']:
                name_elem = card.find('h3') or card.find('a', {'data-zone-name': 'title'})
                if name_elem:
                    product['name'] = name_elem.get_text(strip=True)
            
            # Цена - основные селекторы цен
            price_selectors = [
                '[data-zone-name="price"]',
                '.snippet-price',
                '.price',
                '.snippet-cell__price',
                '[automation-id="price"]'
            ]
            
            for selector in price_selectors:
                price_elem = card.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Извлекаем числа из цены
                    price_match = re.search(r'(\d[\d\s]*)', price_text.replace(' ', ''))
                    if price_match:
                        try:
                            product['price'] = float(price_match.group(1).replace(' ', ''))
                            break
                        except ValueError:
                            continue
            
            # Рейтинг
            rating_selectors = [
                '[aria-label*="Рейтинг"]',
                '.rating',
                '.snippet-rating',
                '[data-zone-name="rating"]'
            ]
            
            for selector in rating_selectors:
                rating_elem = card.select_one(selector)
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    rating_match = re.search(r'(\d+[.,]?\d*)', rating_text)
                    if rating_match:
                        try:
                            product['rating'] = float(rating_match.group(1).replace(',', '.'))
                            break
                        except ValueError:
                            continue
            
            # Количество отзывов
            reviews_selectors = [
                '[data-zone-name="review"]',
                '.snippet-rating__reviews',
                '.rating__reviews'
            ]
            
            for selector in reviews_selectors:
                reviews_elem = card.select_one(selector)
                if reviews_elem:
                    reviews_text = reviews_elem.get_text(strip=True)
                    reviews_match = re.search(r'(\d+)', reviews_text)
                    if reviews_match:
                        try:
                            product['reviews'] = int(reviews_match.group(1))
                            break
                        except ValueError:
                            continue
            
            # Магазин
            shop_selectors = [
                '[data-zone-name="shop"]',
                '.snippet-shop',
                '.shop-name'
            ]
            
            for selector in shop_selectors:
                shop_elem = card.select_one(selector)
                if shop_elem:
                    product['shop'] = shop_elem.get_text(strip=True)
                    break
            
            # Изображение
            img_elem = card.select_one('img')
            if img_elem:
                product['image'] = img_elem.get('src', '')
                if product['image'].startswith('//'):
                    product['image'] = 'https:' + product['image']
            
            return product
            
        except Exception as e:
            print(f" Ошибка парсинга карточки: {e}")
            return None
    
    def get_product_price(self, product_url):
        """
        Получение текущей цены товара по ссылке
        """
        try:
            if not product_url.startswith('http'):
                product_url = 'https://market.yandex.ru' + product_url
            
            print(f" Получаю цену для: {product_url}")
            
            response = self.session.get(product_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем цену на странице товара
            price_selectors = [
                '[data-zone-name="price"]',
                '.price',
                '[automation-id="price"]',
                '.snippet-price'
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d\s]*)', price_text.replace(' ', ''))
                    if price_match:
                        try:
                            return float(price_match.group(1).replace(' ', ''))
                        except ValueError:
                            continue
            
            return 0
            
        except Exception as e:
            print(f" Ошибка получения цены: {e}")
            return 0

# Создаем парсер
parser = YandexMarketParser()

# Команда /start
@bot.message_handler(commands=['start', 'main', 'hello'])
def send_welcome(message):
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""
 Привет, {user.first_name}!

Я бот для мониторинга цен на Яндекс Маркете.

 Что я умею:
• Искать товары на Яндекс Маркете
• Отслеживать изменение цен
• Уведомлять о скидках
• Показывать историю цен

 Основные команды:
/search - Найти товар
/add - Добавить товар для отслеживания
/my_products - Мои товары
/check - Проверить цены
/help - Помощь

 Начните с команды /search чтобы найти товар!
    """
    
    bot.send_message(message.chat.id, welcome_text)
    show_main_menu(message)

def show_main_menu(message):
    """Показать главное меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Поиск товара')
    btn2 = types.KeyboardButton('Мои товары')
    btn3 = types.KeyboardButton('Проверить цены')
    btn4 = types.KeyboardButton('Помощь')
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

# Команда /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
Доступные команды:

/search - Поиск товаров на Яндекс Маркете
/add - Добавить товар для отслеживания
/my_products - Показать отслеживаемые товары
/check - Проверить актуальные цены

Как использовать:
1. Используйте /search для поиска товара
2. Скопируйте ссылку на понравившийся товар
3. Используйте /add чтобы добавить товар для отслеживания
4. Укажите желаемую цену
5. Получайте уведомления при изменении цены!

Бот проверяет цены автоматически каждые 6 часов.
    """
    
    bot.send_message(message.chat.id, help_text)

# Обработка текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == 'Поиск товара':
        bot.send_message(message.chat.id, "Введите название товара для поиска:")
        bot.register_next_step_handler(message, process_search_query)
    
    elif message.text == 'Мои товары':
        show_user_products(message)
    
    elif message.text == 'Проверить цены':
        check_prices_now(message)
    
    elif message.text == 'Помощь':
        send_help(message)
    
    else:
        bot.send_message(message.chat.id, "Используйте кнопки меню или команды")

# Поиск товаров
@bot.message_handler(commands=['search'])
def search_products(message):
    bot.send_message(message.chat.id, "Введите название товара для поиска на Яндекс Маркете:")
    bot.register_next_step_handler(message, process_search_query)

def process_search_query(message):
    query = message.text.strip()
    if len(query) < 2:
        bot.send_message(message.chat.id, "Слишком короткий запрос. Попробуйте еще раз.")
        return
    
    bot.send_message(message.chat.id, f"Ищу '{query}' на Яндекс Маркете... Это может занять до 30 секунд.")
    
    try:
        products = parser.search_products(query, max_results=5)
        
        if not products:
            bot.send_message(message.chat.id, 
                           "Товары не найдены или произошла ошибка парсинга.\n"
                           "Попробуйте:\n"
                           "• Другой запрос\n"
                           "• Более конкретное название\n"
                           "• Подождать несколько минут")
            return
        
        # Отправляем найденные товары
        for i, product in enumerate(products, 1):
            product_text = format_product_info(product, i)
            
            # Если есть изображение, отправляем фото с описанием
            if product.get('image') and product['image'].startswith('http'):
                try:
                    bot.send_photo(message.chat.id, product['image'], 
                                 caption=product_text, parse_mode='HTML')
                except:
                    bot.send_message(message.chat.id, product_text, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, product_text, parse_mode='HTML')
        
        bot.send_message(message.chat.id, 
                        "💡 Чтобы отслеживать товар, скопируйте ссылку и используйте команду /add")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка при поиске: {str(e)}")

def format_product_info(product, number=1):
    """Форматирование информации о товаре"""
    rating_text = f"{product['rating']}" if product['rating'] > 0 else "Нет оценок"
    reviews_text = f"{product['reviews']} отзывов" if product['reviews'] > 0 else "Нет отзывов"
    shop_text = f"{product['shop']}" if product.get('shop') else "Магазин не указан"
    
    return f"""
<b>Товар #{number}</b>
<b>{product['name']}</b>
<b>Цена: {product['price']:,} ₽</b>
{rating_text} | {reviews_text}
{shop_text}
<a href="{product['link']}">Ссылка на товар</a>
    """.replace(',', ' ')

# Добавление товара для отслеживания
@bot.message_handler(commands=['add'])
def add_product(message):
    bot.send_message(message.chat.id, 
                    "Пришлите ссылку на товар с Яндекс Маркета\n\n"
                    "Пример:\n"
                    "https://market.yandex.ru/product/123456789\n"
                    "или\n"
                    "https://market.yandex.ru/product--noutbuk/123456789")
    bot.register_next_step_handler(message, process_product_url)

def process_product_url(message):
    url = message.text.strip()
    
    if 'market.yandex.ru' not in url:
        bot.send_message(message.chat.id, "Это не ссылка на Яндекс Маркет. Попробуйте еще раз.")
        return
    
    # Получаем информацию о товаре
    bot.send_message(message.chat.id, "Получаю информацию о товаре...")
    
    current_price = parser.get_product_price(url)
    
    if current_price == 0:
        bot.send_message(message.chat.id, 
                        "Не удалось получить цену товара.\n"
                        "Возможные причины:\n"
                        "• Товар временно недоступен\n"
                        "• Изменилась структура сайта\n"
                        "• Проблемы с подключением")
        return
    
    # Получаем название товара из страницы
    product_name = f"Товар с Яндекс Маркета ({current_price} руб.)"
    
    # Сохраняем URL и запрашиваем целевую цену
    bot.send_message(message.chat.id, 
                    f"Текущая цена: {current_price} ₽\n\n"
                    f"Укажите целевую цену (в рублях):\n"
                    f"Пример: 5000")
    bot.register_next_step_handler(message, process_target_price, url, product_name, current_price)

def process_target_price(message, product_url, product_name, current_price):
    try:
        target_price = float(message.text.replace(' ', '').replace(',', '.'))
        
        if target_price <= 0:
            bot.send_message(message.chat.id, "Цена должна быть положительной. Попробуйте еще раз.")
            return
        
        # Сохраняем в базу данных
        conn = sqlite3.connect('yandex_market.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO products (user_id, product_name, product_url, target_price, current_price, last_check)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, product_name, product_url, target_price, current_price, datetime.now()))
        
        conn.commit()
        conn.close()
        
        status = "Уже достигнута!" if current_price <= target_price else "Ожидание"
        
        bot.send_message(message.chat.id,
                        f"Товар добавлен для отслеживания!\n\n"
                        f"{product_name}\n"
                        f"Текущая цена: {current_price} ₽\n"
                        f"Целевая цена: {target_price} ₽\n"
                        f"Статус: {status}\n"
                        f"{product_url}\n\n"
                        f"Бот будет уведомлять вас при изменении цены!")
        
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат цены. Введите число (например: 5000)")

# Остальные функции остаются такими же как в предыдущем коде
# (show_user_products, handle_callback, check_single_product, delete_product, check_prices_now)

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
                        "У вас нет отслеживаемых товаров.\n"
                        "Используйте команду /add чтобы добавить товар.")
        return
    
    for product in products:
        product_id, name, url, target_price, current_price, last_check = product
        
        status = "Цена достигнута!" if current_price <= target_price else "Ожидание"
        
        product_info = f"""
<b>Товар #{product_id}</b>
{name}
Текущая цена: <b>{current_price:,} ₽</b>
Целевая цена: <b>{target_price:,} ₽</b>
Статус: {status}
Последняя проверка: {last_check}
<a href="{url}">Ссылка</a>
        """.replace(',', ' ')
        
        # Создаем inline кнопки для управления
        markup = types.InlineKeyboardMarkup()
        btn_check = types.InlineKeyboardButton('Проверить сейчас', callback_data=f'check_{product_id}')
        btn_delete = types.InlineKeyboardButton('Удалить', callback_data=f'delete_{product_id}')
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
    
    cursor.execute('SELECT product_url, current_price, product_name, target_price FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if product:
        product_url, old_price, product_name, target_price = product
        new_price = parser.get_product_price(product_url)
        
        if new_price > 0:
            # Обновляем цену в базе
            cursor.execute('''
                UPDATE products 
                SET current_price = ?, last_check = ?
                WHERE id = ?
            ''', (new_price, datetime.now(), product_id))
            
            conn.commit()
            
            if new_price <= target_price and old_price > target_price:
                bot.send_message(message.chat.id,
                                f"ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                f"{product_name}\n"
                                f"Новая цена: {new_price} ₽\n"
                                f"Цель: {target_price} ₽\n"
                                f"Было: {old_price} ₽")
            else:
                bot.send_message(message.chat.id, 
                                f"{product_name}\n"
                                f"Цена обновлена!\n"
                                f"Было: {old_price} ₽\n"
                                f"Стало: {new_price} ₽")
        else:
            bot.send_message(message.chat.id, "Не удалось получить актуальную цену")
    
    conn.close()

def delete_product(message, product_id):
    """Удаление товара из отслеживания"""
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE products SET is_active = FALSE WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "Товар удален из отслеживания")

# Проверка всех цен
@bot.message_handler(commands=['check'])
def check_prices_now(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, "Проверяю цены всех товаров...")
    
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
                                f"ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                f"{name}\n"
                                f"Новая цена: {new_price} ₽\n"
                                f"Цель: {target_price} ₽\n"
                                f"{url}")
            else:
                bot.send_message(message.chat.id,
                                f"ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                f"{name}\n"
                                f"Было: {old_price} ₽\n"
                                f"Стало: {new_price} ₽\n"
                                f"{url}")
    
    conn.commit()
    conn.close()
    
    if updated_count == 0:
        bot.send_message(message.chat.id, "Все цены актуальны!")
    else:
        bot.send_message(message.chat.id, f"Проверка завершена! Обновлено {updated_count} цен.")

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
                                            f"ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                            f"{name}\n"
                                            f"Новая цена: {new_price} ₽\n"
                                            f"Цель: {target_price} ₽")
                        else:
                            bot.send_message(user_id,
                                            f"ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                            f"{name}\n"
                                            f"Было: {old_price} ₽\n"
                                            f"Стало: {new_price} ₽")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")
    
    # Запускаем проверку каждые 6 часов
    schedule.every(6).hours.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Запуск фоновой задачи
def start_background_jobs():
    thread = threading.Thread(target=background_price_checker, daemon=True)
    thread.start()

# Главная функция
if __name__ == '__main__':
    print("Запуск бота мониторинга Яндекс Маркета...")
    init_db()
    start_background_jobs()
    print("Бот запущен! (Реальный парсинг)")
    bot.infinity_polling()




