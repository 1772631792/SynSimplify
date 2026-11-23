import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_state.dart';
import 'pages/home_page.dart';
import 'pages/log_page.dart';
import 'pages/settings_page.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      statusBarBrightness: Brightness.dark,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  final app = AppState();
  await app.boot();
  runApp(SynSimplifyApp(app: app));
}

class SynSimplifyApp extends StatelessWidget {
  const SynSimplifyApp({super.key, required this.app});

  final AppState app;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SynSimplify',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: Shell(app: app),
    );
  }
}

class Shell extends StatefulWidget {
  const Shell({super.key, required this.app});

  final AppState app;

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _tab = 0;

  AppState get app => widget.app;

  void _go(int index) => setState(() => _tab = index);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      backgroundColor: Palette.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: kBgGradient),
        child: Stack(
          children: [
            const Positioned(top: -150, left: -100, child: _Glow(color: Palette.accent, size: 340)),
            const Positioned(top: 120, right: -130, child: _Glow(color: Palette.accent2, size: 360)),
            IndexedStack(
              index: _tab,
              children: [
                HomePage(app: app, onOpenLog: () => _go(1)),
                LogPage(app: app),
                SettingsPage(app: app),
              ],
            ),
          ],
        ),
      ),
      bottomNavigationBar: AnimatedBuilder(
        animation: app,
        builder: (context, _) => _NavBar(
          index: _tab,
          onTap: _go,
          connected: app.connected,
          badge: app.running ? '•' : null,
        ),
      ),
    );
  }
}

class _Glow extends StatelessWidget {
  const _Glow({required this.color, required this.size});

  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color.withValues(alpha: 0.15), color.withValues(alpha: 0.0)],
          ),
        ),
      ),
    );
  }
}

class _NavBar extends StatelessWidget {
  const _NavBar({
    required this.index,
    required this.onTap,
    required this.connected,
    this.badge,
  });

  final int index;
  final ValueChanged<int> onTap;
  final bool connected;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(16, 20, 16, bottom > 0 ? bottom : 14),
      decoration: BoxDecoration(
        // 让内容在导航栏附近自然淡出，避免文字从胶囊边缘漏出来
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Palette.bg.withValues(alpha: 0.0),
            Palette.bg.withValues(alpha: 0.80),
            Palette.bg,
          ],
          stops: const [0.0, 0.42, 1.0],
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(26),
        child: BackdropFilter(
          filter: ui.ImageFilter.blur(sigmaX: 22, sigmaY: 22),
          child: Container(
            height: 66,
            decoration: BoxDecoration(
              color: const Color(0xFF0A111C).withValues(alpha: 0.88),
              borderRadius: BorderRadius.circular(26),
              border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
            ),
            child: Row(
              children: [
                _NavItem(
                  label: '同步',
                  icon: Icons.sync_rounded,
                  selected: index == 0,
                  dot: connected ? Palette.ok : Palette.warn,
                  badge: badge,
                  onTap: () => onTap(0),
                  highlight: true,
                ),
                _NavItem(
                  label: '记录',
                  icon: Icons.receipt_long_rounded,
                  selected: index == 1,
                  onTap: () => onTap(1),
                ),
                _NavItem(
                  label: '设置',
                  icon: Icons.settings_rounded,
                  selected: index == 2,
                  onTap: () => onTap(2),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    this.dot,
    this.badge,
    this.highlight = false,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final Color? dot;
  final String? badge;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final color = selected ? Palette.text : Palette.textDim;
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Stack(
          alignment: Alignment.center,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              height: 44,
              margin: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                gradient: selected
                    ? LinearGradient(
                        colors: highlight
                            ? [
                                Palette.accent.withValues(alpha: 0.24),
                                Palette.accent2.withValues(alpha: 0.2),
                              ]
                            : [
                                Colors.white.withValues(alpha: 0.08),
                                Colors.white.withValues(alpha: 0.04),
                              ],
                      )
                    : null,
                borderRadius: BorderRadius.circular(16),
                border: selected
                    ? Border.all(color: Colors.white.withValues(alpha: 0.08))
                    : null,
              ),
            ),
            Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Icon(icon, size: 21, color: highlight && selected ? Palette.accent : color),
                    if (dot != null)
                      Positioned(
                        right: -4,
                        top: -2,
                        child: Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: dot,
                            border: Border.all(color: Palette.bg, width: 1),
                          ),
                        ),
                      ),
                    if (badge != null)
                      Positioned(
                        right: -5,
                        top: -3,
                        child: Container(
                          width: 7,
                          height: 7,
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            color: Palette.accent,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  label,
                  style: TextStyle(
                    color: color,
                    fontSize: 10.5,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
