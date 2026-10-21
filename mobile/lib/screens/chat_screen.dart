import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../services/api.dart';
import '../services/device.dart';
import '../services/permissions.dart';
import '../services/store.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.user,
    required this.name,
    required this.onSignedOut,
    required this.onNameChanged,
  });

  final User user;
  final String name;
  final VoidCallback onSignedOut;
  final ValueChanged<String> onNameChanged;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _speech = SpeechToText();
  final _tts = FlutterTts();
  bool _sending = false;
  bool _listening = false;
  bool _speak = false;

  @override
  void initState() {
    super.initState();
    _syncProfile();
    SharedPreferences.getInstance().then((p) => setState(() => _speak = p.getBool('speak') ?? false));
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  Future<void> _syncProfile() async {
    try {
      await Store.saveProfile(widget.user, widget.name, await permissionStatuses());
    } catch (_) {
      // tarmoq yo'q - keyingi ochilishda saqlanadi
    }
  }

  Future<void> _send([String? override]) async {
    final text = (override ?? _input.text).trim();
    if (text.isEmpty || _sending) return;
    _input.clear();
    setState(() => _sending = true);
    final uid = widget.user.uid;
    try {
      final history = await Store.history(uid);
      await Store.addMessage(uid, 'user', text);
      final reply = await AliApi.ask(text, history, widget.name);
      await Store.addMessage(uid, 'assistant', reply.reply, actions: reply.actions);
      if (_speak) await _tts.speak(reply.reply);
      for (final action in reply.actions) {
        await _runAction(action);
      }
    } on AliApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Xato: $e');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _runAction(Map<String, dynamic> action) async {
    if (Device.needsConfirm(action)) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: const Text('Ruxsat berasizmi?'),
          content: Text('Ali buni bajarmoqchi: ${Device.describe(action)}'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Yo‘q')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Ha, bajar')),
          ],
        ),
      );
      if (ok != true) return;
    }
    final result = await Device.run(action);
    _toast('${Device.describe(action)} — $result');
  }

  Future<void> _toggleMic() async {
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }
    final ok = await _speech.initialize(onStatus: (s) {
      if ((s == 'done' || s == 'notListening') && mounted) setState(() => _listening = false);
    });
    if (!ok) {
      _toast('Mikrofonga ruxsat bering: Sozlamalar → Ruxsatlar');
      return;
    }
    setState(() => _listening = true);
    await _speech.listen(onResult: (r) {
      _input.text = r.recognizedWords;
      if (r.finalResult) _send(r.recognizedWords);
    });
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ali'),
        actions: [
          IconButton(
            tooltip: 'Sozlamalar',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => SettingsScreen(
                    user: widget.user,
                    name: widget.name,
                    onNameChanged: widget.onNameChanged,
                    onSignedOut: widget.onSignedOut,
                  ),
                ),
              );
              final p = await SharedPreferences.getInstance();
              setState(() => _speak = p.getBool('speak') ?? false);
              _syncProfile();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: StreamBuilder<List<Map<String, dynamic>>>(
              stream: Store.messages(widget.user.uid),
              builder: (context, snap) {
                final items = snap.data ?? const [];
                if (items.isEmpty) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(
                        '${widget.name}, nima yordam kerak?\nMasalan: “Telegramni och”, “Ertaga ob-havo qanday?”',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyLarge,
                      ),
                    ),
                  );
                }
                _scrollDown();
                return ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.all(12),
                  itemCount: items.length,
                  itemBuilder: (_, i) => _Bubble(items[i]),
                );
              },
            ),
          ),
          if (_sending) const LinearProgressIndicator(minHeight: 2),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
              child: Row(
                children: [
                  IconButton(
                    tooltip: _listening ? 'To‘xtatish' : 'Ovoz bilan',
                    icon: Icon(_listening ? Icons.stop_circle_outlined : Icons.mic_none),
                    color: _listening ? theme.colorScheme.error : null,
                    onPressed: _toggleMic,
                  ),
                  Expanded(
                    child: TextField(
                      controller: _input,
                      minLines: 1,
                      maxLines: 5,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      decoration: const InputDecoration(
                        hintText: 'Xabar yozing...',
                        border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(24))),
                        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Yuborish',
                    icon: const Icon(Icons.send),
                    onPressed: _sending ? null : _send,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.message);

  final Map<String, dynamic> message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mine = message['role'] == 'user';
    final actions = (message['actions'] as List? ?? []).whereType<Map>().toList();
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: mine ? theme.colorScheme.primaryContainer : theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(message['content'] as String? ?? ''),
            for (final a in actions)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('▸ ${Device.describe(Map<String, dynamic>.from(a))}', style: theme.textTheme.bodySmall),
              ),
          ],
        ),
      ),
    );
  }
}
