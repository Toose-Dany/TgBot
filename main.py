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
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Инициализация бота
bot = telebot.TeleBot('8406426014:AAHSvck3eXH6p8J34q7HID2A-ZoPXfaHbag')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
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
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

# Исправленный парсер для GGsel с правильными ссылками
class CorrectGGselParser:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.init_driver()
    
    def init_driver(self):
        """Инициализация Chrome драйвера"""
        try:
            print("Запуск Chrome для GGsel...")
            
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            chrome_options.add_argument("--window-size=1920,1080")
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("Chrome запущен")
            
        except Exception as e:
            print(f"Ошибка запуска Chrome: {e}")
            self.driver = None

    def search_products_correct(self, query, max_results=5):
        """
        Поиск товаров на GGsel с правильными ссылками
        """
        if not self.driver:
            return []
        
        try:
            # ПРАВИЛЬНЫЙ URL для поиска на GGsel
            encoded_query = requests.utils.quote(query)
            url = f"https://ggsel.com/catalog?search={encoded_query}"
            
            print(f"Поиск: {query}")
            print(f"URL: {url}")
            
            # Загружаем страницу
            self.driver.get(url)
            time.sleep(6)
            
            # Получаем HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            products = []
            
            # Ищем товары по структуре GGsel
            # Пробуем разные подходы к поиску товаров
            product_elements = []
            
            # 1. Ищем по классам товаров
            product_selectors = [
                'div[class*="product"]',
                'div[class*="item"]', 
                'div[class*="card"]',
                'div[class*="goods"]',
                'a[class*="product"]',
                'a[class*="item"]'
            ]
            
            for selector in product_selectors:
                elements = soup.select(selector)
                if elements:
                    product_elements.extend(elements)
                    print(f"Найдено по селектору {selector}: {len(elements)}")
            
            # 2. Ищем все div с классом
            all_divs = soup.find_all('div', class_=True)
            for div in all_divs:
                class_text = ' '.join(div.get('class', [])).lower()
                if any(word in class_text for word in ['product', 'item', 'card', 'goods']):
                    if div not in product_elements:
                        product_elements.append(div)
            
            # 3. Ищем все ссылки, которые могут быть товарами
            product_links = soup.find_all('a', href=True)
            for link in product_links:
                href = link.get('href', '')
                if any(pattern in href for pattern in ['/goods/', '/product/', '/game/', '/item/']):
                    # Создаем контейнер для ссылки
                    if link not in product_elements:
                        product_elements.append(link)
            
            print(f"Всего найдено потенциальных элементов: {len(product_elements)}")
            
            # Обрабатываем найденные элементы
            for element in product_elements[:max_results*2]:  # Берем больше для фильтрации
                product = self.extract_product_correct(element, query)
                if product and product['price'] > 0 and product['name']:
                    # Проверяем дубликаты по названию и цене
                    is_duplicate = False
                    for existing_product in products:
                        if (existing_product['name'] == product['name'] and 
                            existing_product['price'] == product['price']):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        products.append(product)
                        print(f"Добавлен товар: {product['name'][:30]} - {product['price']} руб.")
                
                if len(products) >= max_results:
                    break
            
            return products
            
        except Exception as e:
            print(f"Ошибка поиска: {e}")
            return []

    def extract_product_correct(self, element, query):
        """Извлечение данных о товаре с правильными ссылками"""
        try:
            product = {
                'name': f"{query}",
                'price': 0,
                'link': '',
                'image': '',
                'seller': 'GGsel',
                'platform': 'GGsel'
            }
            
            # Получаем текст элемента
            element_text = element.get_text(strip=True)
            
            # 1. Ищем название товара
            name = self.extract_product_name(element, element_text, query)
            if name:
                product['name'] = name
            
            # 2. Ищем цену
            price = self.extract_product_price(element_text)
            if price > 0:
                product['price'] = price
            
            # 3. Ищем ПРАВИЛЬНУЮ ссылку на товар
            link = self.extract_product_link(element)
            if link:
                product['link'] = link
            
            # Проверяем, что товар валидный
            if product['price'] == 0 or not product['name']:
                return None
                
            return product
            
        except Exception as e:
            print(f"Ошибка извлечения товара: {e}")
            return None

    def extract_product_name(self, element, element_text, query):
        """Извлечение названия товара"""
        # Разбиваем текст на строки
        lines = [line.strip() for line in element_text.split('\n') if line.strip()]
        
        # Ищем самую длинную строку, которая не является ценой
        candidate = None
        for line in lines:
            if len(line) > 10:  # Минимальная длина названия
                # Проверяем, что это не цена
                if not re.search(r'\d{3,}\s*[рруб]', line.lower()):
                    if not candidate or len(line) > len(candidate):
                        candidate = line
        
        if candidate:
            return candidate[:80]  # Ограничиваем длину
        
        # Если не нашли, используем запрос
        return f"{query}"

    def extract_product_price(self, text):
        """Извлечение цены из текста"""
        # Паттерны для поиска цены
        patterns = [
            r'(\d{1,3}(?:\s?\d{3})*)\s*[рруб]',
            r'цена\s*[:\-]?\s*(\d{1,3}(?:\s?\d{3})*)',
            r'(\d{1,3}(?:\s?\d{3})*)\s*₽',
            r'руб\s*(\d{1,3}(?:\s?\d{3})*)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    price_str = str(match).replace(' ', '').replace(',', '')
                    price = float(price_str)
                    if 10 <= price <= 100000:  # Реалистичный диапазон цен
                        return price
                except:
                    continue
        
        # Альтернативный поиск - просто ищем большие числа
        numbers = re.findall(r'\b\d{3,6}\b', text)
        for num in numbers:
            try:
                price = float(num)
                if 100 <= price <= 50000:  # Реалистичный диапазон
                    return price
            except:
                continue
        
        return 0

    def extract_product_link(self, element):
        """Извлечение ПРАВИЛЬНОЙ ссылки на товар"""
        # Если элемент сам является ссылкой
        if element.name == 'a':
            href = element.get('href', '')
            if href:
                return self.normalize_link(href)
        
        # Ищем ссылку внутри элемента
        link = element.find('a', href=True)
        if link:
            href = link.get('href', '')
            if href:
                return self.normalize_link(href)
        
        # Ищем любую ссылку в родительских элементах
        parent = element.parent
        for _ in range(3):  # Проверяем 3 уровня вверх
            if parent and parent.name == 'a' and parent.get('href'):
                href = parent.get('href')
                return self.normalize_link(href)
            if parent:
                parent = parent.parent
        
        # Если ссылка не найдена, создаем поисковую ссылку
        return "https://ggsel.com/catalog"

    def normalize_link(self, href):
        """Нормализация ссылки"""
        if not href:
            return "https://ggsel.com/catalog"
        
        # Убираем якоря и параметры
        href = href.split('#')[0]
        
        if href.startswith('//'):
            return 'https:' + href
        elif href.startswith('/'):
            return 'https://ggsel.com' + href
        elif href.startswith('http'):
            return href
        else:
            return 'https://ggsel.com/' + href

    def get_product_price_correct(self, product_url):
        """Получение цены товара по ПРАВИЛЬНОЙ ссылке"""
        if not self.driver:
            return 0
        
        try:
            print(f"Проверка цены: {product_url}")
            
            # Нормализуем URL
            if not product_url.startswith('http'):
                product_url = 'https://ggsel.com' + product_url
            
            self.driver.get(product_url)
            time.sleep(5)
            
            # Получаем HTML страницы
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем цену на странице товара
            page_text = soup.get_text()
            
            # Паттерны для поиска цены
            patterns = [
                r'(\d{1,3}(?:\s?\d{3})*)\s*[рруб]',
                r'цена\s*[:\-]?\s*(\d{1,3}(?:\s?\d{3})*)',
                r'(\d{1,3}(?:\s?\d{3})*)\s*₽',
                r'купить\s*за\s*(\d{1,3}(?:\s?\d{3})*)',
                r'стоимость\s*[:\-]?\s*(\d{1,3}(?:\s?\d{3})*)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = str(match).replace(' ', '').replace(',', '')
                        price = float(price_str)
                        if 1 <= price <= 1000000:
                            print(f"Цена найдена: {price} руб.")
                            return price
                    except:
                        continue
            
            print("Цена не найдена на странице")
            return 0
            
        except Exception as e:
            print(f"Ошибка получения цены: {e}")
            return 0
    
    def close(self):
        """Закрыть браузер"""
        if self.driver:
            self.driver.quit()
            print("Браузер закрыт")

# Создаем парсер
try:
    parser = CorrectGGselParser(headless=True)
    print("Парсер инициализирован")
except Exception as e:
    print(f"Ошибка инициализации парсера: {e}")
    parser = None

# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""Привет, {user.first_name}!

Я бот для отслеживания цен на GGsel.

Что я умею:
- Искать товары на GGsel
- Отслеживать изменение цен
- Уведомлять о скидках

Команды:
/search - Найти товар
/add - Добавить для отслеживания  
/my_products - Мои товары
/check - Проверить цены
/help - Помощь

Просто введи /search и название игры!"""
    
    bot.send_message(message.chat.id, welcome_text)

# Команда /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """Доступные команды:

/search - Найти товары на GGsel
/add - Добавить товар для отслеживания
/my_products - Показать мои товары
/check - Проверить все цены
/help - Эта справка

Примеры использования:
1. /search Minecraft
2. Скопируй ссылку на товар
3. /add - вставь ссылку
4. Укажи желаемую цену

Популярные запросы:
Minecraft, GTA 5, Steam, Fortnite, CSGO"""
    bot.send_message(message.chat.id, help_text)

# Поиск товаров
@bot.message_handler(commands=['search'])
def search_products(message):
    bot.send_message(message.chat.id, "Введите название игры или товара для поиска на GGsel:")
    bot.register_next_step_handler(message, process_search_query)

def process_search_query(message):
    query = message.text.strip()
    
    if not query or len(query) < 2:
        bot.send_message(message.chat.id, "Введите нормальный запрос (минимум 2 символа)")
        return
    
    if not parser:
        bot.send_message(message.chat.id, "Парсер не работает. Попробуйте позже.")
        return
    
    bot.send_message(message.chat.id, f"Ищу '{query}' на GGsel...")
    
    try:
        products = parser.search_products_correct(query, max_results=5)
        
        if not products:
            bot.send_message(message.chat.id, 
                           f"По запросу '{query}' ничего не найдено.\n\n"
                           "Попробуйте:\n"
                           "- Другой запрос\n" 
                           "- Английское название\n"
                           "- Более простой запрос")
            return
        
        # Показываем найденные товары
        for i, product in enumerate(products, 1):
            product_text = f"""
Товар #{i}
Название: {product['name']}
Цена: {product['price']} руб.
Ссылка: {product['link']}
"""
            bot.send_message(message.chat.id, product_text)
        
        bot.send_message(message.chat.id, 
                        "Чтобы отслеживать товар:\n"
                        "1. Скопируй ссылку\n" 
                        "2. Отправь команду /add\n"
                        "3. Вставь ссылку и укажи желаемую цену")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при поиске: {str(e)}")

# Добавление товара для отслеживания
@bot.message_handler(commands=['add'])
def add_product(message):
    bot.send_message(message.chat.id, 
                    "Пришлите ссылку на товар с GGsel\n\n"
                    "Пример правильной ссылки:\n"
                    "https://ggsel.com/goods/123456\n"
                    "https://ggsel.net/goods/123456\n"
                    "https://ggsel.com/product/123456")
    bot.register_next_step_handler(message, process_product_url)

def process_product_url(message):
    url = message.text.strip()
    
    # Проверяем, что это ссылка на товар GGsel
    if not any(domain in url for domain in ['ggsel.com/goods/', 'ggsel.net/goods/', 'ggsel.com/product/']):
        bot.send_message(message.chat.id, 
                        "Это не ссылка на товар GGsel.\n\n"
                        "Правильная ссылка должна содержать:\n"
                        "- ggsel.com/goods/...\n"
                        "- ggsel.net/goods/...\n"
                        "- ggsel.com/product/...")
        return
    
    if not parser:
        bot.send_message(message.chat.id, "Парсер не работает. Попробуйте позже.")
        return
    
    bot.send_message(message.chat.id, "Проверяю товар...")
    
    current_price = parser.get_product_price_correct(url)
    
    if current_price == 0:
        bot.send_message(message.chat.id, 
                        "Не удалось получить цену товара.\n"
                        "Возможно:\n"
                        "- Товар недоступен\n"
                        "- Неправильная ссылка\n"
                        "- Проблемы с сайтом")
        return
    
    # Получаем название товара из URL
    product_name = "Товар с GGsel"
    try:
        # Пробуем получить название из страницы
        parser.driver.get(url)
        time.sleep(3)
        soup = BeautifulSoup(parser.driver.page_source, 'html.parser')
        title = soup.find('title')
        if title:
            product_name = title.get_text(strip=True).split('|')[0].strip()
    except:
        pass
    
    # Сохраняем и запрашиваем целевую цену
    bot.send_message(message.chat.id, 
                    f"Название: {product_name}\n"
                    f"Текущая цена: {current_price} руб.\n\n"
                    f"Введите желаемую цену (в рублях):")
    bot.register_next_step_handler(message, process_target_price, url, product_name, current_price)

def process_target_price(message, product_url, product_name, current_price):
    try:
        target_price = float(message.text.replace(' ', '').replace(',', '.'))
        
        if target_price <= 0:
            bot.send_message(message.chat.id, "Цена должна быть больше 0. Попробуйте еще раз.")
            return
        
        # Сохраняем в базу
        conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO products (user_id, product_name, product_url, target_price, current_price, last_check)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, product_name, product_url, target_price, current_price, datetime.now()))
        
        conn.commit()
        conn.close()
        
        status = "Уже достигнута!" if current_price <= target_price else "Ожидание"
        
        bot.send_message(message.chat.id,
                        f"Товар добавлен!\n\n"
                        f"Название: {product_name}\n"
                        f"Текущая цена: {current_price} руб.\n"
                        f"Целевая цена: {target_price} руб.\n"
                        f"Статус: {status}\n\n"
                        f"Я сообщу, когда цена изменится!")
        
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат цены. Введите число (например: 1500)")

# Показать товары пользователя
@bot.message_handler(commands=['my_products'])
def show_user_products(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
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
                        "У вас нет отслеживаемых товаров.\n\n"
                        "Добавьте товар командой /add")
        return
    
    for product in products:
        product_id, name, url, target_price, current_price, last_check = product
        
        status = "ДОСТИГНУТА!" if current_price <= target_price else "ОЖИДАНИЕ"
        
        product_info = f"""
Товар #{product_id}
{name}
Текущая: {current_price} руб.
Цель: {target_price} руб.
{status}
Проверено: {last_check[:16]}
"""
        
        markup = types.InlineKeyboardMarkup()
        btn_check = types.InlineKeyboardButton('Проверить', callback_data=f'check_{product_id}')
        btn_delete = types.InlineKeyboardButton('Удалить', callback_data=f'delete_{product_id}')
        markup.add(btn_check, btn_delete)
        
        bot.send_message(message.chat.id, product_info, reply_markup=markup)

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
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT product_url, current_price, product_name, target_price FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if not product:
        bot.send_message(message.chat.id, "Товар не найден")
        return
    
    product_url, old_price, product_name, target_price = product
    
    if not parser:
        bot.send_message(message.chat.id, "Парсер не работает")
        conn.close()
        return
    
    bot.send_message(message.chat.id, "Проверяю цену...")
    
    new_price = parser.get_product_price_correct(product_url)
    
    if new_price > 0:
        # Обновляем цену
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
                            f"Новая цена: {new_price} руб.\n"
                            f"Цель: {target_price} руб.")
        elif new_price != old_price:
            bot.send_message(message.chat.id, 
                            f"Цена изменилась\n\n"
                            f"{product_name}\n"
                            f"Было: {old_price} руб.\n"
                            f"Стало: {new_price} руб.")
        else:
            bot.send_message(message.chat.id, 
                            f"Цена не изменилась\n"
                            f"{product_name}\n"
                            f"Текущая цена: {new_price} руб.")
    else:
        bot.send_message(message.chat.id, "Не удалось проверить цену")
    
    conn.close()

def delete_product(message, product_id):
    """Удаление товара"""
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('UPDATE products SET is_active = FALSE WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "Товар удален из отслеживания")

# Проверка всех цен
@bot.message_handler(commands=['check'])
def check_prices_now(message):
    user_id = message.from_user.id
    
    if not parser:
        bot.send_message(message.chat.id, "Парсер не работает")
        return
    
    bot.send_message(message.chat.id, "Проверяю все цены...")
    
    conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, product_url, product_name, current_price, target_price
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))
    
    products = cursor.fetchall()
    
    if not products:
        bot.send_message(message.chat.id, "Нет товаров для проверки")
        conn.close()
        return
    
    updated_count = 0
    
    for product in products:
        product_id, url, name, old_price, target_price = product
        new_price = parser.get_product_price_correct(url)
        
        if new_price > 0 and new_price != old_price:
            # Обновляем цену
            cursor.execute('''
                UPDATE products 
                SET current_price = ?, last_check = ?
                WHERE id = ?
            ''', (new_price, datetime.now(), product_id))
            
            updated_count += 1
            
            if new_price <= target_price:
                bot.send_message(message.chat.id,
                                f"ЦЕЛЬ ДОСТИГНУТА!\n"
                                f"{name}\n"
                                f"Новая цена: {new_price} руб.")
            else:
                bot.send_message(message.chat.id,
                                f"Цена изменилась\n"
                                f"{name}\n"
                                f"Было: {old_price} руб.\n"
                                f"Стало: {new_price} руб.")
        
        time.sleep(2)  # Пауза между запросами
    
    conn.commit()
    conn.close()
    
    if updated_count == 0:
        bot.send_message(message.chat.id, "Все цены актуальны!")
    else:
        bot.send_message(message.chat.id, f"Обновлено {updated_count} цен")

# Фоновая задача для автоматической проверки цен
def background_price_checker():
    def job():
        try:
            print(f"Автоматическая проверка цен на GGsel: {datetime.now()}")
            
            if not parser or not parser.driver:
                print("Парсер не доступен для фоновой проверки")
                return
                
            conn = sqlite3.connect('ggsel_market.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('SELECT DISTINCT user_id FROM products WHERE is_active = TRUE')
            users = cursor.fetchall()
            
            total_updated = 0
            
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
                    new_price = parser.get_product_price_correct(url)
                    
                    if new_price > 0 and new_price != old_price:
                        # Обновляем цену
                        cursor.execute('''
                            UPDATE products 
                            SET current_price = ?, last_check = ?
                            WHERE id = ?
                        ''', (new_price, datetime.now(), product_id))
                        
                        total_updated += 1
                        
                        # Отправляем уведомление
                        if new_price <= target_price:
                            bot.send_message(user_id,
                                            f"ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                            f"{name}\n"
                                            f"Новая цена: {new_price} руб.\n"
                                            f"Цель: {target_price} руб.")
                        else:
                            bot.send_message(user_id,
                                            f"Цена изменилась\n\n"
                                            f"{name}\n"
                                            f"Было: {old_price} руб.\n"
                                            f"Стало: {new_price} руб.")
                    
                    # Задержка между запросами
                    time.sleep(5)
            
            conn.commit()
            conn.close()
            
            print(f"Автоматическая проверка завершена. Обновлено: {total_updated} цен")
            
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

# Обработка завершения работы
import atexit

@atexit.register
def cleanup():
    """Очистка при завершении работы"""
    print("Завершение работы GGsel бота...")
    if parser:
        parser.close()

# Главная функция
if __name__ == '__main__':
    print("Запуск исправленного бота GGsel...")
    
    init_db()
    
    if parser and parser.driver:
        print("Бот запущен и готов к работе!")
        print("Используйте /search для поиска товаров")
        # Запускаем фоновые задачи только если парсер работает
        start_background_jobs()
    else:
        print("Бот запущен без парсера")
        print("Поиск товаров будет недоступен")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Ошибка бота: {e}")
    finally:
        if parser:
            parser.close()