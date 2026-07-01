import os
import json
import feedparser
import requests
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot

# خواندن env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# اتصال تلگرام
bot = Bot(token=BOT_TOKEN)

# RSS خبرها
RSS_FEEDS = [
    # منابع قبلی
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/ai/feed/",
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://deepmind.com/blog/rss.xml",
    "https://marktechpost.com/feed/",
]

# فایل خبرهای ارسال شده (JSON)
SENT_FILE = "sent_news.json"

def load_sent_news():
    """بارگذاری دیکشنری خبرهای ارسال‌شده از فایل JSON"""
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # پشتیبانی از فرمت قدیمی (set) برای یک بار انتقال
            if isinstance(data, list):
                return {item: datetime.now().isoformat() for item in data}
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_sent_news(link):
    """ذخیره خبر جدید با زمان ارسال"""
    data = load_sent_news()
    data[link] = datetime.now().isoformat()
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_news():
    """گرفتن اخبار از RSS"""
    all_news = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:1]:  # هر سایت فقط ۱ خبر
                all_news.append({
                    "title": entry.title,
                    "summary": entry.get("summary", entry.get("title", "")),
                    "link": entry.link
                })
        except Exception as e:
            print(f"خطا در دریافت {url}: {e}")
    return all_news

def summarize(text):
    """خلاصه‌سازی حرفه‌ای خبر با ساختار اجباری"""
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {
                    "role": "user",
                    "content": f"""
خبر زیر را دقیقاً در سه بخش زیر خلاصه کن. از به هم ریختن این ساختار جدا خودداری کن:

**بخش ۱ - عنوان خبر (حداکثر ۸ کلمه):**
فقط عنوان اصلی خبر را به فارسی روان بنویس. اگر نام شرکت یا محصول مهم است، به انگلیسی حفظ کن.

**بخش ۲ - خلاصه خبر (حداکثر ۳ خط):**
مهم‌ترین اتفاق خبر را به فارسی کاملاً روان و ساده بنویس. مثل این است که برای یک دوست غیرمتخصص توضیح می‌دهی. از ترجمه تحت‌اللفظی اکیداً پرهیز کن.

**بخش ۳ - نکته فنی (اختیاری، حداکثر ۱ خط):**
اگر خبر شامل یک جزئیات فنی مهم است، آن را خیلی مختصر بنویس، در غیر این صورت این بخش را خالی بگذار.

**قوانین طلایی:**
- تمام اسامی خاص (افراد، شرکت‌ها، محصولات) را **دقیقاً به انگلیسی** بنویس.
- جملات باید کوتاه، ساده و مفهومی باشند.
- هیچ‌گاه از کلمات پیچیده یا ترجمه‌های تحت‌اللفظی استفاده نکن.

متن خبر:
{text}
"""
                }
            ]
        }
    )
    
    result = response.json()
    if "choices" not in result:
        print("خطا در OpenRouter:", result)
        return "خطا در خلاصه‌سازی خبر"

    raw_summary = result["choices"][0]["message"]["content"].strip()

    # پردازش خروجی برای استخراج بخش‌ها
    parts = raw_summary.split("**بخش")
    title = ""
    summary = ""
    tech_note = ""

    for part in parts:
        if "عنوان خبر" in part:
            title = part.split(":")[-1].strip().split("\n")[0].strip()
        elif "خلاصه خبر" in part:
            summary_lines = part.split(":")[-1].strip().split("\n")
            summary = " ".join([line.strip() for line in summary_lines if line.strip() and not line.startswith("**")])
        elif "نکته فنی" in part:
            tech_note = part.split(":")[-1].strip().split("\n")[0].strip()

    # اگر ساختار به هم خورد، از کل متن به عنوان خلاصه استفاده کن
    if not summary and not title:
        return raw_summary

    final_summary = f"{title}\n\n{summary}"
    if tech_note and tech_note not in ["خالی", "-", "ندارد"]:
        final_summary += f"\n\n💡 {tech_note}"

    return final_summary

async def send_to_telegram(title, summary, link):
    """ارسال خبر به تلگرام"""
    # استخراج عنوان از خلاصه (اگر خلاصه ساختاریافته باشد)
    lines = summary.split("\n\n")
    if lines and len(lines) >= 2:
        news_title = lines[0]
        news_summary = "\n\n".join(lines[1:])
    else:
        news_title = title
        news_summary = summary

    message = f"""
🚀 خبر جدید دنیای AI

📰 {news_title}

🧠 خلاصه:
{news_summary}

🔗 لینک خبر:
{link}

#AI #Tech
"""
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=message
    )

async def main():
    """اجرای اصلی ربات"""
    news = get_news()
    sent_news = load_sent_news()

    for item in news:
        if item["link"] in sent_news:
            print("خبر تکراری رد شد ⏭")
            continue

        print("در حال پردازش خبر...")
        try:
            summary = summarize(item["summary"])
            await send_to_telegram(item["title"], summary, item["link"])
            print("ارسال شد ✅")
            save_sent_news(item["link"])
        except Exception as e:
            print(f"خطا در پردازش خبر: {e}")

if __name__ == "__main__":
    asyncio.run(main())