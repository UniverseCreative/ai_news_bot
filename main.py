
import os
import feedparser
import requests
import asyncio


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

# فعلا 5 منبع خبری

    # AI & Tech
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/ai/feed/",

    # AI Labs
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",

]





# فایل خبرهای ارسال شده
SENT_FILE = "sent_news.txt"


# خواندن خبرهای قبلی
def load_sent_news():

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as file:
            return set(file.read().splitlines())

    except FileNotFoundError:
        return set()


# ذخیره خبر جدید
def save_sent_news(link):

    with open(SENT_FILE, "a", encoding="utf-8") as file:
        file.write(link + "\n")






# گرفتن خبرها
def get_news():

    all_news = []

    for url in RSS_FEEDS:

        feed = feedparser.parse(url)

        for entry in feed.entries[:1]:

            all_news.append({
                "title": entry.title,
                "summary": entry.get("summary", entry.get("title", "")),
                "link": entry.link
            })

    return all_news



# خلاصه سازی




def summarize(text):

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

تو یک خبرنگار حرفه‌ای حوزه تکنولوژی و هوش مصنوعی هستی.

این خبر را:

- روان
- طبیعی
- حرفه‌ای
- کوتاه
- قابل فهم برای فارسی‌زبان‌ها

به فارسی بازنویسی و خلاصه کن.

قوانین:
- ترجمه تحت‌اللفظی نکن
- ترجمه رایج و به روز کلمات رو استفاده کن
- متن شبیه خبر رسانه‌ای فارسی باشد
- حداکثر 5 خط
- لحن مدرن و حرفه‌ای
- اگر اسم شرکت یا محصول مهم است حفظ کن

متن خبر:

{text}
"""

                }
            ]
        }
    )

    result = response.json()

    print(result)

    # اگر خطا داشت
    if "choices" not in result:
        return "خطا در خلاصه‌سازی خبر"

    return result["choices"][0]["message"]["content"]




# ارسال تلگرام

async def send_to_telegram(title, summary, link):

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



# اجرای اصلی

async def main():

    news = get_news()

    sent_news = load_sent_news()

    for item in news:

        if item["link"] in sent_news:

            print("خبر تکراری رد شد ⏭")

            continue

        print("در حال پردازش خبر...")

        summary = summarize(item["summary"])

        await send_to_telegram(
            item["title"],
            summary,
            item["link"]
        )

        print("ارسال شد ✅")

        save_sent_news(item["link"])






# شروع برنامه 

asyncio.run(main())