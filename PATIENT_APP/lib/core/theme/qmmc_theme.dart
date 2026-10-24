import 'package:flutter/material.dart';

/// Palette estimated from the QMMC website (qmmc.doh.gov.ph).
/// Replace with official brand hex codes if the client provides them.
class QmmcColors {
  QmmcColors._();

  static const Color deepGreen = Color(0xFF0F4C3A);
  static const Color mint = Color(0xFFE8F3EC);
  static const Color sage = Color(0xFFBDDCCE);
  static const Color success = Color(0xFF2E7D4F);
  static const Color gold = Color(0xFFF2B632);
  static const Color danger = Color(0xFFC62828);
  static const Color ink = Color(0xFF12261F);
  static const Color muted = Color(0xFF5E7A6F);
}

ThemeData buildQmmcTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: QmmcColors.deepGreen,
    brightness: Brightness.light,
  ).copyWith(
    primary: QmmcColors.deepGreen,
    onPrimary: Colors.white,
    secondary: QmmcColors.success,
    onSecondary: Colors.white,
    error: QmmcColors.danger,
    surface: Colors.white,
    onSurface: QmmcColors.ink,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: QmmcColors.mint,
    appBarTheme: const AppBarTheme(
      backgroundColor: QmmcColors.deepGreen,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: QmmcColors.deepGreen,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: QmmcColors.deepGreen,
        minimumSize: const Size.fromHeight(52),
        side: const BorderSide(color: QmmcColors.deepGreen, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: QmmcColors.sage),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: QmmcColors.deepGreen, width: 2),
      ),
    ),
  );
}
