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
import os
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

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

# Реальный парсер Яндекс Маркета с улучшенным парсингом
class YandexMarketParser:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.init_driver()
    
    def init_driver(self):
        """Инициализация Chrome драйвера с автоматической установкой"""
        try:
            print("🔄 Инициализация Chrome драйвера...")
            
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
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-images")  # Ускоряет загрузку
            
            # Автоматическая установка ChromeDriver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("✅ Chrome драйвер успешно инициализирован")
            
        except Exception as e:
            print(f"❌ Ошибка инициализации Chrome драйвера: {e}")
            self.driver = None
    
    def save_debug_screenshot(self, filename):
        """Сохранить скриншот для отладки"""
        if not self.driver:
            return None
            
        debug_dir = "debug_pages"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        
        filepath = os.path.join(debug_dir, filename)
        self.driver.save_screenshot(filepath)
        print(f"📸 Сохранен скриншот: {filepath}")
        return filepath
    
    def save_debug_html(self, filename):
        """Сохранить HTML для отладки"""
        if not self.driver:
            return None
            
        debug_dir = "debug_pages"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        
        filepath = os.path.join(debug_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        print(f"💾 Сохранен HTML: {filepath}")
        return filepath

    def search_products(self, query, max_results=5):
        """
        Реальный поиск товаров на Яндекс Маркете
        """
        if not self.driver:
            return ["selenium_error"]
        
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://market.yandex.ru/search?text={encoded_query}&how=aprice"
            
            print(f"\n🔍 Начинаем реальный поиск: '{query}'")
            print(f"🌐 URL: {url}")
            
            # Загружаем страницу
            self.driver.get(url)
            
            # Ждем загрузки страницы
            time.sleep(8)
            
            # Сохраняем скриншот и HTML для отладки
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.save_debug_screenshot(f"search_{timestamp}_{query[:10]}.png")
            self.save_debug_html(f"search_{timestamp}_{query[:10]}.html")
            
            # Проверяем на капчу
            page_text = self.driver.page_source.lower()
            if any(word in page_text for word in ['капча', 'captcha', 'робот', 'проверка']):
                print("🚨 Обнаружена капча!")
                return ["captcha"]
            
            # Прокручиваем страницу для загрузки всех товаров
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            # Парсим реальные товары
            products = self.parse_real_products(max_results)
            
            print(f"✅ Найдено товаров: {len(products)}")
            return products
            
        except Exception as e:
            print(f"💥 Ошибка при реальном поиске: {e}")
            return ["error"]

    def parse_real_products(self, max_results):
        """Парсинг реальных товаров с Яндекс Маркета"""
        products = []
        
        try:
            # Получаем весь HTML страницы
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Ищем карточки товаров - основные селекторы Яндекс Маркета 2024
            product_selectors = [
                '[data-zone-name="snippet"]',
                '[data-autotest-id="product-snippet"]',
                '.snippet-cell',
                '.snippet-horizontal',
                'article[data-zone-name="snippet"]',
                'div[data-zone-name="snippet"]'
            ]
            
            product_cards = []
            for selector in product_selectors:
                found_cards = soup.select(selector)
                print(f"🔍 Селектор '{selector}': найдено {len(found_cards)} элементов")
                if found_cards:
                    product_cards = found_cards
                    break
            
            # Если не нашли стандартными селекторами, ищем по структуре
            if not product_cards:
                product_cards = soup.find_all('div', class_=lambda x: x and any(word in str(x).lower() for word in ['snippet', 'product', 'item', 'offer']))
                print(f"🔍 Альтернативный поиск: {len(product_cards)} карточек")
            
            print(f"🛍 Всего найдено карточек: {len(product_cards)}")
            
            for i, card in enumerate(product_cards[:max_results]):
                print(f"   Парсим карточку {i+1}...")
                product = self.parse_product_card_advanced(card)
                if product and product['name'] and product['price'] > 0:
                    products.append(product)
                    print(f"   ✅ Добавлен товар: {product['name'][:50]}... - {product['price']} руб.")
                elif product:
                    print(f"   ❌ Пропущен товар: нет названия или цены")
            
            return products
            
        except Exception as e:
            print(f"💥 Ошибка парсинга реальных товаров: {e}")
            return []

    def parse_product_card_advanced(self, card):
        """Улучшенный парсинг карточки товара"""
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
                '[data-zone-name="title"] a',
                'a[data-zone-name="title"]',
                '.snippet-cell__title a',
                'a.snippet-title'
            ]
            
            for selector in name_selectors:
                name_elem = card.select_one(selector)
                if name_elem:
                    product['name'] = name_elem.get_text(strip=True)
                    href = name_elem.get('href')
                    if href:
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = 'https://market.yandex.ru' + href
                        product['link'] = href
                    break
            
            # Если название не нашли, ищем в других местах
            if not product['name']:
                # Ищем в data-атрибутах
                name_data = card.get('data-zone-data')
                if name_data:
                    try:
                        data = json.loads(name_data)
                        if 'title' in data:
                            product['name'] = data['title']
                    except:
                        pass
            
            # Цена - ищем в различных местах
            price_selectors = [
                '[data-zone-name="price"]',
                '.snippet-price',
                '.price',
                '.snippet-cell__price',
                '[automation-id="price"]',
                '.snippet-price__text',
                '.snippet-price__value'
            ]
            
            for selector in price_selectors:
                price_elem = card.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Ищем число в тексте цены
                    price_match = re.search(r'(\d[\d\s]*)', price_text.replace(' ', ''))
                    if price_match:
                        try:
                            product['price'] = float(price_match.group(1).replace(' ', ''))
                            break
                        except ValueError:
                            continue
            
            # Если цена не найдена, ищем в data-атрибутах
            if product['price'] == 0:
                price_data = card.get('data-zone-data')
                if price_data:
                    try:
                        data = json.loads(price_data)
                        if 'price' in data:
                            product['price'] = float(data['price'])
                    except:
                        pass
            
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
            img_selectors = [
                'img',
                '.snippet-image img',
                '[data-zone-name="picture"] img'
            ]
            
            for selector in img_selectors:
                img_elem = card.select_one(selector)
                if img_elem:
                    src = img_elem.get('src') or img_elem.get('data-src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        product['image'] = src
                        break
            
            # Проверяем, что товар валидный
            if not product['name'] or product['price'] == 0:
                return None
                
            return product
            
        except Exception as e:
            print(f"💥 Ошибка парсинга карточки: {e}")
            return None

    def get_product_price(self, product_url):
        """Получение реальной цены товара по ссылке"""
        if not self.driver:
            return 0
            
        try:
            print(f"💰 Получаю реальную цену для: {product_url}")
            
            if not product_url.startswith('http'):
                product_url = 'https://market.yandex.ru' + product_url
            
            self.driver.get(product_url)
            time.sleep(6)
            
            # Сохраняем для отладки
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.save_debug_screenshot(f"price_{timestamp}.png")
            self.save_debug_html(f"price_{timestamp}.html")
            
            # Парсим цену со страницы товара
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Ищем цену в различных местах
            price_selectors = [
                '[data-zone-name="price"]',
                '.price',
                '[automation-id="price"]',
                '.snippet-price',
                '.product-price__value',
                '.product-price__current'
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d\s]*)', price_text.replace(' ', ''))
                    if price_match:
                        try:
                            price = float(price_match.group(1).replace(' ', ''))
                            print(f"✅ Найдена реальная цена: {price} руб.")
                            return price
                        except ValueError:
                            continue
            
            print("❌ Цена не найдена на странице товара")
            return 0
            
        except Exception as e:
            print(f"💥 Ошибка получения реальной цены: {e}")
            return 0
    
    def close(self):
        """Закрыть браузер"""
        if self.driver:
            self.driver.quit()
            print("✅ Браузер закрыт")

