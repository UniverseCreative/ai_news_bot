import os
import json
import feedparser
import requests
import asyncio
import base64
import hashlib
import subprocess
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# خواندن env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

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

# فایل JSON محلی
SENT_FILE = "sent_news.json"

# تنظیمات GitHub
REPO_OWNER = "UniverseCreative"
REPO_NAME = "ai_news_bot"
BRANCH = "main"
PAGES_DIR = "docs/pages/"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{PAGES_DIR}"

def load_sent_news():
    """بارگذاری از فایل JSON محلی"""
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print("⚠️ فایل حافظه خالی است")
                return {}
            data = json.loads(content)
            if isinstance(data, list):
                return {item: datetime.now().isoformat() for item in data}
            return data
    except FileNotFoundError:
        print("ℹ️ فایل حافظه وجود ندارد، شروع با حافظه خالی")
        return {}
    except json.JSONDecodeError:
        print("⚠️ فایل حافظه خراب است، شروع با حافظه خالی")
        return {}
    except Exception as e:
        print(f"❌ خطا در بارگذاری حافظه: {e}")
        return {}

def save_sent_news(link):
    """ذخیره در فایل JSON محلی"""
    try:
        data = load_sent_news()
        data[link] = datetime.now().isoformat()
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ خبر ذخیره شد (تعداد کل: {len(data)})")
    except Exception as e:
        print(f"❌ خطا در ذخیره‌سازی حافظه: {e}")

def get_news():
    """گرفتن اخبار از RSS"""
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
    """خلاصه‌سازی خبر"""
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

def translate_full_text(text):
    """ترجمه کامل خبر به فارسی"""
    if not text or len(text.strip()) < 50:
        return "متن کامل برای این خبر در دسترس نیست."
    
    prompt = f"""
    متن کامل خبر زیر را به فارسی روان و حرفه‌ای ترجمه کن.
    فقط ترجمه را بنویس، بدون هیچ برچسب اضافی.
    اسامی خاص (شرکت‌ها، محصولات، افراد) را به انگلیسی حفظ کن.

    متن خبر:
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
                "max_tokens": 800
            },
            timeout=45
        )
        
        result = response.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return "ترجمه کامل در دسترس نیست."
            
    except Exception as e:
        print(f"خطا در ترجمه کامل: {e}")
        return "ترجمه کامل در دسترس نیست."

def create_html_page(translated_text, title, original_link):
    """ساخت صفحه HTML برای نمایش ترجمه"""
    if not translated_text or len(translated_text.strip()) < 10:
        translated_text = "متن کامل برای این خبر در دسترس نیست."
    
    html_content = f"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - ترجمه خبر</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
            color: #333;
            line-height: 1.8;
        }}
        .container {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            font-size: 1.5em;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin-bottom: 20px;
            border-bottom: 1px solid #eee;
            padding-bottom: 15px;
        }}
        .content {{
            margin: 20px 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .back-btn {{
            display: inline-block;
            background-color: #3498db;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 5px;
            font-weight: bold;
            margin-top: 20px;
            transition: background-color 0.3s;
        }}
        .back-btn:hover {{
            background-color: #2980b9;
        }}
        .footer {{
            margin-top: 30px;
            text-align: center;
            color: #95a5a6;
            font-size: 0.8em;
        }}
        .original-link {{
            color: #3498db;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📰 {title}</h1>
        <div class="meta">
            <span>📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
            <span style="margin-right: 15px;">🔗 <a href="{original_link}" class="original-link" target="_blank">مشاهده خبر اصلی</a></span>
        </div>
        <div class="content">
            {translated_text.replace('\n', '<br>')}
        </div>
        <div style="text-align: center;">
            <a href="javascript:window.close()" class="back-btn">🔙 بازگشت به تلگرام</a>
        </div>
        <div class="footer">
            <p>🤖 تولید شده توسط ربات خبررسان هوش مصنوعی</p>
        </div>
    </div>
</body>
</html>
    """
    return html_content

