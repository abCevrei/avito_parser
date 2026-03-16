# %%
import requests
from bs4 import BeautifulSoup
import os
import json
import re
import time
from datetime import datetime
from aiogram import Bot
from dotenv import load_dotenv
import random

load_dotenv()

# Railway сам дает переменные окружения
# ========== НАСТРОЙКИ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TG_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID")
AVITO_URL = os.environ.get("AVITO_URL")
AVITO_URL = "https://www.avito.ru/bashkortostan/avtomobili/do-400000-rubley-ASgCAgECAUXGmgwWeyJmcm9tIjowLCJ0byI6NDAwMDAwfQ?f=ASgBAgECA0SeEqaqjQP2xA2~sDrs6hSSmZADAkX~KRl7ImZyb20iOm51bGwsInRvIjoxODAwMDB9xpoMFnsiZnvbSI6MCwidG8iOjQwMDAwMH0&localPriority=0"

SEEN_FILE = "seen_cars.json"
CHECK_INTERVAL = 3600  # 1 час (чтобы точно не блокировали)
# ===============================

bot = Bot(token=TELEGRAM_BOT_TOKEN)

def load_seen():
    """Загружает ID отправленных машин"""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            try:
                return set(json.load(f))
            except:
                return set()
    return set()

def save_seen(ids):
    """Сохраняет ID отправленных машин"""
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(ids), f, ensure_ascii=False, indent=2)

def get_page(url):
    """Получает страницу с Avito (синхронно)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
    }
    
    try:
        # Большая случайная задержка
        delay = random.randint(30, 60)
        print(f"⏳ Ожидание {delay} секунд...")
        time.sleep(delay)
        
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 Статус: {response.status_code}")
        
        if response.status_code == 200:
            return response.text
        elif response.status_code == 429:
            print("⚠️ Avito блокирует запросы. Жду 5 минут...")
            time.sleep(300)  # 5 минут
            return get_page(url)  # Пробуем снова
        else:
            print(f"❌ Ошибка: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def parse_cars(html):
    """Парсит машины из HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    cars = []
    
    # Ищем карточки
    items = soup.find_all('div', {'data-marker': 'item'})
    
    if not items:
        items = soup.select('[data-marker="item"]')
    
    print(f"📦 Найдено карточек: {len(items)}")
    
    for item in items:
        try:
            # ID и ссылка
            link = item.find('a', href=True)
            if not link:
                continue
                
            href = link.get('href', '')
            id_match = re.search(r'/(\d+)$', href) or re.search(r'_(\d+)$', href)
            if not id_match:
                continue
            car_id = id_match.group(1)
            
            # Название
            title = item.find('h3')
            if not title:
                title = item.find('span', {'class': re.compile('title')})
            title_text = title.text.strip() if title else "Без названия"
            
            # Цена
            price_elem = item.find('meta', {'itemprop': 'price'})
            if price_elem:
                price = price_elem.get('content', '0') + ' ₽'
            else:
                price_elem = item.find('span', {'class': re.compile('price')})
                price = price_elem.text.strip() if price_elem else "Цена не указана"
            
            # Параметры
            params = []
            param_elems = item.find_all('li', {'class': re.compile('params')})
            for p in param_elems[:3]:
                params.append(p.text.strip())
            
            # Фото
            img = item.find('img')
            image = None
            if img:
                image = img.get('src') or img.get('data-src')
                if image and image.startswith('//'):
                    image = 'https:' + image
            
            # Полная ссылка
            full_url = f"https://www.avito.ru{href}" if href.startswith('/') else href
            
            # Проверяем, что машина из Башкортостана
            if 'bashkortostan' not in full_url and 'ufa' not in full_url.lower():
                print(f"   ⏭ Не из Башкортостана: {full_url}")
                continue
            
            cars.append({
                'id': car_id,
                'title': title_text,
                'price': price,
                'url': full_url,
                'image': image,
                'params': params
            })
            
            print(f"   ✅ {title_text[:50]}... - {price}")
            
        except Exception as e:
            print(f"⚠️ Ошибка парсинга: {e}")
            continue
    
    return cars

def send_telegram(car):
    """Отправляет сообщение в Telegram"""
    try:
        text = f"🚗 <b>{car['title']}</b>\n\n"
        text += f"💰 <b>{car['price']}</b>\n"
        
        if car['params']:
            text += "\n📊 " + "\n📊 ".join(car['params']) + "\n"
        
        text += f"\n🔗 <a href='{car['url']}'>Открыть на Avito</a>"
        
        # Используем requests для отправки
        if car['image'] and car['image'].startswith('http'):
            # Пробуем отправить с фото
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'photo': car['image'],
                'caption': text,
                'parse_mode': 'HTML'
            }
            response = requests.post(photo_url, data=data)
            if response.status_code != 200:
                # Если фото не отправилось, шлём текст
                text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': text,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': False
                }
                requests.post(text_url, data=data)
        else:
            # Отправляем только текст
            text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            requests.post(text_url, data=data)
        
        print(f"✅ Отправлено: {car['title'][:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

def check_avito():
    """Основная функция проверки"""
    print(f"\n{'='*60}")
    print(f"🔍 ПРОВЕРКА: {datetime.now().strftime('%H:%M:%S')}")
    print(f"📍 Башкортостан, до 400 000 ₽")
    print(f"{'='*60}")
    
    seen = load_seen()
    
    # Получаем страницу
    html = get_page(AVITO_URL)
    if not html:
        print("❌ Не удалось загрузить страницу")
        return
    
    # Парсим машины
    cars = parse_cars(html)
    print(f"\n📊 Найдено машин в Башкортостане: {len(cars)}")
    
    # Отправляем новые
    new_count = 0
    for car in cars:
        if car['id'] not in seen:
            if send_telegram(car):
                seen.add(car['id'])
                new_count += 1
                time.sleep(5)  # Пауза между отправками
    
    if new_count > 0:
        save_seen(seen)
        print(f"\n✨ Отправлено новых: {new_count}")
    else:
        print(f"\n📭 Новых машин нет")

def main():
    print("\n" + "🚗"*30)
    print("🚗 ПАРСЕР AVITO (ПРОСТАЯ ВЕРСИЯ)")
    print("🚗"*30)
    print(f"Регион: Башкортостан")
    print(f"Цена: до 400 000 ₽")
    print(f"Интервал: {CHECK_INTERVAL//3600} час")
    print("🚗"*30 + "\n")
    
    while True:
        try:
            check_avito()
            
            # Ждём до следующей проверки
            print(f"\n💤 Следующая проверка через {CHECK_INTERVAL//3600} час...")
            
            # Разбиваем ожидание на минуты
            for i in range(CHECK_INTERVAL // 60):
                time.sleep(60)
                if i % 10 == 0:
                    print(f"⏳ Осталось {CHECK_INTERVAL//60 - i} минут...")
                    
        except KeyboardInterrupt:
            print("\n👋 Программа остановлена")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            print("💡 Перезапуск через 5 минут...")
            time.sleep(300)

if __name__ == "__main__":
    main()
