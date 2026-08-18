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
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/UniverseCreative/ai_news_bot",
                "X-Title": "Kafa Tech News Bot"
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
    """ساخت صفحه HTML با طراحی Ultra-Professional و مدرن"""
    
    if not translated_text or len(str(translated_text).strip()) < 10:
        content_html = """
        <div class="empty-state">
            <div class="empty-icon">📭</div>
            <p>متاسفانه متن کامل این خبر در دسترس نیست.</p>
            <p style="font-size: 0.9rem; color: #94a3b8; margin-top: 10px;">
                سایت منبع ممکن است دسترسی را مسدود کرده باشد.
            </p>
        </div>
        """
    else:
        paragraphs = str(translated_text).split('\n\n')
        content_html = "".join([f"<p>{p}</p>" for p in paragraphs if p.strip()])

    css_style = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100;300;400;500;700;900&display=swap');
        
        :root {
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            --bg-color: #0f172a;
            --surface-color: rgba(255, 255, 255, 0.98);
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --accent-color: #667eea;
            --border-color: rgba(148, 163, 184, 0.2);
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(102, 126, 234, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(118, 75, 162, 0.15) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            line-height: 1.8;
            direction: rtl;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            animation: fadeIn 0.6s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .header-card {
            background: var(--surface-color);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px;
            margin-bottom: 24px;
            box-shadow: var(--shadow-xl);
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
        }

        .header-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--primary-gradient);
        }

        .category-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 700;
            margin-bottom: 24px;
            box-shadow: var(--shadow-md);
        }

        .header-card h1 {
            font-size: 2rem;
            font-weight: 900;
            line-height: 1.4;
            margin-bottom: 20px;
            background: linear-gradient(135deg, #1e293b 0%, #667eea 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .meta-info {
            display: flex;
            align-items: center;
            gap: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        .meta-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .meta-icon {
            width: 18px;
            height: 18px;
            opacity: 0.6;
        }

        .content-card {
            background: var(--surface-color);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px;
            margin-bottom: 24px;
            box-shadow: var(--shadow-xl);
            border: 1px solid var(--border-color);
        }

        .content-card p {
            font-size: 1.125rem;
            line-height: 2;
            color: var(--text-primary);
            margin-bottom: 24px;
            text-align: justify;
            font-weight: 400;
        }

        .content-card p:last-child {
            margin-bottom: 0;
        }

        .content-card p:first-letter {
            font-size: 3.5rem;
            font-weight: 900;
            float: right;
            margin-left: 8px;
            line-height: 1;
            color: var(--accent-color);
        }

        .actions-card {
            background: var(--surface-color);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 32px;
            box-shadow: var(--shadow-xl);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            padding: 16px 32px;
            border-radius: 16px;
            font-size: 1rem;
            font-weight: 700;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none;
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }

        .btn-primary {
            background: var(--primary-gradient);
            color: white;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.5);
        }

        .btn-primary:active {
            transform: translateY(0);
        }

        .btn-secondary {
            background: rgba(148, 163, 184, 0.1);
            color: var(--text-primary);
            border: 2px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: rgba(148, 163, 184, 0.2);
            border-color: var(--accent-color);
        }

        .btn-icon {
            width: 20px;
            height: 20px;
        }

        .footer {
            text-align: center;
            padding: 32px;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }

        .footer-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
        }

        .empty-icon {
            font-size: 4rem;
            margin-bottom: 16px;
            opacity: 0.5;
        }

        @media (max-width: 768px) {
            body {
                padding: 12px;
            }

            .header-card,
            .content-card,
            .actions-card {
                padding: 24px;
                border-radius: 20px;
            }

            .header-card h1 {
                font-size: 1.5rem;
            }

            .content-card p {
                font-size: 1rem;
            }

            .content-card p:first-letter {
                font-size: 2.5rem;
            }

            .meta-info {
                flex-direction: column;
                gap: 12px;
                align-items: flex-start;
            }

            .btn {
                width: 100%;
            }
        }

        ::-webkit-scrollbar {
            width: 10px;
        }

        ::-webkit-scrollbar-track {
            background: rgba(148, 163, 184, 0.1);
            border-radius: 10px;
        }

        ::-webkit-scrollbar-thumb {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        }
    </style>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{title[:150]}">
    {css_style}
</head>
<body>
    <div class="container">
        <div class="header-card">
            <div class="category-badge">
                <span></span>
                <span>هوش مصنوعی و تکنولوژی</span>
            </div>
            <h1>{title}</h1>
            <div class="meta-info">
                <div class="meta-item">
                    <svg class="meta-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                    </svg>
                    <span>{date_str}</span>
                </div>
                <div class="meta-item">
                    <svg class="meta-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span>زمان مطالعه: ~۲ دقیقه</span>
                </div>
            </div>
        </div>

        <div class="content-card">
            {content_html}
        </div>

        <div class="actions-card">
            <a href="{original_link}" target="_blank" class="btn btn-primary">
                <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
                </svg>
                مشاهده منبع اصلی خبر
            </a>
            <a href="https://t.me/KafaTechNews" class="btn btn-secondary">
                <svg class="btn-icon" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/>
                </svg>
                بازگشت به کانال تلگرام
            </a>
        </div>

        <div class="footer">
            <div class="footer-brand">
                <span>🤖</span>
                <span>Kafa Tech News Agent</span>
            </div>
            <p style="margin-top: 8px; opacity: 0.7;">تهیه و تنظیم توسط ربات خبررسان هوش مصنوعی</p>
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

 *{title}*

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