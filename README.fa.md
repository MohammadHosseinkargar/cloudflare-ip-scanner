<div dir="rtl">

# جعبه‌ابزار Cloudflare CDN

یک برنامه دسکتاپ با تم تیره و رنگ سبز نئونی (ویندوز / مک / لینوکس) که
کمک می‌کند **سریع‌ترین آی‌پی‌های Cloudflare** را برای کانفیگ VLESS خودتان
پیدا کنید و دامنه‌تان را به آن‌ها وصل کنید — همه در یک پنجره.

**زبان‌های دیگر:** [English](README.md)

---

## این برنامه چه کار می‌کند؟

۱. **SCAN (اسکن)** — از لینک ساب (لیست کانفیگ VLESS) فقط آی‌پی‌های Cloudflare
روی پورت ۴۴۳ را جدا می‌کند و پینگ می‌گیرد تا آی‌پی‌های زنده پیدا شوند.

۲. **SPEED (تست سرعت)** — با استفاده از `xray-core` مثل v2rayN یک تست سرعت
واقعی روی هر آی‌پی می‌گیرد و از سریع‌ترین به کندترین مرتب می‌کند.

۳. **DNS** — رکوردهای A دامنه شما در Cloudflare را با آی‌پی‌های برتر تست
سرعت با یک کلیک جایگزین می‌کند.

۴. **PROFILES (پروفایل)** — همه تنظیمات (UUID، SNI، هاست، پس، پورت، توکن
API، Zone ID، نام رکورد، لینک ساب) را ذخیره می‌کند تا هر بار تایپ نکنید.

## شروع سریع

### ۱. نصب پایتون ۳.۱۱ یا بالاتر
از https://www.python.org/downloads/ دانلود کنید
(تیک «Add Python to PATH» را بزنید).

### ۲. دانلود پروژه
روی دکمه سبز **Code** در گیت‌هاب کلیک کنید → **Download ZIP**، بعد اکسترکت
کنید. یا با گیت:

<div dir="ltr">

```bash
git clone https://github.com/MohammadHosseinkargar/cloudflare-ip-scanner.git
cd cloudflare-ip-scanner
```

</div>

### ۳. نصب پیش‌نیازها
در پوشه پروژه ترمینال باز کنید و بزنید:

<div dir="ltr">

```bash
pip install -r requirements.txt
```

</div>

### ۴. دریافت xray-core (برای تست سرعت لازم است)
فایل `xray.exe` (ویندوز) یا `xray` (مک/لینوکس) را از
https://github.com/XTLS/Xray-core/releases دانلود کنید و **کنار `app.py`**
بگذارید (یا هر جایی روی PATH).

### ۵. اجرای برنامه

<div dir="ltr">

```bash
python app.py
```

</div>

## گرفتن API Token از Cloudflare

۱. برو به https://dash.cloudflare.com/profile/api-tokens

۲. روی **Create Token** بزن و قالب **Edit zone DNS** را انتخاب کن.

۳. در قسمت *Zone Resources* دامنه‌ای که می‌خواهی مدیریت کنی را انتخاب کن.

۴. توکن را کپی کن و در برنامه بگذار.

۵. **Zone ID** در سمت راست صفحه‌ی Overview دامنه‌ات پیدا می‌شود.

## نکته‌ها

- اول تب **SCAN**، بعد **SPEED**، در آخر **DNS** را استفاده کن.
- یک **Profile** ذخیره کن تا دفعه بعد با یک کلیک همه تنظیمات بیاید.
- تب DNS رکوردها را به صورت *DNS only* (ابر خاکستری) با TTL Auto می‌سازد.
- هیچ اطلاعاتی از کامپیوترت خارج نمی‌شود به جز درخواست‌ها به Cloudflare
  و لینک ساب خودت.

## فایل‌های پروژه

<div dir="ltr">

```
app.py              # برنامه اصلی (این را اجرا کن)
scanner.py          # پارس ساب + پینگ آی‌پی
xray_test.py        # تست سرعت واقعی با xray-core
cloudflare_api.py   # کلاینت Cloudflare API v4
utils.py            # توابع کمکی
gui.py / main.py    # نسخه قدیمی فقط-DNS (اختیاری)
requirements.txt
```

</div>

## مجوز

MIT — هر کاری خواستی بکن، بدون ضمانت.

</div>
