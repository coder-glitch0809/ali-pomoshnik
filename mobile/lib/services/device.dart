import 'dart:io';

import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';

/// Telefonda amal bajarish: ilova/sayt/sozlama ochish, qo'ng'iroq, boshqa ilovalarni boshqarish.
class Device {
  static const _channel = MethodChannel('uz.ali/device');

  /// iPhone'da boshqa ilovalar faqat URL sxemasi orqali ochiladi (Info.plist -> LSApplicationQueriesSchemes).
  static const _iosSchemes = {
    'telegram': 'tg://',
    'instagram': 'instagram://',
    'whatsapp': 'whatsapp://',
    'youtube': 'youtube://',
    'facebook': 'fb://',
    'tiktok': 'snssdk1233://',
    'spotify': 'spotify://',
    'maps': 'maps://',
    'xarita': 'maps://',
    'google maps': 'comgooglemaps://',
    'gmail': 'googlegmail://',
    'chrome': 'googlechrome://',
    'yandex navigator': 'yandexnavi://',
  };

  static Future<bool> accessibilityEnabled() async {
    if (!Platform.isAndroid || !isFullFlavor) return false;
    try {
      return await _channel.invokeMethod<bool>('accessibilityEnabled') ?? false;
    } on PlatformException {
      return false;
    }
  }

  static Future<void> openAccessibilitySettings() async {
    if (Platform.isAndroid) await _channel.invokeMethod('openAccessibilitySettings');
  }

  /// Serverga yuboriladigan imkoniyatlar - server faqat shu amallarni taklif qiladi.
  static Future<List<String>> capabilities() async {
    final caps = ['web', 'phone', 'settings', 'apps'];
    if (await accessibilityEnabled()) caps.add('control');
    return caps;
  }

  /// Bu amallar bajarilishidan oldin foydalanuvchidan alohida tasdiq so'raladi.
  static bool needsConfirm(Map<String, dynamic> action) =>
      const {'click_text', 'type_text', 'call', 'sms'}.contains(action['type']);

  static String describe(Map<String, dynamic> action) {
    final target = action['target'] ?? '';
    switch (action['type']) {
      case 'open_app':
        return '“$target” ilovasini ochish';
      case 'open_url':
        return 'Saytni ochish: $target';
      case 'open_settings':
        return 'Sozlamalarni ochish: $target';
      case 'call':
        return 'Qo‘ng‘iroq: $target';
      case 'sms':
        return 'SMS: $target';
      case 'global':
        return 'Tizim amali: $target';
      case 'click_text':
        return '“$target” tugmasini bosish';
      case 'type_text':
        return 'Matn yozish: $target';
    }
    return '$action';
  }

  static Future<String> run(Map<String, dynamic> action) async {
    final type = action['type'] as String? ?? '';
    final target = (action['target'] as String? ?? '').trim();
    try {
      switch (type) {
        case 'open_url':
          return await _launch(target) ? 'Ochildi' : 'Ochib bo‘lmadi';
        case 'call':
          return await _launch('tel:${target.replaceAll(' ', '')}') ? 'Qo‘ng‘iroq oynasi ochildi' : 'Ochib bo‘lmadi';
        case 'sms':
          final body = Uri.encodeComponent(action['text'] as String? ?? '');
          return await _launch('sms:${target.replaceAll(' ', '')}?body=$body') ? 'SMS oynasi ochildi' : 'Ochib bo‘lmadi';
        case 'open_app':
          if (Platform.isAndroid) {
            return await _channel.invokeMethod<String>('openApp', {'name': target}) ?? 'Ilova topilmadi';
          }
          final scheme = _iosSchemes[target.toLowerCase()];
          return scheme != null && await _launch(scheme) ? 'Ochildi' : 'iPhone’da bu ilovani ochib bo‘lmadi';
        case 'open_settings':
          if (Platform.isAndroid) {
            return await _channel.invokeMethod<String>('openSettings', {'target': target}) ?? 'Ochildi';
          }
          await openAppSettings(); // iPhone faqat ilovaning o'z sozlamalarini ochishga ruxsat beradi
          return 'Sozlamalar ochildi';
        case 'global':
        case 'click_text':
        case 'type_text':
          if (!await accessibilityEnabled()) return 'Avval “Boshqa ilovalarni boshqarish” ruxsatini yoqing';
          return await _channel.invokeMethod<String>(type, {'target': target}) ?? 'Bajarildi';
      }
    } on PlatformException catch (e) {
      return 'Xato: ${e.message}';
    }
    return 'Noma’lum amal';
  }

  static Future<bool> _launch(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return false;
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } on PlatformException {
      return false;
    }
  }
}