# Создаем парсер
try:
    parser = YandexMarketParser(headless=True)
    print("✅ Парсер инициализирован в РЕАЛЬНОМ режиме")
except Exception as e:
    print(f"❌ Ошибка инициализации парсера: {e}")
    parser = None

# Команда /start
@bot.message_handler(commands=['start', 'main', 'hello'])
def send_welcome(message):
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    status_text = "⚡ РЕАЛЬНЫЙ РЕЖИМ - работает настоящий поиск!" if parser and parser.driver else "⚠️ ДЕМО-РЕЖИМ - проблемы с браузером"
    
    welcome_text = f"""
 Привет, {user.first_name}!

Я бот для мониторинга цен на Яндекс Маркете.

{status_text}

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
/debug - Диагностика парсера

💡 Бот использует реальный браузер для поиска!
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
    btn5 = types.KeyboardButton('Диагностика')
    markup.add(btn1, btn2)
    markup.add(btn3, btn4, btn5)
    
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

# Команда /help
@bot.message_handler(commands=['help'])
def send_help(message):
    status_text = "⚡ РЕАЛЬНЫЙ РЕЖИМ" if parser and parser.driver else "⚠️ ДЕМО-РЕЖИМ"
    
    help_text = f"""
Доступные команды:

/search - Поиск товаров на Яндекс Маркете
/add - Добавить товар для отслеживания
/my_products - Показать отслеживаемые товары
/check - Проверить актуальные цены
/debug - Диагностика парсера

