import telebot
import requests
from bs4 import BeautifulSoup
import schedule
import time
import threading
import sqlite3
from datetime import datetime
import logging
import re
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Токен бота (получите у @BotFather)
BOT_TOKEN = ""

# Создание бота
bot = telebot.TeleBot(BOT_TOKEN)

# База данных для хранения отслеживаемых товаров
def init_db():
    conn = sqlite3.connect('ggsel_monitor.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracked_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_url TEXT,
            product_name TEXT,
            current_price REAL,
            last_check TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_url TEXT,
            price REAL,
            check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Функция для получения цены товара с GGsel
def get_ggsel_price(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Способ 1: Поиск в JSON-LD структурированных данных
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'offers' in data:
                    price = data['offers'].get('price')
                    name = data.get('name')
                    if price and name:
                        return float(price), name
            except:
                continue
        
        # Способ 2: Поиск по классам и атрибутам
        name = "Неизвестный товар"
        name_selectors = [
            'h1.product-name',
            'h1.product-title', 
            'h1.title',
            '.product-name',
            '.product-title',
            '[class*="product-name"]',
            'h1'
        ]
        
        for selector in name_selectors:
            name_element = soup.select_one(selector)
            if name_element and name_element.get_text().strip():
                name = name_element.get_text().strip()
                break
        
        # Способ 3: Поиск цены - расширенные селекторы
        price = None
        price_selectors = [
            '.product-price .price',
            '.price-current',
            '.product-price',
            '.cost',
            '.price',
            '[class*="price"]',
            '.product-cost',
            '.current-price',
            '.product__price',
            '.goods__price',
            '.item__price'
        ]
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for element in price_elements:
                price_text = element.get_text().strip()
                if price_text:
                    # Ищем числа в тексте
                    price_match = re.search(r'(\d+[\s\d]*(?:[.,]\d+)?)', price_text.replace(',', '.'))
                    if price_match:
                        try:
                            price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
                            price = float(price_str)
                            logging.info(f"Найдена цена через селектор {selector}: {price}")
                            return price, name
                        except ValueError:
                            continue
        
        # Способ 4: Поиск через data-атрибуты
        price_elements = soup.find_all(attrs={"data-price": True})
        for element in price_elements:
            try:
                price = float(element['data-price'])
                logging.info(f"Найдена цена через data-атрибут: {price}")
                return price, name
            except (ValueError, KeyError):
                continue
        
        # Способ 5: Поиск в meta-тегах
        meta_price = soup.find('meta', property='product:price')
        if meta_price and meta_price.get('content'):
            try:
                price = float(meta_price['content'])
                logging.info(f"Найдена цена через meta-тег: {price}")
                return price, name
            except ValueError:
                pass
        
        # Способ 6: Поиск по структуре GGsel
        # Попробуем найти любой элемент с ценой
        all_elements = soup.find_all(text=re.compile(r'\d+\s*\d*[.,]?\d*\s*[₽рр]'))
        for element in all_elements:
            price_match = re.search(r'(\d+[\s\d]*(?:[.,]\d+)?)', element.replace(',', '.'))
            if price_match:
                try:
                    price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
                    price = float(price_str)
                    logging.info(f"Найдена цена через текстовый поиск: {price}")
                    return price, name
                except ValueError:
                    continue
        
        logging.warning(f"Не удалось найти цену для {url}")
        return None, name
        
    except Exception as e:
        logging.error(f"Ошибка при получении цены для {url}: {e}")
        return None, None

# Команда старт
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
🤖 Добро пожаловать в монитор цен GGsel!

Доступные команды:
/add <url> - Добавить товар для отслеживания
/list - Показать отслеживаемые товары
/check <id> - Проверить цену конкретного товара
/remove <id> - Удалить товар из отслеживания
/help - Показать справку

Просто отправьте ссылку на товар с GGsel для быстрого добавления!

Поддерживаемые домены: ggsel.net, ggsel.com, ggsell.net
    """
    bot.reply_to(message, welcome_text)

# Команда помощи
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
📖 Справка по использованию бота:

1. Чтобы добавить товар для отслеживания:
   - Используйте команду /add <ссылка>
   - Или просто отправьте ссылку на товар

2. Для просмотра всех отслеживаемых товаров:
   - Используйте команду /list

3. Чтобы проверить цену конкретного товара:
   - Используйте команду /check <ID товара>

4. Чтобы удалить товар из отслеживания:
   - Используйте команду /remove <ID товара>

Примеры:
/add https://ggsel.net/example-product
/list
/check 1
/remove 1
    """
    bot.reply_to(message, help_text)

# Добавление товара для отслеживания
@bot.message_handler(commands=['add'])
def add_product(message):
    try:
        # Извлекаем URL из команды
        if len(message.text.split()) < 2:
            bot.reply_to(message, "❌ Пожалуйста, укажите ссылку на товар.\nПример: /add https://ggsel.net/example-product")
            return
        
        url = message.text.split()[1]
        
        # Проверяем, что это ссылка на GGsel (обновленные домены)
        allowed_domains = ['ggsel.net', 'ggsel.com', 'ggsell.net']
        if not any(domain in url for domain in allowed_domains):
            bot.reply_to(message, "❌ Пожалуйста, используйте ссылки только с сайтов GGsel:\n- ggsel.net\n- ggsel.com\n- ggsell.net")
            return
        
        # Показываем сообщение о начале обработки
        processing_msg = bot.reply_to(message, "⏳ Получаю информацию о товаре...")
        
        # Получаем текущую цену
        price, name = get_ggsel_price(url)
        
        # Удаляем сообщение о обработке
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
        
        if price is None:
            bot.reply_to(message, "❌ Не удалось получить информацию о товаре. Возможные причины:\n• Товар недоступен\n• Изменилась структура сайта\n• Проблемы с подключением\n\nПопробуйте позже или свяжитесь с разработчиком.")
            return
        
        # Сохраняем в базу данных
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tracked_products (user_id, product_url, product_name, current_price, last_check)
            VALUES (?, ?, ?, ?, ?)
        ''', (message.chat.id, url, name, price, datetime.now()))
        
        # Сохраняем в историю цен
        cursor.execute('''
            INSERT INTO price_history (product_url, price)
            VALUES (?, ?)
        ''', (url, price))
        
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Товар добавлен!\n📦 Название: {name}\n💰 Цена: {price} руб.\n🕒 Отслеживание начато!")
        
    except Exception as e:
        logging.error(f"Ошибка при добавлении товара: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при добавлении товара.")

# Быстрое добавление по ссылке
@bot.message_handler(func=lambda message: any(domain in message.text for domain in ['ggsel.net', 'ggsel.com', 'ggsell.net']) and not message.text.startswith('/'))
def quick_add_product(message):
    try:
        url = message.text.strip()
        
        # Проверяем, что это действительно ссылка
        if not url.startswith('http'):
            return
        
        # Показываем сообщение о начале обработки
        processing_msg = bot.reply_to(message, "⏳ Получаю информацию о товаре...")
        
        # Получаем текущую цену
        price, name = get_ggsel_price(url)
        
        # Удаляем сообщение о обработке
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
        
        if price is None:
            bot.reply_to(message, "❌ Не удалось получить информацию о товаре. Возможные причины:\n• Товар недоступен\n• Изменилась структура сайта\n• Проблемы с подключением")
            return
        
        # Сохраняем в базу данных
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tracked_products (user_id, product_url, product_name, current_price, last_check)
            VALUES (?, ?, ?, ?, ?)
        ''', (message.chat.id, url, name, price, datetime.now()))
        
        # Сохраняем в историю цен
        cursor.execute('''
            INSERT INTO price_history (product_url, price)
            VALUES (?, ?)
        ''', (url, price))
        
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Товар добавлен!\n📦 Название: {name}\n💰 Цена: {price} руб.\n🕒 Отслеживание начато!")
        
    except Exception as e:
        logging.error(f"Ошибка при быстром добавлении товара: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при добавлении товара.")

# Остальные функции остаются без изменений (list, check, remove, auto_check_prices, etc.)
# ... [остальной код без изменений] ...

# Показать список отслеживаемых товаров
@bot.message_handler(commands=['list'])
def list_products(message):
    try:
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, product_name, current_price, last_check 
            FROM tracked_products 
            WHERE user_id = ?
        ''', (message.chat.id,))
        
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            bot.reply_to(message, "📭 У вас нет отслеживаемых товаров.")
            return
        
        response = "📋 Ваши отслеживаемые товары:\n\n"
        for product in products:
            product_id, name, price, last_check = product
            # Обрабатываем разные форматы timestamp
            try:
                if '.' in last_check:
                    last_check_formatted = datetime.strptime(last_check, '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m.%Y %H:%M')
                else:
                    last_check_formatted = datetime.strptime(last_check, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            except:
                last_check_formatted = last_check
            
            response += f"🆔 ID: {product_id}\n📦 {name}\n💰 {price} руб.\n🕒 Последняя проверка: {last_check_formatted}\n\n"
        
        response += "ℹ️ Используйте /check <ID> для проверки цены или /remove <ID> для удаления."
        bot.reply_to(message, response)
        
    except Exception as e:
        logging.error(f"Ошибка при получении списка товаров: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при получении списка товаров.")

# Проверить цену конкретного товара
@bot.message_handler(commands=['check'])
def check_product(message):
    try:
        if len(message.text.split()) < 2:
            bot.reply_to(message, "❌ Пожалуйста, укажите ID товара.\nПример: /check 1")
            return
        
        product_id = int(message.text.split()[1])
        
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT product_url, product_name, current_price 
            FROM tracked_products 
            WHERE id = ? AND user_id = ?
        ''', (product_id, message.chat.id))
        
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            bot.reply_to(message, "❌ Товар с таким ID не найден.")
            return
        
        url, name, old_price = product
        
        # Получаем актуальную цену
        new_price, _ = get_ggsel_price(url)
        
        if new_price is None:
            conn.close()
            bot.reply_to(message, "❌ Не удалось получить актуальную цену.")
            return
        
        # Обновляем цену в базе
        cursor.execute('''
            UPDATE tracked_products 
            SET current_price = ?, last_check = ? 
            WHERE id = ?
        ''', (new_price, datetime.now(), product_id))
        
        # Сохраняем в историю
        cursor.execute('''
            INSERT INTO price_history (product_url, price)
            VALUES (?, ?)
        ''', (url, new_price))
        
        conn.commit()
        conn.close()
        
        price_change = new_price - old_price
        if price_change < 0:
            change_emoji = "🟢"
            change_text = f"📉 Цена упала на {abs(price_change):.2f} руб."
        elif price_change > 0:
            change_emoji = "🔴"
            change_text = f"📈 Цена выросла на {price_change:.2f} руб."
        else:
            change_emoji = "⚪"
            change_text = "💎 Цена не изменилась"
        
        response = f"📊 Актуальная информация:\n\n📦 {name}\n💰 Цена: {new_price} руб.\n{change_emoji} {change_text}"
        bot.reply_to(message, response)
        
    except Exception as e:
        logging.error(f"Ошибка при проверке товара: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при проверке товара.")

