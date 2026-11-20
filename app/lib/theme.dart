import 'package:flutter/material.dart';

import 'models.dart';

/// 深色玻璃底 + 蓝紫渐变，和电脑端保持同一套色。
class Palette {
  const Palette._();

  static const bg = Color(0xFF05080F);
  static const bgTop = Color(0xFF0B1320);
  static const card = Color(0xFF101A28);
  static const cardSoft = Color(0xFF0C1421);
  static const stroke = Color(0x1FFFFFFF);
  static const text = Color(0xFFF2F7FF);
  static const textDim = Color(0xFF8A98AC);
  static const textMuted = Color(0xFF5C6A7E);

  static const accent = Color(0xFF4F8CFF);
  static const accent2 = Color(0xFF9B6BFF);
  static const mint = Color(0xFF2FD8A0);
  static const cyan = Color(0xFF22D3EE);
  static const pink = Color(0xFFFF6FAE);

  static const ok = Color(0xFF35D07F);
  static const warn = Color(0xFFFFB020);
  static const err = Color(0xFFFF5F6D);

  static const grad = LinearGradient(
    colors: [accent, accent2],
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
  );

  static const pushGrad = LinearGradient(
    colors: [Color(0xFF4F8CFF), Color(0xFF9B6BFF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const pullGrad = LinearGradient(
    colors: [Color(0xFF2FD8A0), Color(0xFF22D3EE)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const twoGrad = LinearGradient(
    colors: [Color(0xFFFF6FAE), Color(0xFF9B6BFF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const cardGrad = LinearGradient(
    colors: [Color(0xFF131D2C), Color(0xFF0B1320)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static LinearGradient gradOf(Direction d) => switch (d) {
        Direction.push => pushGrad,
        Direction.pull => pullGrad,
        Direction.two => twoGrad,
      };

  static Color colorOf(Direction d) => switch (d) {
        Direction.push => accent,
        Direction.pull => mint,
        Direction.two => pink,
      };
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: Palette.accent,
    brightness: Brightness.dark,
  ).copyWith(
    primary: Palette.accent,
    secondary: Palette.accent2,
    surface: Palette.card,
    onSurface: Palette.text,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: Palette.bg,
    canvasColor: Palette.bg,
    splashFactory: InkSparkle.splashFactory,
    snackBarTheme: SnackBarThemeData(
      backgroundColor: const Color(0xFF182133),
      contentTextStyle: const TextStyle(color: Palette.text, fontSize: 14),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Palette.card,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? Colors.white : const Color(0xFF8493A8),
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? Palette.accent : const Color(0xFF243044),
      ),
      trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
    ),
    textSelectionTheme: const TextSelectionThemeData(
      cursorColor: Palette.accent,
      selectionColor: Color(0x554F8CFF),
      selectionHandleColor: Palette.accent,
    ),
  );
}

const kBgGradient = LinearGradient(
  colors: [Palette.bgTop, Palette.bg, Color(0xFF03060B)],
  begin: Alignment.topCenter,
  end: Alignment.bottomCenter,
  stops: [0.0, 0.45, 1.0],
);
