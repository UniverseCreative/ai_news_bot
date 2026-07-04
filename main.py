import os
import json
import feedparser
import requests
import asyncio
import base64
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

bot = Bot(token=BOT_TOKEN)

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/ai/feed/",
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://deepmind.com/blog/rss.xml",
    "https://marktechpost.com/feed/",
]

REPO_OWNER = "UniverseCreative"
REPO_NAME = "ai_news_bot"
FILE_PATH = "sent_news.json"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"

def load_sent_news():
    """بارگذاری فایل JSON از مخزن با GitHub API"""
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        response = requests.get(API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            content = data.get("content", "")
            if not content:
                print("⚠️ فایل حافظه خالی است")
                return {}
            
            try:
                decoded = base64.b64decode(content).decode('utf-8')
                if not decoded.strip():
                    print("⚠️ محتوای فایل خالی است")
                    return {}
                
                loaded_data = json.loads(decoded)
                if isinstance(loaded_data, list):
                    return {item: datetime.now().isoformat() for item in loaded_data}
                return loaded_data
            except json.JSONDecodeError:
                print("⚠️ محتوای فایل معتبر نیست، بازنشانی به حافظه خالی")
                return {}
        else:
            print(f"⚠️ فایل حافظه پیدا نشد (کد {response.status_code})، شروع با حافظه خالی")
            return {}
            
    except Exception as e:
        print(f"❌ خطا در بارگذاری حافظه: {e}")
        return {}

def save_sent_news(link):
    """ذخیره خبر جدید در مخزن با GitHub API"""
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        
        get_response = requests.get(API_URL, headers=headers)
        data = {}
        sha = None
        
        if get_response.status_code == 200:
            try:
                file_data = get_response.json()
                sha = file_data.get("sha")
                content = file_data.get("content", "")
                if content:
                    decoded = base64.b64decode(content).decode('utf-8')
                    if decoded.strip():
                        data = json.loads(decoded)
            except (json.JSONDecodeError, base64.binascii.Error):
                print("⚠️ فایل موجود معتبر نیست، بازنشانی...")
                data = {}
        
        data[link] = datetime.now().isoformat()
        
        new_content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
        
        payload = {
            "message": f"اضافه کردن خبر {link[:30]}...",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha
        
        put_response = requests.put(API_URL, headers=headers, json=payload)
        
        if put_response.status_code in [200, 201]:
            print(f"✅ حافظه به‌روزرسانی شد (تعداد اخبار: {len(data)})")
        else:
            print(f"❌ خطا در ذخیره‌سازی: {put_response.status_code}")
            
    except Exception as e:
        print(f"❌ خطا در ذخیره‌سازی حافظه: {e}")

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
    print(f"تعداد اخبار موجود در حافظه: {len(sent_news)}")

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