def save_html_page(html_content, news_id):
    """ذخیره صفحه HTML در مخزن با GitHub API"""
    try:
        if not GITHUB_TOKEN:
            print("❌ توکن GitHub وجود ندارد!")
            return None
            
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        
        file_path = f"{PAGES_DIR}news_{news_id}.html"
        
        # بررسی وجود فایل
        check_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_path}"
        get_response = requests.get(check_url, headers=headers)
        sha = None
        if get_response.status_code == 200:
            sha = get_response.json().get("sha")
        
        # آماده‌سازی برای آپلود
        encoded_content = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
        
        payload = {
            "message": f"افزودن ترجمه خبر {news_id}",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha
        
        put_response = requests.put(check_url, headers=headers, json=payload)
        
        if put_response.status_code in [200, 201]:
            print(f"✅ صفحه HTML ذخیره شد: news_{news_id}.html")
            return f"https://{REPO_OWNER}.github.io/{REPO_NAME}/pages/news_{news_id}.html"
        else:
            print(f"❌ خطا در ذخیره صفحه: {put_response.status_code}")
            print(put_response.text)
            return None
            
    except Exception as e:
        print(f"❌ خطا در ذخیره صفحه: {e}")
        return None

def get_full_text_from_link(url):
    """دریافت متن کامل خبر از لینک"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # استخراج متن با BeautifulSoup (نیاز به نصب)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # حذف تگ‌های غیرضروری
            for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside']):
                tag.decompose()
            
            # پیدا کردن متن اصلی
            article = soup.find('article') or soup.find('main') or soup.body
            if article:
                paragraphs = article.find_all('p')
                full_text = " ".join([p.get_text(strip=True) for p in paragraphs[:15]])
            else:
                full_text = soup.get_text(strip=True)[:3000]
            
            return full_text if len(full_text) > 100 else None
        except ImportError:
            print("⚠️ BeautifulSoup نصب نیست، از متن خلاصه استفاده می‌شود")
            return None
            
    except Exception as e:
        print(f"خطا در دریافت متن کامل: {e}")
        return None

def generate_news_id(link):
    """تولید شناسه یکتا برای خبر"""
    return hashlib.md5(link.encode('utf-8')).hexdigest()[:8]

async def send_to_telegram(title, summary, link, full_translation=None, html_url=None):
    """ارسال خبر به تلگرام با دکمه متن کامل"""
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
    
    # اگر لینک HTML وجود دارد، به عنوان دکمه اضافه کن
    reply_markup = None
    if html_url:
        keyboard = [[InlineKeyboardButton("📖 متن کامل خبر به فارسی", url=html_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=message,
        reply_markup=reply_markup
    )

async def process_news_item(item, sent_news):
    """پردازش یک خبر"""
    link = item["link"]
    
    if link in sent_news:
        print(f"⏭ خبر تکراری رد شد: {link[:50]}...")
        return False
    
    print(f"🔄 در حال پردازش خبر: {item['title'][:30]}...")
    
    try:
        # خلاصه‌سازی
        summary = summarize(item["summary"])
        
        # دریافت متن کامل و ترجمه
        full_text = get_full_text_from_link(link)
        if full_text:
            translation = translate_full_text(full_text)
        else:
            translation = "متن کامل برای این خبر در دسترس نیست."
        
        # ایجاد HTML
        html_content = create_html_page(translation, item['title'], link)
        news_id = generate_news_id(link)
        html_url = save_html_page(html_content, news_id)
        
        # ارسال به تلگرام
        await send_to_telegram(item['title'], summary, link, translation, html_url)
        
        print("✅ ارسال شد")
        save_sent_news(link)
        return True
        
    except Exception as e:
        print(f"❌ خطا در پردازش خبر: {e}")
        return False

async def main():
    """اجرای اصلی ربات"""
    news = get_news()
    sent_news = load_sent_news()
    print(f"📊 تعداد اخبار موجود در حافظه: {len(sent_news)}")

    for item in news:
        await process_news_item(item, sent_news)

if __name__ == "__main__":
    asyncio.run(main())