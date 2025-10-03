import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Токен бота от @BotFather
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    
    # API ключ GGSell (если доступен)
    GGSELL_API_KEY = os.getenv('GGSELL_API_KEY', '')
    
    # Настройки базы данных
    DATABASE_URL = 'ggsell_monitor.db'
    
    # Интервал проверки цен (в часах)
    CHECK_INTERVAL_HOURS = 4
    
    # Настройки логирования
    LOG_LEVEL = 'INFO'
    
    # User-Agent для запросов
    USER_AGENT = 'GGSellPriceMonitorBot/1.0'