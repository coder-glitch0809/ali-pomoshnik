/// Yig'ish sozlamalari: --dart-define=FLAVOR=full (APK, to'liq boshqaruv) yoki store (Play Market / App Store).
const String kFlavor = String.fromEnvironment('FLAVOR', defaultValue: 'store');
const String kServer = String.fromEnvironment('ALI_SERVER', defaultValue: 'https://ali-pomoshnik.vercel.app');
const String kPrivacyUrl = '$kServer/privacy';

bool get isFullFlavor => kFlavor == 'full';
