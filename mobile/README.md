# Ali — telefon ilovasi (Flutter)

Android va iPhone uchun bitta kod. Ilova ochilganda ismni so'raydi, keyin har bir ruxsatni alohida so'raydi.
Foydalanuvchi Firebase'da email bilan ro'yxatdan o'tadi va Ali bulut serveri bilan suhbatlashadi.

## Versiyalar

| Versiya | Qayerga | Nimalar bor |
|---|---|---|
| `store` | Play Market, App Store | Mikrofon, kamera, rasmlar, joylashuv, kontaktlar, kalendar, bildirishnomalar; ilova, sayt va sozlamalarni ochish; qo'ng'iroq va SMS oynasi |
| `full` | Faqat saytdan yuklanadigan APK (Android) | `store` dagi hammasi + boshqa ilovalarni boshqarish (Accessibility: bosish, yozish, orqaga/uyga) + barcha fayllarga kirish |

`full` versiyani Play Market'ga yuklamang: Google Accessibility va "barcha fayllar" ruxsatini AI yordamchi
uchun rad etadi.

iPhone cheklovi: Apple boshqa ilovalarni boshqarishga va tizim sozlamalariga kirishga ruxsat bermaydi.
Ilova faqat standart ruxsatlarni so'raydi, boshqa ilovalarni URL sxemasi bilan ochadi (Telegram, Instagram...)
va o'zining sozlamalar sahifasini ochadi.

## Tuzilishi

```
lib/
  main.dart                  ism -> ruxsatlar -> kirish -> suhbat
  config.dart                FLAVOR, ALI_SERVER (--dart-define)
  firebase_options.dart      flutterfire configure yaratadi
  screens/                   name, permissions, auth, chat, settings
  services/
    api.dart                 POST /api/mobile/ask (Firebase ID token bilan)
    store.dart               Firestore: users/{uid}, users/{uid}/messages
    permissions.dart         so'raladigan ruxsatlar ro'yxati
    device.dart              telefonda amal bajarish (MethodChannel uz.ali/device)
android/app/src/main/.../MainActivity.kt   ilova/sozlama ochish, Accessibility ko'prigi
android/app/src/full/                      AliAccessibilityService + manifest (faqat full)
build.ps1                                  yig'ish (lotin harfli D:\dev\ali-mobile da)
```

## Bir martalik sozlash

1. Vositalar `D:\dev` da: Flutter SDK (`flutter`), JDK 17 (`jdk17`), Android SDK (`android-sdk`).
   Loyiha yo'lida kirill harflari bor, shuning uchun `build.ps1` yig'ishni `D:\dev\ali-mobile` da qiladi.
2. Firebase: `firebase login`, keyin `dart pub global activate flutterfire_cli` va
   `flutterfire configure --project=<loyiha-id> --platforms=android,ios`.
   Bu `lib/firebase_options.dart`, `android/app/google-services.json` va `ios/Runner/GoogleService-Info.plist` ni yaratadi.
3. Firebase Console → Authentication → Email/Password ni yoqing.
4. Xavfsizlik qoidalari: `cd ..\firebase && firebase deploy --only firestore`.
5. Serverda (Render) `FIREBASE_PROJECT_ID=<loyiha-id>` ni o'rnating.
6. iPhone (Mac'da): `ios/Podfile` ning `post_install` qismiga permission_handler ruxsatlarini qo'shing:
   ```ruby
   target.build_configurations.each do |config|
     config.build_settings['GCC_PREPROCESSOR_DEFINITIONS'] ||= ['$(inherited)',
       'PERMISSION_MICROPHONE=1', 'PERMISSION_SPEECH_RECOGNIZER=1', 'PERMISSION_CAMERA=1',
       'PERMISSION_PHOTOS=1', 'PERMISSION_LOCATION_WHENINUSE=1', 'PERMISSION_CONTACTS=1',
       'PERMISSION_EVENTS_FULL_ACCESS=1', 'PERMISSION_NOTIFICATIONS=1']
   end
   ```

## Yig'ish

```powershell
# To'liq APK (saytdan yuklash uchun)
powershell -ExecutionPolicy Bypass -File mobile\build.ps1 -Target full
# Play Market (AAB)
powershell -ExecutionPolicy Bypass -File mobile\build.ps1 -Target store
# iPhone (faqat Mac'da, Xcode bilan)
flutter build ipa --dart-define=FLAVOR=store
```

## Do'konlarga joylash

- **Play Market**: Google Play Console hisobi ($25). Release kalit (`keytool`) bilan imzolang. Data safety
  bo'limida: ism, email, xabarlar (Firebase), ovoz faqat qurilmada. Maxfiylik siyosati:
  `https://ali-pomoshnik.vercel.app/privacy`.
- **App Store**: Apple Developer hisobi ($99/yil) va Mac kerak. App Privacy bo'limini to'ldiring.
  Akkauntni ilova ichida o'chirish bor (Apple talabi).
