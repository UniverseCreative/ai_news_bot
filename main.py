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

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITTI_TOKEN")

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

SENT_FILE = "sent_news.json"
PAGES_DIR = "docs/pages/"

def load_sent_news():
    try:
        if not os.path.exists(SENT_FILE):
            return {}
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            if isinstance(data, list):
                return {item: datetime.now().isoformat() for item in data}
            return data
    except Exception as e:
        print(f"❌ خطا در بارگذاری حافظه: {e}")
        return {}

def save_sent_news(link):
    try:
        data = load_sent_news()
        # اطمینان از اینکه data یک دیکشنری است
        if not isinstance(data, dict):
            data = {}
        data[link] = datetime.now().isoformat()
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ خبر در حافظه ذخیره شد.")
    except Exception as e:
        print(f"❌ خطا در ذخیره‌سازی حافظه: {e}")

def get_news():
    all_news = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                entry = feed.entries[0]
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
    prompt = f"""
    خبر زیر را به زبان فارسی رسمی، روان و خبری خلاصه کن.
    محدودیت: حداکثر ۳ جمله.
    لحن: کاملاً حرفه‌ای و بی‌طرفانه.
    اسامی شرکت‌ها یا محصولات را به انگلیسی بنویس.
    
    متن خبر:
    {text[:1500]}
    
    خلاصه:
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/UniverseCreative/ai_news_bot",
                "X-Title": "Kafa Tech News Bot"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
            },
            timeout=30
        )
        if response.status_code != 200:
            print(f"❌ خطای API: {response.status_code} - {response.text}")
            return "خطا در دریافت خلاصه."

        result = response.json()
        if "choices" in result and result["choices"]:
            raw_summary = result["choices"][0]["message"]["content"].strip()
            return raw_summary if len(raw_summary) > 10 else "خلاصه‌ای در دسترس نیست."
        return "خطا در دریافت خلاصه."
    except Exception as e:
        print(f"⚠️ خطا در خلاصه‌سازی: {e}")
        return "خطا در دریافت خلاصه."

def get_full_text_from_link(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe', 'noscript', 'form']):
                tag.decompose()
            
            article = soup.find('article') or soup.find('main') or soup.find('div', class_='post-content') or soup.body
            
            if article:
                paragraphs = article.find_all('p')
                full_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30])
                return full_text if len(full_text) > 200 else article.get_text(separator="\n", strip=True)[:2500]
            return soup.get_text(separator="\n", strip=True)[:2500]
        except ImportError:
            return None
    except Exception as e:
        print(f"⚠️ خطا در دریافت متن کامل: {e}")
        return None

def translate_full_text(text):
    if not text or len(text.strip()) < 100:
        return None
    
    prompt = f"""
    متن انگلیسی زیر را به فارسی رسمی، سلیس و با لحن خبری ترجمه کن.
    پاراگراف‌بندی متن اصلی را دقیقاً حفظ کن.
    اسامی خاص (شرکت‌ها، محصولات، افراد) را به انگلیسی نگه دار.
    فقط متن ترجمه شده را برگردان.

    متن:
    {text[:3500]}
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
                "max_tokens": 1200
            },
            timeout=60
        )
        if response.status_code != 200:
            return None
        result = response.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"].strip()
        return None
    except Exception as e:
        print(f"⚠️ خطا در ترجمه: {e}")
        return None

