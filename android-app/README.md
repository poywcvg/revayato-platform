# روایتو — اپ Native اندروید

اپ مستقل Android Native که مستقیماً به API روایتو متصل می‌شود و رابط کاتالوگ، جستجو، جزئیات، ورود، دانلود و پلیر Media3 را ارائه می‌کند.
بدونِ هیچ تغییری در کد وب، تمام امکانات سایت درون اپ کار می‌کند:

- مرور کاتالوگ، جستجو، جزئیات فیلم/سریال
- پخش آنلاین (HLS + MP4) با دکمه تمام‌صفحه که مثل مرورگر گوشی، افقی قفل می‌شود
- ورود و ثبت‌نام (کوکی‌های JWT — با پاک نشدن داده اپ، ورود پس از بستن و بازکردن باقی می‌ماند)
- زیرنویس، دوبله، دسته‌بندی‌ها
- تماشای گروهی (watch-party) با WebSocket زنده (`wss://revayato.com/ws`)
- دانلود فایل‌ها **داخل خود اپ** با نوتیفیکیشن پیشرفت و ذخیره در `Downloads/Revayato/`
- داشبورد و پنل مدیریت (برای حساب‌های با سطح دسترسی staff)

سایت مقصد به‌صورت ثابت `https://revayato.com/` است؛ لینک‌های دیگر دامنه‌ها
(مثلاً تلگرام، TMDB) در مرورگر سیستمی باز می‌شوند.

## ساخت APK

پیش‌نیازها: JDK 17+ و Android SDK (پروژه با `local.properties` به
`sdk.dir=C:\Android` اشاره می‌کند؛ نسخه 35). Gradle نسخه 8.10.2 از قبل در کش
wrapper است؛ این پروژه هیچ وابستگی خارجی ندارد (فقط platform Android).

```powershell
# از ریشه ریپو (جایی که پوشه‌های frontend/ backend/ android-app/ هستند):
    powershell -ExecutionPolicy Bypass -File tools/build-android-apk.ps1

# خروجی: android-app/dist/revayato-native-v5.0.0.apk
```

امضا با همان `debug.keystore` (کلید CURRENT APK های قدیمی) انجام می‌شود،
پس روی همان دستگاه‌ها جایگزین/نصب می‌شود. برای فروشگاه/انتشار واقعی، یک
keystore اختصاصی بسازید و در `android-app/app/build.gradle` به‌جای
`signingConfigs.debug` قرار دهید (بخش `signingConfigs`).

## بررسی روی دستگاه

```powershell
# نصب مستقیم (adb در platform-tools SDK)
& "$env:LOCALAPPDATA\..\..\Android\platform-tools\adb.exe" install -r android-app/dist/revayato-android-v2.0.0.apk
```

نکته: برای تست در محیط توسعه که می‌خواهید به سرور محلی/LAN اشاره کنید،
مقدار `APP_URL` در `MainActivity.java` را موقتاً تغییر دهید و دوباره بسازید
(در این حالت برای HTTP باید `cleartextTraffic` را در manifest فعال کنید).

## ساختار

```
android-app/
├─ app/src/main/java/com/revayato/app/
│   ├─ MainActivity.java       # کاتالوگ، جزئیات، جستجو، امتیازها، دانلود
│   ├─ PlayerActivity.java     # پلیر Media3 (HLS/MP4/MKV، زیرنویس، قفل، PiP)
│   ├─ WatchPartyActivity.java # لابی تماشای گروهی
│   ├─ AuthActivity.java       # ورود / ثبت‌نام / بازیابی رمز
│   └─ ImageLoader.java        # بارگذاری و کش تصاویر
├─ app/src/main/AndroidManifest.xml
├─ app/src/main/res/           # تم تیره #050807، اسپلش، آیکون از سایت
├─ app/build.gradle            # applicationId com.revayato.app, minSdk 24
└─ dist/                       # خروجی‌های build (آخرین: revayato-native-v5.0.0.apk)
```

رابط همه صفحات با تم تیره یکپارچه #050807 ساخته شده و متن‌ها و ردیف‌ها
با بزرگی فونت سیستم (Accessibility) اسکیل می‌شوند؛ پلیر در صورت
پاسخ‌ندادن منبع، همان منبع را یک‌بار دوباره امتحان می‌کند و سپس
هوشمندانه به منبع بعدی سوییچ می‌کند.
