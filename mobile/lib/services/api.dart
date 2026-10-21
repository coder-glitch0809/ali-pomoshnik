import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';
import 'device.dart';

class AliReply {
  AliReply(this.reply, this.actions, this.left);

  final String reply;
  final List<Map<String, dynamic>> actions;
  final int? left;
}

class AliApiException implements Exception {
  AliApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Ali bulut serveri bilan aloqa. Firebase ID tokeni har so'rovda yuboriladi.
class AliApi {
  static String? _base;

  /// Vercel manzili faqat GET so'rovlarini serverga yo'naltiradi, shuning uchun haqiqiy server manzili
  /// /api/mobile/ping orqali bilib olinadi va saqlab qo'yiladi.
  static Future<String> _baseUrl() async {
    if (_base != null) return _base!;
    final prefs = await SharedPreferences.getInstance();
    try {
      final r = await http.get(Uri.parse('$kServer/api/mobile/ping')).timeout(const Duration(seconds: 20));
      final base = _json(r.bodyBytes)['base'] as String?;
      if (r.statusCode == 200 && base != null && base.startsWith('https://')) {
        await prefs.setString('server_base', base);
        return _base = base;
      }
    } catch (_) {
      // tarmoq yo'q - oxirgi ma'lum manzil ishlatiladi
    }
    return _base = prefs.getString('server_base') ?? kServer;
  }

  static Future<AliReply> ask(String text, List<Map<String, String>> history, String name) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) throw AliApiException('Avval tizimga kiring');
    final token = await user.getIdToken();
    final body = jsonEncode({
      'text': text,
      'history': history,
      'name': name,
      'platform': Platform.isIOS ? 'ios' : 'android',
      'capabilities': await Device.capabilities(),
    });
    http.Response r;
    try {
      r = await http
          .post(Uri.parse('${await _baseUrl()}/api/mobile/ask'),
              headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'}, body: body)
          .timeout(const Duration(seconds: 90));
    } on Exception {
      _base = null;
      throw AliApiException('Serverga ulanib bo‘lmadi. Internetni tekshiring.');
    }
    final data = _json(r.bodyBytes);
    if (r.statusCode != 200) {
      throw AliApiException(data['detail']?.toString() ?? 'Server xatosi (${r.statusCode})');
    }
    final actions = (data['actions'] as List? ?? []).whereType<Map>().map((a) => Map<String, dynamic>.from(a)).toList();
    return AliReply(data['reply'] as String? ?? '', actions, data['left'] as int?);
  }

  /// FastAPI JSON javobida charset ko'rsatilmaydi - matnni har doim UTF-8 deb o'qiymiz.
  static Map<String, dynamic> _json(List<int> bytes) {
    try {
      final v = jsonDecode(utf8.decode(bytes, allowMalformed: true));
      return v is Map<String, dynamic> ? v : {};
    } on FormatException {
      return {};
    }
  }
}
