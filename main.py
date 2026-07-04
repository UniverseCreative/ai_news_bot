import os
import json
import feedparser
import requests
import asyncio
import subprocess
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot

# خواندن env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # این مهم است

# اتصال تلگرام
bot = Bot(token=BOT_TOKEN)

# RSS خبرها
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/ai/feed/",
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://deepmind.com/blog/rss.xml",
    "https://marktechpost.com/feed/",
]

REPO_URL = f"https://x-access-token:{GITHUB_TOKEN}@github.com/UniverseCreative/ai_news_bot.git"
BRANCH = "memory"
SENT_FILE = "sent_news.json"

def load_sent_news():
    """بارگذاری دیکشنری خبرهای ارسال‌شده از شاخه‌ی memory"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # کلون کردن فقط شاخه‌ی memory
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, tmpdir],
                check=True, capture_output=True, text=True
            )
            file_path = os.path.join(tmpdir, SENT_FILE)
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {item: datetime.now().isoformat() for item in data}
                    return data
            return {}
    except Exception as e:
        print(f"خطا در بارگذاری حافظه: {e}")
        return {}

def save_sent_news(link):
    """ذخیره خبر جدید در شاخه‌ی memory"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # کلون کردن شاخه‌ی memory
            subprocess.run(
                ["git", "clone", "--branch", BRANCH, REPO_URL, tmpdir],
                check=True, capture_output=True, text=True
            )
            file_path = os.path.join(tmpdir, SENT_FILE)
            
            # بارگذاری داده‌های موجود
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}
            
            # اضافه کردن خبر جدید
            data[link] = datetime.now().isoformat()
            
            # ذخیره در فایل
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # تنظیمات git و commit و push
            subprocess.run(["git", "config", "user.email", "bot@example.com"], cwd=tmpdir, check=True)
            subprocess.run(["git", "config", "user.name", "AI News Bot"], cwd=tmpdir, check=True)
            subprocess.run(["git", "add", SENT_FILE], cwd=tmpdir, check=True)
            subprocess.run(["git", "commit", "-m", f"اضافه کردن خبر {link[:50]}..."], cwd=tmpdir, check=True)
            subprocess.run(["git", "push", "origin", BRANCH], cwd=tmpdir, check=True)
    except Exception as e:
        print(f"خطا در ذخیره‌سازی حافظه: {e}")

def get_news():
    all_news = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:1]:
                all_news.append({
                    "title": entry.title,
                    "summary": entry.get("summary", entry.get("title", "")),
                    "link": entry.link
                })
        except Exception as e:
            print(f"خطا در دریافت {url}: {e}")
    return all_news

def summarize(text):
    """خلاصه‌سازی حرفه‌ای خبر با تضمین خروجی غیرخالی"""
    prompt = f"""
    خبر زیر را به زبان فارسی خیلی روان و ساده، در دو یا سه جمله خلاصه کن.
    فقط متن خلاصه را بنویس، بدون هیچ برچسب یا عنوان اضافی.
    اگر اسم شرکت یا محصول خاصی هست، آن را به انگلیسی حفظ کن.
    جملات باید کوتاه و مفهومی باشند.

    خبر:
    {text[:1500]}

    خلاصه (فقط دو خط):
    """

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
            },
            timeout=30
        )
        
        result = response.json()
        if "choices" in result and result["choices"]:
            raw_summary = result["choices"][0]["message"]["content"].strip()
        else:
            raise Exception("پاسخ نامعتبر از API")
            
    except Exception as e:
        print(f"خطا در تماس با OpenRouter: {e}")
        raw_summary = ""

    raw_summary = raw_summary.replace("خلاصه:", "").replace("**", "").strip()
    
    if len(raw_summary) < 20:
        sentences = text.split(".")
        for sent in sentences[:3]:
            clean_sent = sent.strip()
            if len(clean_sent) > 30:
                raw_summary = clean_sent[:200] + "..."
                break
        else:
            raw_summary = "خلاصه‌ای برای این خبر در دسترس نیست."

    if len(raw_summary) > 350:
        raw_summary = raw_summary[:350].rsplit(" ", 1)[0] + "..."

    return raw_summary

async def send_to_telegram(title, summary, link):
    if len(summary) < 20:
        summary = f"خلاصه‌ای برای این خبر موجود نیست. عنوان: {title}"
    
    message = f"""
🚀 خبر جدید دنیای AI

📰 {title}

🧠 خلاصه:
{summary}

🔗 لینک خبر:
{link}

#AI #Tech
"""
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=message
    )

async def main():
    news = get_news()
    sent_news = load_sent_news()

    for item in news:
        if item["link"] in sent_news:
            print(f"خبر تکراری رد شد ⏭: {item['link']}")
            continue

        print(f"در حال پردازش خبر: {item['title'][:30]}...")
        try:
            summary = summarize(item["summary"])
            await send_to_telegram(item["title"], summary, item["link"])
            print("ارسال شد ✅")
            save_sent_news(item["link"])
        except Exception as e:
            print(f"خطا در پردازش خبر: {e}")

if __name__ == "__main__":
    asyncio.run(main())