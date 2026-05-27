#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import sqlite3
import random
import requests
import urllib3
from datetime import datetime
from urllib.parse import quote
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== НАСТРОЙКИ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
MAX_TOPICS_IN_MEMORY = 100

# Hugging Face токен
HF_TOKEN = os.environ.get("HF_TOKEN", "")
# =================================

print("📚 НЕЙРОСЕТЕВОЙ КОМБАЙН — КАФЕДРА ВЫЖИВАНИЯ")
print("🤖 Hugging Face (Mistral) + Flux\n")


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


def generate_post_huggingface(topic):
    """Генерация поста через Hugging Face (Mistral-7B)"""
    print("🤖 Hugging Face генерирует текст...")

    post_type = get_post_type(topic)
    topic_clean = topic.split(":")[-1].strip()

    system_prompt = f"""Ты автор учебного Telegram-канала. Напиши пост для студентов. Тип поста: {post_type}. Тема: {topic_clean}.

Формат:
- Длина: 250-450 символов
- Используй эмодзи
- Дружелюбный, поддерживающий тон
- В конце хэштег (например #мотивация, #конспект, #лайфхак, #инструмент, #безпаники)

Пост:"""

    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": system_prompt,
        "parameters": {
            "max_new_tokens": 300,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get('generated_text', '')
                    # Убираем повтор промпта
                    if text.startswith(system_prompt):
                        text = text[len(system_prompt):]
                    if len(text.strip()) > 100:
                        print(f"✅ Пост готов ({len(text)} символов)")
                        return text.strip()
            elif response.status_code == 503:
                print(f"⏳ Модель загружается, ждём... (попытка {attempt+1})")
                time.sleep(5)
            else:
                print(f"⚠️ Ошибка HF: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: {e}")
            time.sleep(3)

    return None


def generate_image_for_post(topic, post_type):
    print("🎨 Flux генерирует картинку...")
    rand_seed = random.randint(1000, 99999)

    style_map = {
        "notes": "схема, интеллект-карта, учебные заметки",
        "lifehack": "лайфхак, инфографика, чек-лист",
        "tool": "интерфейс программы, приложение, ноутбук",
        "motivation": "мотивационная картинка, яркие цвета, вдохновение",
        "calm": "спокойствие, расслабление, мягкие тона",
        "general": "учеба, студенты, книги"
    }
    style = style_map.get(post_type, style_map["general"])

    prompt = f"{topic}, {style}, качественная иллюстрация, сочный цвет, современный дизайн, seed {rand_seed}"
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

    post = generate_post_huggingface(topic)
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