def create_html_page(translated_text, title, original_link, date_str):
    """ساخت صفحه HTML با طراحی رسمی، خبری و استاندارد"""
    
    if not translated_text or len(str(translated_text).strip()) < 50:
        content_html = "<p style='text-align: center; color: #6b7280; padding: 40px;'>متاسفانه متن کامل این خبر در دسترس نیست یا سایت منبع اجازه استخراج متن را نمی‌دهد.</p>"
    else:
        paragraphs = str(translated_text).split('\n\n')
        content_html = "".join([f"<p>{p}</p>" for p in paragraphs if p.strip()])

    css_style = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;800&display=swap');
        
        :root {
            --primary-color: #1e40af; /* آبی تیره رسمی */
            --bg-color: #f3f4f6;      /* خاکستری بسیار روشن */
            --surface-color: #ffffff;
            --text-main: #111827;     /* تقریباً مشکی */
            --text-muted: #6b7280;    /* خاکستری متن */
            --border-color: #e5e7eb;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Vazirmatn', Tahoma, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            line-height: 1.8;
            direction: rtl;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--surface-color);
            border-radius: 8px; /* گوشه‌های کمی گرد برای جدیت بیشتر */
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            overflow: hidden;
            border: 1px solid var(--border-color);
        }

        .header {
            padding: 32px 40px;
            border-bottom: 1px solid var(--border-color);
        }

        .category-badge {
            display: inline-block;
            background-color: #eff6ff;
            color: var(--primary-color);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 700;
            margin-bottom: 16px;
        }

        .header h1 {
            font-size: 1.6rem;
            font-weight: 800;
            line-height: 1.5;
            color: var(--primary-color); /* رنگ مناسب برای عنوان */
            margin-bottom: 16px;
        }

        .meta-info {
            display: flex;
            gap: 20px;
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .content {
            padding: 40px;
        }

        .content p {
            font-size: 1.1rem;
            line-height: 2.2; /* فاصله خطوط عالی برای خوانایی */
            margin-bottom: 24px;
            text-align: justify; /* تراز کردن متن از دو طرف */
            text-justify: inter-word;
            color: var(--text-main);
        }

        .content p:last-child {
            margin-bottom: 0;
        }

        .footer {
            background-color: #f9fafb;
            padding: 24px 40px;
            border-top: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 12px 28px;
            border-radius: 6px;
            font-size: 0.95rem;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            width: 100%;
            max-width: 320px;
        }

        .btn-primary {
            background-color: var(--primary-color);
            color: white;
        }

        .btn-primary:hover {
            background-color: #1e3a8a;
        }

        .btn-secondary {
            background-color: transparent;
            color: var(--text-muted);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            border-color: var(--primary-color);
            color: var(--primary-color);
            background-color: #eff6ff;
        }

        .footer-text {
            margin-top: 8px;
            font-size: 0.8rem;
            color: var(--text-muted);
            text-align: center;
        }

        @media (max-width: 768px) {
            body { padding: 0; background-color: var(--surface-color); }
            .container { border-radius: 0; border: none; box-shadow: none; }
            .header, .content, .footer { padding: 24px; }
            .header h1 { font-size: 1.3rem; }
            .content p { font-size: 1rem; line-height: 2; }
            .meta-info { flex-direction: column; gap: 8px; }
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
            <span class="category-badge">هوش مصنوعی و فناوری</span>
            <h1>{title}</h1>
            <div class="meta-info">
                <span>📅 {date_str}</span>
                <span>⏱️ زمان مطالعه: حدود ۲ دقیقه</span>
            </div>
        </div>
        
        <div class="content">
            {content_html}
        </div>
        
        <div class="footer">
            <a href="{original_link}" target="_blank" class="btn btn-primary">🔗 مشاهده منبع اصلی خبر</a>
            <a href="https://t.me/KafaTechNews" class="btn btn-secondary">📱 بازگشت به کانال تلگرام</a>
            <div class="footer-text">
                تهیه و تنظیم توسط ربات خبررسان هوش مصنوعی
            </div>
        </div>
    </div>
</body>
</html>"""
    
    return html_content

def save_html_page(html_content, news_id):
    try:
        os.makedirs(PAGES_DIR, exist_ok=True)
        safe_id = re.sub(r'[^\w\-]', '_', str(news_id))
        file_name = f"news_{safe_id}.html"
        file_path = os.path.join(PAGES_DIR, file_name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        base_url = "https://UniverseCreative.github.io/ai_news_bot"
        final_url = f"{base_url}/pages/{file_name}"
        print(f"✅ فایل HTML ذخیره شد: {final_url}")
        return final_url
    except Exception as e:
        print(f"❌ خطا در ذخیره فایل HTML: {e}")
        return None

def generate_news_id(link):
    return hashlib.md5(link.encode('utf-8')).hexdigest()[:8]

async def send_to_telegram(title, summary, link, html_url=None):
    message = f"""
📰 *خبر جدید هوش مصنوعی*

*{title}*

📝 *خلاصه:*
{summary}

🔗 [لینک منبع اصلی]({link})

#AI #News #Tech
"""
    reply_markup = None
    if html_url:
        keyboard = [[InlineKeyboardButton("📖 متن کامل خبر به فارسی", url=html_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        print("✅ پیام با موفقیت ارسال شد.")
    except Exception as e:
        print(f"❌ خطا در ارسال تلگرام: {e}")

async def process_news_item(item, sent_news):
    link = item["link"]
    if link in sent_news:
        print(f"⏭ خبر تکراری رد شد.")
        return False
    
    print(f"🔄 شروع پردازش: {item['title'][:40]}...")
    
    try:
        summary = summarize(item["summary"])
        
        full_text_en = get_full_text_from_link(link)
        translated_text = None
        if full_text_en:
            translated_text = translate_full_text(full_text_en)
        
        if not translated_text:
            print("⚠️ متن کامل دریافت/ترجمه نشد، از خلاصه RSS استفاده می‌شود.")
            translated_text = summary + "\n\n(توجه: سایت منبع اجازه استخراج متن کامل را نداد.)"
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = create_html_page(translated_text, item['title'], link, now_str)
        
        news_id = generate_news_id(link)
        html_url = save_html_page(html_content, news_id)
        
        await send_to_telegram(item['title'], summary, link, html_url)
        save_sent_news(link)
        
        return True
        
    except Exception as e:
        print(f"❌ خطا در پردازش خبر: {e}")
        return False

async def main():
    print("🤖 ربات خبررسان هوش مصنوعی شروع به کار کرد...")
    news_items = get_news()
    print(f"📊 تعداد {len(news_items)} خبر جدید یافت شد.")
    
    sent_news = load_sent_news()
    success_count = 0
    
    for item in news_items:
        if await process_news_item(item, sent_news):
            success_count += 1
            await asyncio.sleep(2)
            
    print(f"🏁 پایان کار. {success_count} خبر با موفقیت پردازش شد.")

if __name__ == "__main__":
    asyncio.run(main())