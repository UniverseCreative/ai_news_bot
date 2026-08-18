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
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/UniverseCreative/ai_news_bot",
                "X-Title": "AI News Bot"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ خطای API OpenRouter: {response.status_code} - {response.text}")
            return "خطا در دریافت خلاصه هوشمند."

        result = response.json()
        if "choices" in result and result["choices"]:
            raw_summary = result["choices"][0]["message"]["content"].strip()
            raw_summary = re.sub(r'^(خلاصه:|Summary:)', '', raw_summary).strip()
            return raw_summary if len(raw_summary) > 10 else "خلاصه‌ای برای این خبر موجود نیست."
        else:
            print(f"❌ پاسخ نامعتبر از API: {result}")
            return "خطا در دریافت خلاصه هوشمند."
            
    except Exception as e:
        print(f"⚠️ خطا در خلاصه‌سازی: {e}")
        return "خطا در دریافت خلاصه هوشمند."

def get_full_text_from_link(url):
    try:
        # هدرهای قوی‌تر برای دور زدن مسدودسازی 403
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe', 'noscript']):
                tag.decompose()
            
            article = soup.find('article') or soup.find('main') or soup.find('div', class_='post-content') or soup.body
            
            if article:
                paragraphs = article.find_all('p')
                full_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
                
                if len(full_text) > 200:
                    return full_text
                else:
                    return article.get_text(separator="\n", strip=True)[:2000]
            else:
                return soup.get_text(separator="\n", strip=True)[:2000]
                
        except ImportError:
            print("⚠️ کتابخانه BeautifulSoup نصب نیست.")
            return None
            
    except requests.exceptions.HTTPError as e:
        print(f"⚠️ دسترسی به سایت مسدود شد (403/404): {url[:50]}...")
        return None
    except Exception as e:
        print(f"⚠️ خطا در دریافت متن کامل: {e}")
        return None

def translate_full_text(text):
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
        
        if response.status_code != 200:
            print(f"❌ خطای ترجمه API: {response.status_code}")
            return None

        result = response.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return None
    except Exception as e:
        print(f"⚠️ خطا در ترجمه کامل: {e}")
        return None

def create_html_page(translated_text, title, original_link, date_str):
    """ساخت صفحه HTML با طراحی مدرن و مدیریت خطای content_html"""
    
    # ✅ رفع باگ: همیشه content_html مقداردهی می‌شود
    if not translated_text or len(str(translated_text).strip()) < 10:
        content_html = "<p style='color: #64748b; font-style: italic;'>متاسفانه متن کامل این خبر در دسترس نیست یا سایت منبع دسترسی را مسدود کرده است. می‌توانید از لینک پایین خبر اصلی را مطالعه کنید.</p>"
    else:
        paragraphs = str(translated_text).split('\n\n')
        content_html = "".join([f"<p>{p}</p>" for p in paragraphs if p.strip()])

    css_style = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;900&display=swap');
        :root {
            --primary: #2563eb; --primary-dark: #1d4ed8; --bg: #f8fafc;
            --surface: #ffffff; --text-main: #0f172a; --text-muted: #64748b; --border: #e2e8f0;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Vazirmatn', system-ui, -apple-system, sans-serif;
            background-color: var(--bg); color: var(--text-main); line-height: 1.8;
            direction: rtl; -webkit-font-smoothing: antialiased;
        }
        .wrapper {
            max-width: 720px; margin: 40px auto; background: var(--surface);
            border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            overflow: hidden; border: 1px solid var(--border);
        }
        .header { padding: 40px 40px 20px 40px; border-bottom: 1px solid var(--border); }
        .badge {
            display: inline-block; background: #eff6ff; color: var(--primary);
            font-size: 0.8rem; font-weight: 700; padding: 4px 12px;
            border-radius: 9999px; margin-bottom: 16px;
        }
        .header h1 { font-size: 1.75rem; font-weight: 900; line-height: 1.4; margin-bottom: 16px; }
        .meta { display: flex; align-items: center; gap: 16px; font-size: 0.875rem; color: var(--text-muted); }
        .content { padding: 40px; font-size: 1.125rem; color: #334155; }
        .content p { margin-bottom: 1.5rem; text-align: justify; }
        .footer {
            background: #f8fafc; padding: 24px 40px; border-top: 1px solid var(--border);
            display: flex; flex-direction: column; align-items: center; gap: 16px;
        }
        .btn {
            display: inline-flex; align-items: center; justify-content: center; gap: 8px;
            background: var(--primary); color: white; text-decoration: none;
            padding: 12px 24px; border-radius: 8px; font-weight: 600;
            transition: all 0.2s ease; width: 100%; max-width: 300px;
        }
        .btn:hover { background: var(--primary-dark); transform: translateY(-1px); }
        .btn-outline { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
        .btn-outline:hover { background: #f1f5f9; color: var(--text-main); }
        .watermark { font-size: 0.8rem; color: var(--text-muted); text-align: center; }
        @media (max-width: 640px) {
            .wrapper { margin: 0; border-radius: 0; border: none; }
            .header, .content, .footer { padding: 24px; }
            .header h1 { font-size: 1.4rem; }
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
    <div class="wrapper">
        <div class="header">
            <span class="badge">هوش مصنوعی و تکنولوژی</span>
            <h1>{title}</h1>
            <div class="meta">
                <span>📅 {date_str}</span>
                <span>⏱️ زمان مطالعه: ~۲ دقیقه</span>
            </div>
        </div>
        <div class="content">
            {content_html}
        </div>
        <div class="footer">
            <a href="{original_link}" target="_blank" class="btn">🔗 مشاهده منبع اصلی خبر</a>
            <div class="watermark">تهیه و تنظیم توسط ربات خبررسان هوش مصنوعی</div>
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
🚀 *خبر جدید هوش مصنوعی*

📰 *{title}*

🧠 *خلاصه:*
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
        else:
            print("⚠️ متن کامل دریافت نشد، از خلاصه RSS استفاده می‌شود.")
            translated_text = summarize(item["summary"]) + "\n\n(توجه: سایت منبع اجازه استخراج متن کامل را نداد، این متن بر اساس خلاصه RSS تولید شده است.)"
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = create_html_page(translated_text, item['title'], link, now_str)
        
        news_id = generate_news_id(link)
        html_url = save_html_page(html_content, news_id)
        
        await send_to_telegram(item['title'], summary, link, html_url)
        save_sent_news(link)
        
        return True
        
    except Exception as e:
        print(f"❌ خطا در پردازش خبر: {e}")
        import traceback
        traceback.print_exc()
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