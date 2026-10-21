import 'dart:io';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../config.dart';
import 'device.dart';

/// Ali so'raydigan bitta ruxsat: nomi, nima uchun kerakligi va tizim ruxsatlari.
class AppPermission {
  const AppPermission({
    required this.key,
    required this.title,
    required this.why,
    required this.icon,
    this.permissions = const [],
    this.accessibility = false,
  });

  final String key;
  final String title;
  final String why;
  final IconData icon;
  final List<Permission> permissions;

  /// Android "Maxsus imkoniyatlar" xizmati (faqat to'liq APK versiyada) - tizim sozlamasida yoqiladi.
  final bool accessibility;

  Future<bool> isGranted() async {
    if (accessibility) return Device.accessibilityEnabled();
    for (final p in permissions) {
      final status = await p.status;
      if (!status.isGranted && !status.isLimited) return false;
    }
    return true;
  }

  /// Ruxsat so'raydi. Avval butunlay rad etilgan bo'lsa (qayta so'rab bo'lmaydi) - ilova sozlamalarini ochadi.
  Future<bool> request() async {
    if (accessibility) {
      await Device.openAccessibilitySettings();
      return false; // foydalanuvchi sozlamadan qaytgach qayta tekshiriladi
    }
    var all = true;
    for (final p in permissions) {
      var status = await p.request();
      if (status.isPermanentlyDenied) {
        await openAppSettings();
        status = await p.status;
      }
      all = all && (status.isGranted || status.isLimited);
    }
    return all;
  }
}

List<AppPermission> appPermissions() {
  final android = Platform.isAndroid;
  return [
    AppPermission(
      key: 'microphone',
      title: 'Mikrofon',
      why: 'Ovoz bilan savol berish uchun. Faqat siz tugmani bosganingizda yoziladi.',
      icon: Icons.mic_none,
      permissions: [Permission.microphone, if (!android) Permission.speech],
    ),
    const AppPermission(
      key: 'camera',
      title: 'Kamera',
      why: 'Rasmga olib savol berish uchun.',
      icon: Icons.photo_camera_outlined,
      permissions: [Permission.camera],
    ),
    const AppPermission(
      key: 'photos',
      title: 'Rasmlar va videolar',
      why: 'Galereyadan rasm tanlab yuborish uchun.',
      icon: Icons.photo_library_outlined,
      permissions: [Permission.photos],
    ),
    const AppPermission(
      key: 'location',
      title: 'Joylashuv',
      why: 'Ob-havo, yaqin joylar va yo‘l haqidagi savollar uchun.',
      icon: Icons.location_on_outlined,
      permissions: [Permission.locationWhenInUse],
    ),
    const AppPermission(
      key: 'contacts',
      title: 'Kontaktlar',
      why: '“Onamga qo‘ng‘iroq qil” kabi buyruqlar uchun. Kontaktlar serverga yuborilmaydi.',
      icon: Icons.contacts_outlined,
      permissions: [Permission.contacts],
    ),
    const AppPermission(
      key: 'calendar',
      title: 'Kalendar',
      why: 'Uchrashuv va eslatmalarni qo‘shish uchun.',
      icon: Icons.event_outlined,
      permissions: [Permission.calendarFullAccess],
    ),
    const AppPermission(
      key: 'notifications',
      title: 'Bildirishnomalar',
      why: 'Eslatmalar va javoblar haqida xabar berish uchun.',
      icon: Icons.notifications_none,
      permissions: [Permission.notification],
    ),
    if (android && isFullFlavor)
      const AppPermission(
        key: 'files',
        title: 'Barcha fayllar',
        why: 'Telefondagi hujjat va fayllarni topish, ochish va saqlash uchun.',
        icon: Icons.folder_open_outlined,
        permissions: [Permission.manageExternalStorage],
      ),
    if (android && isFullFlavor)
      const AppPermission(
        key: 'accessibility',
        title: 'Boshqa ilovalarni boshqarish',
        why: 'Siz buyurganda boshqa ilovalarda tugma bosish, matn yozish, orqaga yoki bosh ekranga qaytish uchun. '
            'Ochilgan sozlamalarda “Ali” xizmatini yoqing.',
        icon: Icons.touch_app_outlined,
        accessibility: true,
      ),
  ];
}

Future<Map<String, bool>> permissionStatuses() async {
  final result = <String, bool>{};
  for (final p in appPermissions()) {
    result[p.key] = await p.isGranted();
  }
  return result;
}
