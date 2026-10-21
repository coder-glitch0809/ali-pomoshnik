import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'firebase_options.dart';
import 'screens/auth_screen.dart';
import 'screens/chat_screen.dart';
import 'screens/name_screen.dart';
import 'screens/permissions_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const AliApp());
}

class AliApp extends StatelessWidget {
  const AliApp({super.key});

  static const seed = Color(0xFF5B7CFA);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ali',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: seed, useMaterial3: true),
      darkTheme: ThemeData(
        colorSchemeSeed: seed,
        brightness: Brightness.dark,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0B0F17),
      ),
      home: const Gate(),
    );
  }
}

/// Birinchi ochilishda: ism -> ruxsatlar -> kirish. Keyin to'g'ridan-to'g'ri suhbat.
class Gate extends StatefulWidget {
  const Gate({super.key});

  @override
  State<Gate> createState() => _GateState();
}

class _GateState extends State<Gate> {
  SharedPreferences? _prefs;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) => setState(() => _prefs = p));
  }

  @override
  Widget build(BuildContext context) {
    final prefs = _prefs;
    if (prefs == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final name = prefs.getString('name');
    if (name == null || name.isEmpty) {
      return NameScreen(onDone: (value) async {
        await prefs.setString('name', value);
        setState(() {});
      });
    }
    if (!(prefs.getBool('permissions_done') ?? false)) {
      return PermissionsScreen(
        name: name,
        onboarding: true,
        onDone: () async {
          await prefs.setBool('permissions_done', true);
          setState(() {});
        },
      );
    }
    return StreamBuilder<User?>(
      stream: FirebaseAuth.instance.authStateChanges(),
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        final user = snap.data;
        if (user == null) return AuthScreen(name: name);
        return ChatScreen(
          user: user,
          name: name,
          onSignedOut: () => setState(() {}),
          onNameChanged: (value) async {
            await prefs.setString('name', value);
            setState(() {});
          },
        );
      },
    );
  }
}
