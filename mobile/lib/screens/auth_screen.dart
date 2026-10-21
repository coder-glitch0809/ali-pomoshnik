import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';

/// Email va parol bilan kirish / ro'yxatdan o'tish (Firebase Auth).
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.name});

  final String name;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = FirebaseAuth.instance;
    try {
      if (_register) {
        final cred = await auth.createUserWithEmailAndPassword(email: _email.text.trim(), password: _password.text);
        await cred.user?.updateDisplayName(widget.name);
      } else {
        await auth.signInWithEmailAndPassword(email: _email.text.trim(), password: _password.text);
      }
    } on FirebaseAuthException catch (e) {
      setState(() => _error = _message(e.code));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reset() async {
    final email = _email.text.trim();
    if (email.isEmpty) {
      setState(() => _error = 'Avval emailingizni kiriting');
      return;
    }
    try {
      await FirebaseAuth.instance.sendPasswordResetEmail(email: email);
      setState(() => _error = 'Parolni tiklash havolasi emailingizga yuborildi');
    } on FirebaseAuthException catch (e) {
      setState(() => _error = _message(e.code));
    }
  }

  String _message(String code) => switch (code) {
        'invalid-email' => 'Email noto‘g‘ri',
        'email-already-in-use' => 'Bu email bilan akkaunt bor. “Kirish”ni tanlang',
        'weak-password' => 'Parol kamida 6 belgi bo‘lsin',
        'user-not-found' || 'wrong-password' || 'invalid-credential' => 'Email yoki parol noto‘g‘ri',
        'network-request-failed' => 'Internet yo‘q',
        'too-many-requests' => 'Juda ko‘p urinish. Birozdan so‘ng qayta urinib ko‘ring',
        _ => 'Xato: $code',
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 32),
            Text(_register ? 'Akkaunt yaratish' : 'Kirish', style: theme.textTheme.headlineMedium),
            const SizedBox(height: 8),
            Text('${widget.name}, suhbatlaringiz akkauntingizda saqlanadi va faqat sizga ko‘rinadi.',
                style: theme.textTheme.bodyLarge),
            const SizedBox(height: 24),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _password,
              obscureText: true,
              autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
              onSubmitted: (_) => _submit(),
              decoration: const InputDecoration(labelText: 'Parol', border: OutlineInputBorder()),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
            ],
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: _busy
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(_register ? 'Ro‘yxatdan o‘tish' : 'Kirish'),
            ),
            TextButton(
              onPressed: () => setState(() => _register = !_register),
              child: Text(_register ? 'Akkauntim bor — kirish' : 'Yangi akkaunt yaratish'),
            ),
            if (!_register) TextButton(onPressed: _reset, child: const Text('Parolni unutdim')),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => launchUrl(Uri.parse(kPrivacyUrl), mode: LaunchMode.externalApplication),
              child: const Text('Maxfiylik siyosati'),
            ),
          ],
        ),
      ),
    );
  }
}
