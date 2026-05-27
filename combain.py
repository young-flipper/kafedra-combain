#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import sqlite3
import requests
import urllib3
import subprocess
from datetime import datetime
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== НАСТРОЙКИ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
MAX_TOPICS_IN_MEMORY = 100

# GigaChat авторизация
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY", "")
# =================================

print("📚 НЕЙРОСЕТЕВОЙ КОМБАЙН — КАФЕДРА ВЫЖИВАНИЯ")
print("🤖 GigaChat (текст) + Kandinsky (картинки)\n")


class MemoryDB:
    def __init__(self, db_path="memory.db"):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('CREATE TABLE IF NOT EXISTS used_topics (id INTEGER PRIMARY KEY, topic TEXT, used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
            conn.commit()
            conn.close()

    def is_used(self, topic):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT 1 FROM used_topics WHERE topic = ?", (topic,))
            result = c.fetchone() is not None
            conn.close()
            return result

    def add(self, topic):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT INTO used_topics (topic) VALUES (?)", (topic,))
            conn.commit()
            conn.close()

    def get_stats(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM used_topics")
            count = c.fetchone()[0]
            conn.close()
            return count


def get_topics():
    default = [
        "Витаминка мотивации: Запускаем неделю!",
        "Конспект-карточка: Теория множеств за 3 минуты",
        "Инструмент в деле: Умные шаблоны для конспектов в Notion",
        "Лайфхак сессии: Метод Фейнмана",
        "Вопрос-ответ: Какой предмет самый сложный?",
        "Без паники: Как написать введение к курсовой за 30 минут",
        "Инструмент в деле: Учим слова с Anki без мучений",
        "5 приёмов тайм-менеджмента для сессии"
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

    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("📤 Отправка обновлений в репозиторий...")
        try:
            subprocess.run(["git", "config", "user.name", "github-actions"], capture_output=True, check=False)
            subprocess.run(["git", "config", "user.email", "github-actions@github.com"], capture_output=True, check=False)
            subprocess.run(["git", "add", "topics.json"], capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "Обновление тем после публикации", "--allow-empty"], capture_output=True, check=False)
            subprocess.run(["git", "push"], capture_output=True, check=False)
            print("✅ Изменения отправлены")
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")


def get_next_topic():
    topics = get_topics()
    if not topics:
        return None
    topic = topics.pop(0)
    save_topics(topics)
    return topic


def generate_post_gigachat(topic):
    print("🤖 GigaChat генерирует текст...")

    if not GIGACHAT_AUTH_KEY:
        print("❌ GIGACHAT_AUTH_KEY не задан")
        return None

    try:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole

        giga = GigaChat(
            credentials=GIGACHAT_AUTH_KEY,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False
        )

        clean_topic = topic.split(":")[-1].strip()

        # Определяем тип поста для хэштегов
        topic_lower = topic.lower()
        if "мотивация" in topic_lower or "витаминка" in topic_lower:
            hashtags = "#мотивация #студенты #учеба"
        elif "конспект" in topic_lower:
            hashtags = "#конспект #учеба #студентам"
        elif "лайфхак" in topic_lower:
            hashtags = "#лайфхак #сессия #студенты"
        elif "инструмент" in topic_lower:
            hashtags = "#инструмент #лайфхак #учеба"
        elif "без паники" in topic_lower:
            hashtags = "#безпаники #курсовая #студенты"
        else:
            hashtags = "#студентам #учеба #шпаргалка"

        payload = Chat(
            messages=[
                Messages(
                    role=MessagesRole.SYSTEM,
                    content="Ты автор учебного Telegram-канала. Пиши коротко, с эмодзи, дружелюбно. НЕ используй **. НЕ добавляй хэштеги."
                ),
                Messages(
                    role=MessagesRole.USER,
                    content=f"Напиши пост для студентов на тему: {clean_topic}"
                )
            ],
            temperature=0.7,
            max_tokens=300
        )

        response = giga.chat(payload)
        text = response.choices[0].message.content.strip()

        # Убираем маркеры жирного шрифта
        text = text.replace("**", "")

        # Добавляем хэштеги
        text = text.strip() + f"\n\n{hashtags}"

        if len(text) > 50:
            print(f"✅ Пост готов ({len(text)} символов)")
            return text

    except ImportError:
        print("❌ Установите gigachat: pip install gigachat")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")

    return None


def generate_image_kandinsky(topic):
    print("🎨 Kandinsky генерирует картинку...")

    if not GIGACHAT_AUTH_KEY:
        print("❌ GIGACHAT_AUTH_KEY не задан")
        return None

    try:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole
        import json as json_lib

        giga = GigaChat(
            credentials=GIGACHAT_AUTH_KEY,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False
        )

        clean_topic = topic.split(":")[-1].strip()
        prompt = f"Нарисуй иллюстрацию для учебного поста. Тема: {clean_topic}. Стиль: современный, яркий, позитивный. Студенты, книги, знания."

        payload = Chat(
            messages=[
                Messages(
                    role=MessagesRole.USER,
                    content=prompt
                )
            ],
            functions=[{"name": "text2image"}],
            function_call="auto"
        )

        response = giga.chat(payload)

        if response.choices and response.choices[0].message.function_call:
            function_call = response.choices[0].message.function_call
            if function_call.name == "text2image":
                args = json_lib.loads(function_call.arguments)
                file_id = args.get("file_id")

                if file_id:
                    access_token = giga._access_token
                    image_url = f"https://gigachat.devices.sberbank.ru/api/v1/files/{file_id}/content"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/octet-stream"
                    }
                    image_response = requests.get(image_url, headers=headers, verify=False)

                    if image_response.status_code == 200:
                        with open("post_image.jpg", "wb") as f:
                            f.write(image_response.content)
                        print("✅ Картинка готова (Kandinsky)")
                        return "post_image.jpg"
                    else:
                        print(f"⚠️ Ошибка скачивания: {image_response.status_code}")

    except Exception as e:
        print(f"⚠️ Ошибка Kandinsky: {e}")

    return None


def send_to_telegram(text, image_path=None):
    print("📤 Отправка в Telegram...")
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                r = requests.post(url, files={"photo": photo}, data={
                    "chat_id": TELEGRAM_CHANNEL_ID, "caption": text[:1024]
                }, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            r = requests.post(url, json={
                "chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4096]
            }, timeout=30)
        if r.status_code == 200:
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

    post = generate_post_gigachat(topic)
    if not post:
        print("❌ Не удалось сгенерировать пост")
        return

    print(f"\n📝 Пост:\n{post}\n")

    image = generate_image_kandinsky(topic)

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
