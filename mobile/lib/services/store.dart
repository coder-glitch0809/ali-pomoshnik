import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../config.dart';

/// Firestore: users/{uid} - profil, users/{uid}/messages - suhbat. Xavfsizlik qoidalari
/// (firebase/firestore.rules) har kimga faqat o'z hujjatlarini ochadi.
class Store {
  static final _db = FirebaseFirestore.instance;

  static DocumentReference<Map<String, dynamic>> _user(String uid) => _db.collection('users').doc(uid);

  static CollectionReference<Map<String, dynamic>> _messages(String uid) => _user(uid).collection('messages');

  static Future<void> saveProfile(User user, String name, Map<String, bool> permissions) async {
    final ref = _user(user.uid);
    final exists = (await ref.get()).exists;
    await ref.set({
      'name': name,
      'email': user.email ?? '',
      'platform': Platform.isIOS ? 'ios' : 'android',
      'flavor': kFlavor,
      'permissions': permissions,
      'updatedAt': FieldValue.serverTimestamp(),
      if (!exists) 'createdAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  static Future<String?> profileName(String uid) async {
    final snap = await _user(uid).get();
    return snap.data()?['name'] as String?;
  }

  static Stream<List<Map<String, dynamic>>> messages(String uid) => _messages(uid)
      .orderBy('createdAt')
      .limitToLast(200)
      .snapshots()
      .map((s) => s.docs.map((d) => d.data()).toList());

  static Future<void> addMessage(String uid, String role, String content, {List<Map<String, dynamic>>? actions}) =>
      _messages(uid).add({
        'role': role,
        'content': content,
        if (actions != null && actions.isNotEmpty) 'actions': actions,
        'createdAt': FieldValue.serverTimestamp(),
      });

  /// Oxirgi xabarlar - serverga kontekst sifatida yuboriladi.
  static Future<List<Map<String, String>>> history(String uid, {int limit = 10}) async {
    final snap = await _messages(uid).orderBy('createdAt').limitToLast(limit).get();
    return snap.docs
        .map((d) => {'role': d.data()['role'] as String? ?? 'user', 'content': d.data()['content'] as String? ?? ''})
        .toList();
  }

  static Future<void> clearMessages(String uid) async {
    while (true) {
      final snap = await _messages(uid).limit(400).get();
      if (snap.docs.isEmpty) return;
      final batch = _db.batch();
      for (final d in snap.docs) {
        batch.delete(d.reference);
      }
      await batch.commit();
    }
  }

  /// Akkaunt va barcha ma'lumotni o'chiradi (App Store va Play Market talabi).
  static Future<void> deleteAccount(User user) async {
    await clearMessages(user.uid);
    await _user(user.uid).delete();
    await user.delete();
  }
}
