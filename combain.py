#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import sqlite3
import random
import re
import requests
import urllib3
from datetime import datetime
from urllib.parse import quote
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== НАСТРОЙКИ ==========
TELEGRAM_BOT_TOKEN = "8300024794:AAHSkOz6kXKPOfqQt0qtrKPJo2oryh301hg"
TELEGRAM_CHANNEL_ID = "@kafedra_vizhivaniya"
MAX_TOPICS_IN_MEMORY = 100
# =================================

print("📚 НЕЙРОСЕТЕВОЙ КОМБАЙН — КАФЕДРА ВЫЖИВАНИЯ")
print("🤖 GPT-4o-mini + Flux | Учебный контент\n")


class MemoryDB:
    def __init__(self, db_path="memory.db"):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE IF NOT EXISTS used_topics (id INTEGER PRIMARY KEY, topic TEXT, used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic ON used_topics(topic)')
            conn.commit()
            conn.close()

    def is_used(self, topic):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM used_topics WHERE topic = ?", (topic,))
            result = cursor.fetchone() is not None
            conn.close()
            return result

    def add(self, topic):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO used_topics (topic) VALUES (?)", (topic,))
            conn.commit()
            conn.close()

    def get_stats(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM used_topics")
            count = cursor.fetchone()[0]
            conn.close()
            return count


def get_topics():
    default = [
        "Витаминка мотивации: Запускаем неделю!",
        "Конспект-карточка: Теория множеств за 3 минуты",
        "Инструмент в деле: Умные шаблоны для конспектов в Notion",
        "Лайфхак сессии: Метод Фейнмана для быстрого понимания темы",
        "Вопрос-ответ: Какой предмет самый сложный?",
        "Без паники: Как написать введение к курсовой за 30 минут",
        "Инструмент в деле: Учим слова с Anki без мучений",
        "5 приёмов тайм-менеджмента, которые работают в сессию"
    ]
    try:
        with open("topics.json", "r", encoding="utf-8") as f:
            topics = json.load(f)
            if not topics:
                topics = default
    except:
        topics = default
        with open("topics.json", "w", encoding="utf-8") as f:
            json.dump(topics, f, ensure_ascii=False, indent=2)
    return topics


def save_topics(topics):
    with open("topics.json", "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)


def get_next_topic():
    topics = get_topics()
    if not topics:
        return None
    topic = topics.pop(0)
    save_topics(topics)
    return topic


def get_post_type(topic):
    t = topic.lower()
    if "конспект" in t:
        return "notes"
    elif "лайфхак" in t or "совет" in t:
        return "lifehack"
    elif "инструмент" in t or "программа" in t or "приложение" in t:
        return "tool"
    elif "мотивация" in t or "витаминка" in t:
        return "motivation"
    elif "опрос" in t or "вопрос-ответ" in t:
        return "poll"
    elif "без паники" in t:
        return "calm"
    else:
        return "general"


def clean_post(text):
    if not text:
        return text
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line_lower = line.lower()
        if 'proxy' in line_lower and 'cheaper' in line_lower:
            continue
        if 'op.wtf' in line_lower:
            continue
        if line.strip():
            clean_lines.append(line.strip())
    result = '\n'.join(clean_lines)
    result = re.sub(r'Need proxies.*$', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'https?://op\.wtf.*$', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def generate_post_with_gpt(topic):
    print("📝 GPT-4o-mini пишет пост...")

    try:
        from g4f.client import Client
        client = Client()
    except ImportError:
        print("❌ Установите g4f: pip install -U g4f[all]")
        return None

    post_type = get_post_type(topic)

    prompts = {
        "notes": f"""Ты автор учебного Telegram-канала. Напиши краткий понятный конспект на тему: {topic}

Формат:
- Используй списки и эмодзи
- Разбивай на смысловые блоки
- В конце добавь хэштег #конспект
- Длина: 350-500 символов

Пост:""",

        "lifehack": f"""Ты автор учебного Telegram-канала. Напиши короткий практичный лайфхак на тему: {topic}

Формат:
- Один чёткий совет
- По делу, без воды
- С эмодзи
- В конце хэштег #лайфхак
- Длина: 200-350 символов

Пост:""",

        "tool": f"""Ты автор учебного Telegram-канала. Опиши полезный инструмент (программу, приложение, фишку) на тему: {topic}

Формат:
- Что это и зачем
- Как использовать (кратко)
- Эмодзи
- В конце хэштег #инструмент
- Длина: 300-450 символов

Пост:""",

        "motivation": f"""Ты автор учебного Telegram-канала. Напиши короткий мотивирующий пост на тему: {topic}

Формат:
- Яркий, дружелюбный
- Поддерживающий тон
- Эмодзи
- В конце хэштег #мотивация
- Длина: 200-350 символов

Пост:""",

        "calm": f"""Ты автор учебного Telegram-канала. Напиши совет по борьбе со стрессом или тайм-менеджменту на тему: {topic}

Формат:
- Конкретный приём
- Без лишних слов
- Эмодзи
- В конце хэштег #безпаники
- Длина: 250-400 символов

Пост:""",

        "general": f"""Ты автор учебного Telegram-канала. Напиши полезный пост для студентов на тему: {topic}

Формат:
- Дружелюбно, с эмодзи
- Практично
- Длина: 300-500 символов

Пост:"""
    }

    prompt_text = prompts.get(post_type, prompts["general"])

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_text}],
                timeout=45
            )
            post = response.choices[0].message.content.strip()
            post = clean_post(post)
            if len(post) > 100:
                print(f"✅ Пост готов ({len(post)} символов)")
                return post
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: {e}")
            time.sleep(3)
    return None


def generate_image_for_post(topic, post_type):
    print("🎨 Flux генерирует картинку...")

    rand_seed = random.randint(1000, 99999)

    if post_type == "notes":
        style = "схема, интеллект-карта, учебные заметки, структура, таблица"
    elif post_type == "lifehack":
        style = "лайфхак, быстрый совет, чек-лист, инфографика, яркие элементы"
    elif post_type == "tool":
        style = "интерфейс программы, приложение, компьютер, утилита, современный гаджет"
    elif post_type == "motivation":
        style = "мотивационная картинка, яркие цвета, вдохновение, цитата, успех"
    elif post_type == "calm":
        style = "спокойствие, отдых, студент расслабляется, мягкие тона"
    else:
        style = "учеба, студенты, книги, ноутбук, современный стиль"

    prompt = f"{topic}, {style}, качественная иллюстрация, сочный цвет, современный дизайн, уникальный стиль ID {rand_seed}"

    encoded = quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&seed={rand_seed}"

    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
            with open("post_image.jpg", "wb") as f:
                f.write(response.content)
            print("✅ Картинка готова")
            return "post_image.jpg"
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    return None


def send_to_telegram(text, image_path=None):
    print("📤 Отправка в Telegram...")
    text = clean_post(text)
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                response = requests.post(url, files={"photo": photo}, data={
                    "chat_id": TELEGRAM_CHANNEL_ID, "caption": text[:1024]
                }, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            response = requests.post(url, json={
                "chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4096]
            }, timeout=30)

        if response.status_code == 200:
            print("✅ Пост опубликован!")
            return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    return False


def run():
    print("=" * 55)
    print(f"🚀 ЗАПУСК: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    memory = MemoryDB()
    used_count = memory.get_stats()
    print(f"📊 Уже опубликовано постов: {used_count}")

    topic = get_next_topic()
    if not topic:
        print("✅ Все темы использованы! Добавьте новые в topics.json")
        return

    print(f"📌 Тема: {topic}")

    if memory.is_used(topic):
        print(f"⚠️ Тема '{topic}' уже публиковалась!")
        return

    print("\n🤖 РАБОТА КОМБАЙНА")
    print("-" * 45)

    post = generate_post_with_gpt(topic)
    if not post:
        print("❌ Не удалось сгенерировать пост")
        return

    print(f"\n📝 Пост:\n{post}\n")

    post_type = get_post_type(topic)
    image = generate_image_for_post(topic, post_type)

    success = send_to_telegram(post, image)

    if success:
        memory.add(topic)

    if image and os.path.exists(image):
        os.remove(image)

    print("=" * 55)
    if success:
        print("✅ КОМБАЙН ОТРАБОТАЛ!")
        remaining = get_topics()
        if remaining:
            print(f"📋 Осталось тем: {len(remaining)}")
    else:
        print("⚠️ ОШИБКА! Проверьте интернет и VPN.")
    print("=" * 55)


if __name__ == "__main__":
    run()
