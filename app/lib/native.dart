import 'dart:io';

import 'package:flutter/services.dart';

/// 和 Android 原生打的一点交道：文件权限、选文件夹、常亮。
class Native {
  static const _channel = MethodChannel('synsimplify/native');

  static bool get isAndroid => Platform.isAndroid;

  static Future<Map<String, String>> paths() async {
    if (!isAndroid) return {};
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>('paths');
      if (raw == null) return {};
      return raw.map((k, v) => MapEntry(k, (v ?? '').toString()));
    } catch (_) {
      return {};
    }
  }

  static Future<bool> isAllFiles() async {
    if (!isAndroid) return true;
    try {
      return await _channel.invokeMethod<bool>('isAllFiles') ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> requestAllFiles() async {
    if (!isAndroid) return;
    try {
      await _channel.invokeMethod('requestAllFiles');
    } catch (_) {}
  }

  static Future<String?> pickFolder() async {
    if (!isAndroid) return null;
    try {
      return await _channel.invokeMethod<String>('pickFolder');
    } catch (_) {
      return null;
    }
  }

  static Future<void> keepAwake(bool on) async {
    if (!isAndroid) return;
    try {
      await _channel.invokeMethod('keepAwake', {'on': on});
    } catch (_) {}
  }
}
