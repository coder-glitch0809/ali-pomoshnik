import 'package:flutter/material.dart';

import '../services/permissions.dart';

/// Har bir ruxsatni alohida, nima uchun kerakligi bilan so'raydi. Rad etish mumkin - ilova ishlayveradi.
class PermissionsScreen extends StatefulWidget {
  const PermissionsScreen({super.key, required this.name, this.onboarding = false, this.onDone});

  final String name;
  final bool onboarding;
  final VoidCallback? onDone;

  @override
  State<PermissionsScreen> createState() => _PermissionsScreenState();
}

class _PermissionsScreenState extends State<PermissionsScreen> with WidgetsBindingObserver {
  final _items = appPermissions();
  final Map<String, bool> _granted = {};
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // Tizim sozlamalaridan qaytganda holatni yangilaymiz
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    for (final p in _items) {
      _granted[p.key] = await p.isGranted();
    }
    if (mounted) setState(() {});
  }

  Future<void> _ask(AppPermission p) async {
    setState(() => _busy = true);
    await p.request();
    await _refresh();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _askAll() async {
    setState(() => _busy = true);
    for (final p in _items) {
      if (!(_granted[p.key] ?? false) && !p.accessibility) await p.request();
    }
    await _refresh();
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final all = _items.every((p) => _granted[p.key] ?? false);
    return Scaffold(
      appBar: AppBar(title: const Text('Ruxsatlar'), automaticallyImplyLeading: !widget.onboarding),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          Text(
            '${widget.name}, Ali sizga yordam berishi uchun quyidagi ruxsatlar kerak. Har birini alohida '
            'tanlaysiz va keyin Sozlamalardan o‘zgartirishingiz mumkin.',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 16),
          for (final p in _items)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: Icon(p.icon),
                title: Text(p.title),
                subtitle: Text(p.why),
                isThreeLine: true,
                trailing: (_granted[p.key] ?? false)
                    ? Icon(Icons.check_circle, color: theme.colorScheme.primary, semanticLabel: 'Ruxsat berilgan')
                    : TextButton(onPressed: _busy ? null : () => _ask(p), child: const Text('Ruxsat')),
              ),
            ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: Row(
            children: [
              if (widget.onboarding)
                TextButton(onPressed: widget.onDone, child: const Text('Keyinroq')),
              const Spacer(),
              if (!all)
                FilledButton(onPressed: _busy ? null : _askAll, child: const Text('Hammasiga ruxsat berish'))
              else if (widget.onboarding)
                FilledButton(onPressed: widget.onDone, child: const Text('Davom etish')),
            ],
          ),
        ),
      ),
    );
  }
}