{status_text}

⚡ Реальный парсинг через Selenium:
• Находит настоящие товары
• Получает актуальные цены
• Показывает рейтинги и отзывы
• Сохраняет скриншоты для отладки

Как использовать:
1. Используйте /search для поиска товара
2. Скопируйте ссылку на понравившийся товар
3. Используйте /add чтобы добавить товар для отслеживания
4. Укажите желаемую цену
5. Получайте уведомления при изменении цены!

Бот проверяет цены автоматически каждые 6 часов.
    """
    
    bot.send_message(message.chat.id, help_text)

# Команда диагностики
@bot.message_handler(commands=['debug'])
def debug_parser(message):
    """Диагностика работы парсера"""
    bot.send_message(message.chat.id, "🔧 Запускаю диагностику реального парсера...")
    
    if not parser or not parser.driver:
        bot.send_message(message.chat.id, 
                       "❌ Selenium не доступен\n"
                       "💡 Проверьте установку Chrome и ChromeDriver")
        return
    
    bot.send_message(message.chat.id, 
                   "✅ Selenium доступен\n"
                   "🌐 Браузер запущен\n"
                   "🔍 Тестируем реальный поиск...")
    
    # Тестовый запрос
    test_queries = ["iPhone 15", "ноутбук Asus", "телевизор Samsung"]
    
    for query in test_queries:
        bot.send_message(message.chat.id, f"🔍 Тестируем реальный поиск: '{query}'")
        
        products = parser.search_products(query, max_results=2)
        
        if isinstance(products, list) and len(products) > 0 and isinstance(products[0], str):
            error_msg = products[0]
            if error_msg == "captcha":
                bot.send_message(message.chat.id, 
                               f"❌ '{query}': Обнаружена капча\n\n"
                               "📸 Скриншот сохранен в debug_pages/")
            elif error_msg == "selenium_error":
                bot.send_message(message.chat.id, f"❌ '{query}': Ошибка Selenium")
            else:
                bot.send_message(message.chat.id, f"❌ '{query}': Ошибка - {error_msg}")
        elif products:
            bot.send_message(message.chat.id, f"✅ '{query}': Найдено {len(products)} реальных товаров")
            for product in products[:1]:
                price_text = f"{product['price']} руб." if product['price'] > 0 else "цена не найдена"
                rating_text = f", рейтинг: {product['rating']}" if product['rating'] > 0 else ""
                bot.send_message(message.chat.id, 
                               f"Пример: {product['name'][:60]}...\nЦена: {price_text}{rating_text}")
        else:
            bot.send_message(message.chat.id, f"❌ '{query}': Товары не найдены")
        
        time.sleep(3)
    
    bot.send_message(message.chat.id, 
                    "📊 Диагностика завершена.\n"
                    "📸 Скриншоты и HTML сохранены в папке debug_pages/\n"
                    "👀 Вы можете посмотреть что видит браузер!")

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
    
    elif message.text == 'Диагностика':
        debug_parser(message)
    
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
    
    if not parser or not parser.driver:
        bot.send_message(message.chat.id, 
                       "❌ Парсер не доступен. Используйте /debug для диагностики.")
        return
    
    bot.send_message(message.chat.id, f"🔍 Ищу '{query}' на Яндекс Маркете...\n⚡ Использую реальный браузер...")
    
    try:
        products = parser.search_products(query, max_results=5)
        
        # Обработка специальных случаев
        if isinstance(products, list) and products and isinstance(products[0], str):
            error_type = products[0]
            if error_type == "captcha":
                bot.send_message(message.chat.id, 
                               "⚠️ Обнаружена капча!\n\n"
                               "📸 Скриншот сохранен в debug_pages/\n"
                               "🔄 Попробуйте позже или используйте другой запрос")
                return
            elif error_type == "selenium_error":
                bot.send_message(message.chat.id, "❌ Ошибка браузера. Используйте /debug")
                return
            else:
                bot.send_message(message.chat.id, f"❌ Ошибка поиска: {error_type}")
                return
        
        if not products:
            bot.send_message(message.chat.id, 
                           "❌ Товары не найдены.\n\n"
                           "Возможные причины:\n"
                           "• Неправильный запрос\n"
                           "• Проблемы с сайтом\n"
                           "• Блокировка\n"
                           "📸 Скриншоты сохранены для анализа")
            return
        
        # Отправляем найденные товары
        for i, product in enumerate(products, 1):
            product_text = format_product_info(product, i)
            
            # Если есть изображение, отправляем фото с описанием
            if product.get('image') and product['image'].startswith('http'):
                try:
                    bot.send_photo(message.chat.id, product['image'], 
                                 caption=product_text, parse_mode='HTML')
                except Exception as e:
                    print(f"Ошибка отправки фото: {e}")
                    bot.send_message(message.chat.id, product_text, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, product_text, parse_mode='HTML')
        
        bot.send_message(message.chat.id, 
                        "💡 Чтобы отслеживать товар, скопируйте ссылку и используйте команду /add")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"💥 Произошла ошибка при поиске: {str(e)}")

def format_product_info(product, number=1):
    """Форматирование информации о товаре"""
    rating_text = f"⭐ {product['rating']}" if product['rating'] > 0 else "⭐ Нет оценок"
    reviews_text = f"📝 {product['reviews']} отзывов" if product['reviews'] > 0 else "📝 Нет отзывов"
    shop_text = f"🏪 {product['shop']}" if product.get('shop') else "🏪 Магазин не указан"
    
    return f"""
