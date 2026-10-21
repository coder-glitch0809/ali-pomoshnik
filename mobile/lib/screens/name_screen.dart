import 'package:flutter/material.dart';

/// Birinchi ekran: Ali foydalanuvchining ismini so'raydi.
class NameScreen extends StatefulWidget {
  const NameScreen({super.key, required this.onDone});

  final ValueChanged<String> onDone;

  @override
  State<NameScreen> createState() => _NameScreenState();
}

class _NameScreenState extends State<NameScreen> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final name = _controller.text.trim();
    if (name.isNotEmpty) widget.onDone(name.length > 80 ? name.substring(0, 80) : name);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Spacer(),
              CircleAvatar(
                radius: 32,
                backgroundColor: theme.colorScheme.primaryContainer,
                child: Text('A', style: theme.textTheme.headlineMedium),
              ),
              const SizedBox(height: 24),
              Text('Assalomu alaykum!', style: theme.textTheme.headlineMedium),
              const SizedBox(height: 8),
              Text('Men Ali — shaxsiy yordamchingizman. Ismingiz nima?', style: theme.textTheme.bodyLarge),
              const SizedBox(height: 24),
              TextField(
                controller: _controller,
                autofocus: true,
                textCapitalization: TextCapitalization.words,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
                decoration: const InputDecoration(labelText: 'Ismingiz', border: OutlineInputBorder()),
              ),
              const Spacer(flex: 2),
              SizedBox(
                width: double.infinity,
                child: FilledButton(onPressed: _submit, child: const Text('Davom etish')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
