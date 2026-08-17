import os
import json
import feedparser
import requests
import asyncio
import hashlib
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# بارگذاری متغیرهای محیطی
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# این توکن الان فقط برای اطمینان تعریف شده، اما برای ذخیره فایل استفاده نمیشه
GITHUB_TOKEN = os.getenv("GITTI_TOKEN") 

bot = Bot(token=BOT_TOKEN)

# لیست منابع RSS
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://venturebeat.com/ai/feed/",
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://deepmind.com/blog/rss.xml",
    "https://marktechpost.com/feed/",
]

SENT_FILE = "sent_news.json"
PAGES_DIR = "docs/pages/"

def load_sent_news():
    """بارگذاری لیست اخبار ارسال شده"""
    try:
        if not os.path.exists(SENT_FILE):
            return {}
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            # تبدیل لیست قدیمی به دیکشنری اگر نیاز بود
            if isinstance(data, list):
                return {item: datetime.now().isoformat() for item in data}
            return data
    except Exception as e:
        print(f"❌ خطا در بارگذاری حافظه: {e}")
        return {}

def save_sent_news(link):
    """ذخیره لینک خبر برای جلوگیری از تکرار"""
    try:
        data = load_sent_news()
        data[link] = datetime.now().isoformat()
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ خبر در حافظه ذخیره شد.")
    except Exception as e:
        print(f"❌ خطا در ذخیره‌سازی حافظه: {e}")

def get_news():
    """دریافت آخرین خبر از هر منبع"""
    all_news = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                entry = feed.entries[0]  # فقط جدیدترین خبر
                all_news.append({
                    "title": entry.title,
                    "summary": entry.get("summary", entry.get("description", "")),
                    "link": entry.link,
                    "published": entry.get("published", "")
                })
        except Exception as e:
            print(f"⚠️ خطا در دریافت از {url}: {e}")
    return all_news

def summarize(text):
    """خلاصه‌سازی هوشمند خبر"""
    prompt = f"""
    خبر زیر را به زبان فارسی خیلی روان، ساده و جذاب خلاصه کن.
    محدودیت: حداکثر ۳ جمله کوتاه.
    لحن: خبری و حرفه‌ای.
    اگر اسم شرکت یا محصول خاصی هست، آن را به انگلیسی بنویس.
    
    متن خبر:
    {text[:1500]}
    
    خلاصه فارسی:
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
            # تمیز کردن خروجی
            raw_summary = re.sub(r'^(خلاصه:|Summary:)', '', raw_summary).strip()
            return raw_summary if len(raw_summary) > 10 else "خلاصه‌ای برای این خبر موجود نیست."
        else:
            raise Exception("پاسخ نامعتبر از API")
    except Exception as e:
        print(f"⚠️ خطا در خلاصه‌سازی: {e}")
        return "خطا در دریافت خلاصه هوشمند."

def translate_full_text(text):
    """ترجمه کامل متن خبر"""
    if not text or len(text.strip()) < 50:
        return None
    
    prompt = f"""
    متن انگلیسی زیر را به فارسی سلیس، روان و حرفه‌ای ترجمه کن.
    پاراگراف‌بندی را حفظ کن.
    اسامی خاص (شرکت‌ها، محصولات، افراد) را به انگلیسی نگه دار.
    فقط متن ترجمه شده را برگردان.

    متن انگلیسی:
    {text[:3000]}
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
                "max_tokens": 1000
            },
            timeout=60
        )
        result = response.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return None
    except Exception as e:
        print(f"⚠️ خطا در ترجمه کامل: {e}")
        return None

def get_full_text_from_link(url):
    """استخراج متن اصلی از لینک خبر"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # استفاده از BeautifulSoup برای استخراج متن تمیز
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # حذف اسکریپت‌ها و استایل‌ها
            for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe']):
                tag.decompose()
            
            # تلاش برای پیدا کردن بدنه اصلی مقاله
            article = soup.find('article') or soup.find('main') or soup.find('div', class_='post-content') or soup.body
            
            if article:
                paragraphs = article.find_all('p')
                # ترکیب پاراگراف‌ها
                full_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
                
                if len(full_text) > 200:
                    return full_text
                else:
                    # اگر پاراگراف کافی نبود، کل متن تمیز شده
                    return article.get_text(separator="\n", strip=True)[:2000]
            else:
                return soup.get_text(separator="\n", strip=True)[:2000]
                
        except ImportError:
            print("⚠️ کتابخانه BeautifulSoup نصب نیست. متن خام استفاده می‌شود.")
            return response.text[:2000]
            
    except Exception as e:
        print(f"⚠️ خطا در دریافت متن کامل: {e}")
        return None

def create_html_page(translated_text, title, original_link, date_str):
    """ساخت صفحه HTML با طراحی زیبا"""
    
    # اگر ترجمه‌ای وجود نداشت، پیام پیش‌فرض
    if not translated_text:
        translated_text = "<p>متاسفانه متن کامل این خبر در دسترس نیست یا خطایی رخ داده است.</p>"
    else:
        # تبدیل newline های معمولی به تگ <br> یا <p> برای نمایش بهتر
        # اینجا فرض می‌کنیم translated_text پاراگراف‌بندی شده است
        paragraphs = translated_text.split('\n\n')
        content_html = "".join([f"<p>{p}</p>" for p in paragraphs if p.strip()])

    # استایل CSS مدرن و زیبا
    css_style = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700&display=swap');
        
        :root {
            --primary-color: #4f46e5;
            --secondary-color: #818cf8;
            --bg-color: #f3f4f6;
            --text-color: #1f2937;
            --card-bg: #ffffff;
        }

        body {
            font-family: 'Vazirmatn', Tahoma, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            direction: rtl;
            line-height: 1.8;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--card-bg);
            border-radius: 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 0;
            line-height: 1.4;
        }

        .meta-info {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 15px;
            font-size: 0.9rem;
            opacity: 0.9;
        }

        .content {
            padding: 30px;
            font-size: 1.1rem;
            text-align: justify;
        }

        .content p {
            margin-bottom: 1.5em;
        }

        .footer {
            background-color: #f9fafb;
            padding: 20px;
            text-align: center;
            border-top: 1px solid #e5e7eb;
            font-size: 0.9rem;
            color: #6b7280;
        }

        .btn-original {
            display: inline-block;
            background-color: var(--primary-color);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            margin-top: 10px;
            transition: background 0.3s;
        }

        .btn-original:hover {
            background-color: #4338ca;
        }

        @media (max-width: 600px) {
            body { padding: 10px; }
            .header { padding: 20px; }
            .header h1 { font-size: 1.2rem; }
            .content { padding: 20px; font-size: 1rem; }
        }
    </style>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {css_style}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="meta-info">
                <span>📅 {date_str}</span>
                <span>🤖 ربات خبررسان AI</span>
            </div>
        </div>
        <div class="content">
            {content_html}
        </div>
        <div class="footer">
            <p>برای مطالعه خبر اصلی به زبان انگلیسی:</p>
            <a href="{original_link}" target="_blank" class="btn-original">مشاهده منبع اصلی 🔗</a>
            <p style="margin-top: 15px; font-size: 0.8em;">تولید شده توسط هوش مصنوعی</p>
        </div>
    </div>
</body>
</html>"""
    
    return html_content