<b>Товар #{number}</b>
<b>{product['name']}</b>
💰 <b>Цена: {product['price']:,} ₽</b>
{rating_text} | {reviews_text}
{shop_text}
🔗 <a href="{product['link']}">Ссылка на товар</a>
    """.replace(',', ' ')

# Добавление товара для отслеживания
@bot.message_handler(commands=['add'])
def add_product(message):
    if not parser or not parser.driver:
        bot.send_message(message.chat.id, "❌ Парсер не доступен. Используйте /debug для диагностики.")
        return
        
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
    bot.send_message(message.chat.id, "⚡ Получаю информацию о товаре через реальный браузер...")
    
    current_price = parser.get_product_price(url)
    
    if current_price == 0:
        bot.send_message(message.chat.id, 
                        "❌ Не удалось получить цену товара.\n\n"
                        "Возможные причины:\n"
                        "• Товар временно недоступен\n"
                        "• Изменилась структура сайта\n"
                        "• Капча или блокировка\n"
                        "📸 Скриншот сохранен для анализа")
        return
    
    # Получаем название товара
    product_name = f"Товар с Яндекс Маркета ({current_price} руб.)"
    
    # Сохраняем URL и запрашиваем целевую цену
    bot.send_message(message.chat.id, 
                    f"💰 Текущая цена: {current_price} ₽\n\n"
                    f"🎯 Укажите целевую цену (в рублях):\n"
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
        
        status = "🎉 Уже достигнута!" if current_price <= target_price else "⏳ Ожидание"
        
        bot.send_message(message.chat.id,
                        f"✅ Товар добавлен для отслеживания!\n\n"
                        f"{product_name}\n"
                        f"💰 Текущая цена: {current_price} ₽\n"
                        f"🎯 Целевая цена: {target_price} ₽\n"
                        f"📊 Статус: {status}\n\n"
                        f"Бот будет уведомлять вас при изменении цены!")
        
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат цены. Введите число (например: 5000)")

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
        
        status = "🎉 Цена достигнута!" if current_price <= target_price else "⏳ Ожидание"
        
        product_info = f"""
