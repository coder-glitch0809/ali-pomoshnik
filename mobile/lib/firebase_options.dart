// VAQTINCHALIK: `flutterfire configure --project=<loyiha-id>` bu faylni haqiqiy sozlamalar bilan almashtiradi.
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform =>
      throw UnsupportedError('Firebase hali ulanmagan: mobile papkasida `flutterfire configure` ni ishga tushiring.');
}
