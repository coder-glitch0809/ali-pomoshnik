import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';
import '../services/store.dart';
import 'permissions_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.user,
    required this.name,
    required this.onNameChanged,
    required this.onSignedOut,
  });

  final User user;
  final String name;
  final ValueChanged<String> onNameChanged;
  final VoidCallback onSignedOut;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _speak = false;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) => setState(() => _speak = p.getBool('speak') ?? false));
  }

  Future<void> _rename() async {
    final controller = TextEditingController(text: widget.name);
    final value = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Ismingiz'),
        content: TextField(controller: controller, autofocus: true, textCapitalization: TextCapitalization.words),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('Bekor')),
          FilledButton(onPressed: () => Navigator.pop(c, controller.text.trim()), child: const Text('Saqlash')),
        ],
      ),
    );
    if (value != null && value.isNotEmpty) {
      widget.onNameChanged(value);
      if (mounted) Navigator.pop(context);
    }
  }

  Future<bool> _confirm(String title, String text, String yes) async =>
      await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text(title),
          content: Text(text),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Bekor')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(yes)),
          ],
        ),
      ) ??
      false;

  Future<void> _clear() async {
    if (!await _confirm('Suhbatni tozalash', 'Barcha xabarlar o‘chiriladi.', 'Tozalash')) return;
    await Store.clearMessages(widget.user.uid);
    _toast('Suhbat tozalandi');
  }

  Future<void> _delete() async {
    if (!await _confirm('Akkauntni o‘chirish',
        'Akkaunt, profil va barcha suhbatlar butunlay o‘chiriladi. Bu amalni qaytarib bo‘lmaydi.', 'O‘chirish')) {
      return;
    }
    try {
      await Store.deleteAccount(widget.user);
      await (await SharedPreferences.getInstance()).clear();
      if (mounted) Navigator.popUntil(context, (r) => r.isFirst);
      widget.onSignedOut();
    } on FirebaseAuthException catch (e) {
      _toast(e.code == 'requires-recent-login'
          ? 'Xavfsizlik uchun chiqib, qayta kiring va yana urinib ko‘ring'
          : 'O‘chirib bo‘lmadi: ${e.code}');
    }
  }

  Future<void> _signOut() async {
    await FirebaseAuth.instance.signOut();
    if (mounted) Navigator.popUntil(context, (r) => r.isFirst);
    widget.onSignedOut();
  }

  void _toast(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final danger = Theme.of(context).colorScheme.error;
    return Scaffold(
      appBar: AppBar(title: const Text('Sozlamalar')),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.person_outline),
            title: Text(widget.name),
            subtitle: Text(widget.user.email ?? ''),
            trailing: const Icon(Icons.edit_outlined),
            onTap: _rename,
          ),
          ListTile(
            leading: const Icon(Icons.verified_user_outlined),
            title: const Text('Ruxsatlar'),
            subtitle: const Text('Mikrofon, kamera, joylashuv va boshqalar'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => PermissionsScreen(name: widget.name)),
            ),
          ),
          SwitchListTile(
            secondary: const Icon(Icons.volume_up_outlined),
            title: const Text('Javobni ovoz bilan o‘qish'),
            value: _speak,
            onChanged: (v) async {
              await (await SharedPreferences.getInstance()).setBool('speak', v);
              setState(() => _speak = v);
            },
          ),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('Versiya'),
            subtitle: Text(isFullFlavor ? 'To‘liq (APK)' : 'Do‘kon versiyasi'),
          ),
          ListTile(
            leading: const Icon(Icons.privacy_tip_outlined),
            title: const Text('Maxfiylik siyosati'),
            onTap: () => launchUrl(Uri.parse(kPrivacyUrl), mode: LaunchMode.externalApplication),
          ),
          const Divider(),
          ListTile(leading: const Icon(Icons.delete_sweep_outlined), title: const Text('Suhbatni tozalash'), onTap: _clear),
          ListTile(leading: const Icon(Icons.logout), title: const Text('Chiqish'), onTap: _signOut),
          ListTile(
            leading: Icon(Icons.delete_forever_outlined, color: danger),
            title: Text('Akkauntni o‘chirish', style: TextStyle(color: danger)),
            onTap: _delete,
          ),
        ],
      ),
    );
  }
}