<b>Товар #{product_id}</b>
{name}
💰 Текущая цена: <b>{current_price:,} ₽</b>
🎯 Целевая цена: <b>{target_price:,} ₽</b>
📊 Статус: {status}
🕒 Последняя проверка: {last_check}
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
    
    cursor.execute('SELECT product_url, current_price, product_name, target_price FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if product:
        product_url, old_price, product_name, target_price = product
        
        if not parser or not parser.driver:
            bot.send_message(message.chat.id, "❌ Парсер не доступен.")
            conn.close()
            return
            
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
                                f"🎉 ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                f"{product_name}\n"
                                f"💰 Новая цена: {new_price} ₽\n"
                                f"🎯 Цель: {target_price} ₽\n"
                                f"📊 Было: {old_price} ₽")
            elif new_price != old_price:
                bot.send_message(message.chat.id, 
                                f"📈 ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                f"{product_name}\n"
                                f"📊 Было: {old_price} ₽\n"
                                f"💰 Стало: {new_price} ₽")
            else:
                bot.send_message(message.chat.id, 
                                f"✅ Цена не изменилась\n\n"
                                f"{product_name}\n"
                                f"💰 Текущая цена: {new_price} ₽")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось получить актуальную цену")
    
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
    
    if not parser or not parser.driver:
        bot.send_message(message.chat.id, "❌ Парсер не доступен. Используйте /debug для диагностики.")
        return
        
    bot.send_message(message.chat.id, "🔍 Проверяю цены всех товаров...")
    
    conn = sqlite3.connect('yandex_market.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, product_url, product_name, current_price, target_price
        FROM products 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))
    
    products = cursor.fetchall()
    
    if not products:
        bot.send_message(message.chat.id, "У вас нет товаров для отслеживания.")
        conn.close()
        return
    
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
                                f"{name}\n"
                                f"💰 Новая цена: {new_price} ₽\n"
                                f"🎯 Цель: {target_price} ₽\n"
                                f"🔗 {url}")
            else:
                bot.send_message(message.chat.id,
                                f"📈 ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                f"{name}\n"
                                f"📊 Было: {old_price} ₽\n"
                                f"💰 Стало: {new_price} ₽\n"
                                f"🔗 {url}")
        
        # Задержка между запросами
        time.sleep(5)
    
    conn.commit()
    conn.close()
    
    if updated_count == 0:
        bot.send_message(message.chat.id, "✅ Все цены актуальны!")
    else:
        bot.send_message(message.chat.id, f"📊 Проверка завершена! Обновлено {updated_count} цен.")

# Фоновая задача для автоматической проверки цен
def background_price_checker():
    def job():
        try:
            print(f"\n🕒 Автоматическая проверка цен: {datetime.now()}")
            
            if not parser or not parser.driver:
                print("❌ Парсер не доступен для фоновой проверки")
                return
                
            conn = sqlite3.connect('yandex_market.db')
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
                    new_price = parser.get_product_price(url)
                    
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
                                            f"🎉 ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!\n\n"
                                            f"{name}\n"
                                            f"💰 Новая цена: {new_price} ₽\n"
                                            f"🎯 Цель: {target_price} ₽")
                        else:
                            bot.send_message(user_id,
                                            f"📈 ИЗМЕНЕНИЕ ЦЕНЫ\n\n"
                                            f"{name}\n"
                                            f"📊 Было: {old_price} ₽\n"
                                            f"💰 Стало: {new_price} ₽")
                    
                    # Задержка между запросами
                    time.sleep(10)
            
            conn.commit()
            conn.close()
            
            print(f"✅ Автоматическая проверка завершена. Обновлено: {total_updated} цен")
            
        except Exception as e:
            print(f"💥 Ошибка в фоновой задаче: {e}")
    
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
    print("🔄 Завершение работы...")
    if parser:
        parser.close()

# Главная функция
if __name__ == '__main__':
    print("🚀 Запуск бота мониторинга Яндекс Маркета...")
    print("⚡ РЕАЛЬНЫЙ РЕЖИМ - настоящий парсинг через Selenium!")
    print("📸 Скриншоты будут сохраняться в папку debug_pages/")
    
    # Создаем папку для отладки
    if not os.path.exists("debug_pages"):
        os.makedirs("debug_pages")
    
    init_db()
    start_background_jobs()
    
    if parser and parser.driver:
        print("✅ Бот запущен в РЕАЛЬНОМ режиме!")
        print("🔍 Парсер готов к поиску товаров")
    else:
        print("⚠️ Бот запущен с ограниченным функционалом")
        print("💡 Используйте /debug для диагностики")
    
    print("📝 Используйте команду /search для начала работы")
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("⏹ Остановка бота...")
    finally:
        if parser:
            parser.close()