def save_html_page(html_content, news_id):
    """ذخیره فایل HTML در پوشه محلی برای Commit شدن توسط GitHub Actions"""
    try:
        # ایجاد پوشه اگر وجود ندارد
        os.makedirs(PAGES_DIR, exist_ok=True)
        
        # نام فایل امن
        safe_id = re.sub(r'[^\w\-]', '_', str(news_id))
        file_name = f"news_{safe_id}.html"
        file_path = os.path.join(PAGES_DIR, file_name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # ساخت لینک نهایی بر اساس ساختار GitHub Pages
        # فرض بر این است که ریپازیتوری ai_news_bot است و روی شاخه main و پوشه docs تنظیم شده
        base_url = "https://UniverseCreative.github.io/ai_news_bot"
        final_url = f"{base_url}/pages/{file_name}"
        
        print(f"✅ فایل HTML ذخیره شد: {file_path}")
        return final_url
        
    except Exception as e:
        print(f"❌ خطا در ذخیره فایل HTML: {e}")
        return None

def generate_news_id(link):
    """تولید شناسه یکتا برای هر خبر"""
    return hashlib.md5(link.encode('utf-8')).hexdigest()[:8]

async def send_to_telegram(title, summary, link, html_url=None):
    """ارسال پیام به کانال تلگرام"""
    
    # فرمت‌بندی پیام
    message = f"""
🚀 *خبر جدید هوش مصنوعی*

📰 *{title}*

🧠 *خلاصه:*
{summary}

🔗 [لینک منبع اصلی]({link})

#AI #News #Tech
"""
    
    # ساخت دکمه شیشه‌ای
    reply_markup = None
    if html_url:
        keyboard = [
            [InlineKeyboardButton("📖 متن کامل خبر به فارسی", url=html_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            disable_web_page_preview=True  # برای نمایش بهتر دکمه‌ها
        )
        print("✅ پیام با موفقیت ارسال شد.")
    except Exception as e:
        print(f"❌ خطا در ارسال تلگرام: {e}")

async def process_news_item(item, sent_news):
    """پردازش تک‌تک اخبار"""
    link = item["link"]
    
    # بررسی تکراری بودن
    if link in sent_news:
        print(f"⏭ خبر تکراری رد شد.")
        return False
    
    print(f"🔄 شروع پردازش: {item['title'][:40]}...")
    
    try:
        # 1. خلاصه‌سازی
        summary = summarize(item["summary"])
        
        # 2. دریافت و ترجمه متن کامل
        full_text_en = get_full_text_from_link(link)
        translated_text = None
        if full_text_en:
            translated_text = translate_full_text(full_text_en)
        
        # 3. ساخت HTML
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = create_html_page(translated_text, item['title'], link, now_str)
        
        # 4. ذخیره HTML
        news_id = generate_news_id(link)
        html_url = save_html_page(html_content, news_id)
        
        # 5. ارسال به تلگرام
        await send_to_telegram(item['title'], summary, link, html_url)
        
        # 6. ذخیره در حافظه
        save_sent_news(link)
        
        return True
        
    except Exception as e:
        print(f"❌ خطا در پردازش خبر: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🤖 ربات خبررسان هوش مصنوعی شروع به کار کرد...")
    
    # دریافت اخبار
    news_items = get_news()
    print(f"📊 تعداد {len(news_items)} خبر جدید یافت شد.")
    
    # بارگذاری حافظه
    sent_news = load_sent_news()
    
    # پردازش اخبار
    success_count = 0
    for item in news_items:
        if await process_news_item(item, sent_news):
            success_count += 1
            # کمی تاخیر برای رعایت نرخ درخواست API
            await asyncio.sleep(2)
            
    print(f"🏁 پایان کار. {success_count} خبر با موفقیت پردازش شد.")

if __name__ == "__main__":
    asyncio.run(main())