# Удалить товар из отслеживания
@bot.message_handler(commands=['remove'])
def remove_product(message):
    try:
        if len(message.text.split()) < 2:
            bot.reply_to(message, "❌ Пожалуйста, укажите ID товара.\nПример: /remove 1")
            return
        
        product_id = int(message.text.split()[1])
        
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM tracked_products 
            WHERE id = ? AND user_id = ?
        ''', (product_id, message.chat.id))
        
        if cursor.rowcount == 0:
            conn.close()
            bot.reply_to(message, "❌ Товар с таким ID не найден.")
            return
        
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Товар с ID {product_id} удален из отслеживания.")
        
    except Exception as e:
        logging.error(f"Ошибка при удалении товара: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при удалении товара.")

# Функция для автоматической проверки цен
def auto_check_prices():
    try:
        conn = sqlite3.connect('ggsel_monitor.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, user_id, product_url, product_name, current_price FROM tracked_products')
        products = cursor.fetchall()
        
        for product in products:
            product_id, user_id, url, name, old_price = product
            
            new_price, _ = get_ggsel_price(url)
            
            if new_price is not None and new_price != old_price:
                # Цена изменилась, отправляем уведомление
                price_change = new_price - old_price
                if price_change < 0:
                    change_emoji = "🟢"
                    change_text = f"упала на {abs(price_change):.2f} руб."
                else:
                    change_emoji = "🔴" 
                    change_text = f"выросла на {price_change:.2f} руб."
                
                message = f"{change_emoji} Цена изменилась!\n\n📦 {name}\n💰 Было: {old_price} руб.\n💰 Стало: {new_price} руб.\n📊 {change_text}"
                
                try:
                    bot.send_message(user_id, message)
                except Exception as e:
                    logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
                
                # Обновляем цену в базе
                cursor.execute('''
                    UPDATE tracked_products 
                    SET current_price = ?, last_check = ? 
                    WHERE id = ?
                ''', (new_price, datetime.now(), product_id))
                
                # Сохраняем в историю
                cursor.execute('''
                    INSERT INTO price_history (product_url, price)
                    VALUES (?, ?)
                ''', (url, new_price))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка при автоматической проверке цен: {e}")

# Функция для запуска планировщика
def run_scheduler():
    # Проверка каждые 30 минут
    schedule.every(30).minutes.do(auto_check_prices)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск бота
if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    logging.info("Бот запущен!")
    
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Ошибка при работе бота: {e}")