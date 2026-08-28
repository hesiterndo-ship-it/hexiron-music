# HexIron Music Bot

## نصب و اجرا روی سیستم شخصی (Windows / macOS / Linux)

### پیش‌نیازها
- Python 3.10 یا بالاتر ([python.org](https://www.python.org/downloads/))
- (اختیاری ولی توصیه‌شده) ffmpeg نصب‌شده روی سیستم:
  - Windows: `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` یا معادلش

### مراحل
```bash
# ۱. پوشه‌ی پروژه رو extract کن و برو داخلش
cd HexIronMusic

# ۲. یک virtual environment بساز (اختیاری ولی توصیه‌شده)
python -m venv venv
# ویندوز:
venv\Scripts\activate
# مک/لینوکس:
source venv/bin/activate

# ۳. وابستگی‌ها رو نصب کن
pip install -r requirements.txt

# ۴. فایل .env بساز
cp .env.example .env
# حالا .env رو با ویرایشگر متن باز کن و مقادیر واقعی رو بنویس
```

### مقادیر لازم در `.env`
- `BOT_TOKEN` — از [@BotFather](https://t.me/BotFather)
- `API_ID`, `API_HASH` — از https://my.telegram.org
- `OWNER_ID` — آیدی عددی تلگرام خودت
- `STRING_SESSION` — با اجرای دستور زیر (فقط یک‌بار) ساخته می‌شه:
  ```bash
  python generate_session.py
  ```
  شماره تلفن یه اکانت **مجزا** (نه اکانت اصلی خودت) رو وارد کن، کد تأیید رو بزن، و رشته‌ای که چاپ می‌شه رو در `.env` جلوی `STRING_SESSION=` بذار.

### اجرا
```bash
python main.py
```

## دستورات ربات
- `/start` — راهنما (فقط در چت خصوصی)
- `/admin` — پنل مدیریت (فقط مالک، بر اساس `OWNER_ID`)
- `/play <اسم آهنگ>` — پخش یا افزودن به صف (فقط داخل گروه)
- `/pause` `/resume` `/skip` `/stop`
- `/queue` — نمایش صف پخش

## معماری: چرا دو تا اکانت (bot + userbot)؟
تلگرام به اکانت‌های bot اجازه نمی‌ده وارد یا میزبان ویس‌چت گروه بشن
(خطای `BOT_METHOD_INVALID`). برای همین:
- **bot** (با `BOT_TOKEN`) فقط دستورات متنی رو مدیریت می‌کنه
- **userbot** (با `STRING_SESSION`) واقعاً وارد ویس‌چت می‌شه و صدا پخش می‌کنه

هر دو اکانت (هم bot، هم userbot) باید عضو گروهی باشن که می‌خوای توش پخش کنی.

## نکات مهم
- منبع موزیک: RadioJavan (از طریق پکیج `radiojavanapi`، غیررسمی و reverse-engineered — ممکنه با تغییرات RadioJavan از کار بیفته)
- دانلود آهنگ‌ها در پوشه‌ی `downloads/` کش می‌شن
- برای پخش صدا در ویس‌چت، **باید یک ویس‌چت از قبل در گروه باز باشه** — ربات خودش ویس‌چت نمی‌سازه
- اگه صدا پخش نمی‌شه ولی userbot در لیست شرکت‌کنندگان دیده می‌شه، احتمالاً ترافیک **UDP خروجی** روی شبکه‌ات بسته‌ست (پخش صدای ویس‌چت تلگرام از UDP استفاده می‌کنه، نه فقط TCP) — این معمولاً روی سیستم شخصی مشکلی نداره، ولی روی برخی هاست‌های محدود پیش میاد
