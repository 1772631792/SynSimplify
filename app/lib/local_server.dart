import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'models.dart';
import 'sync_engine.dart';

/// 手机端也有一个 HTTP 服务，电脑可以主动来推文件 / 拉文件。
/// 接口和电脑端 server.py 完全一致。
class LocalServer {
  LocalServer({
    required this.deviceName,
    required this.deviceId,
    required this.hue,
    required this.rootProvider,
    this.onPeerSeen,
  });

  final String deviceName;
  final String deviceId;
  final int hue;
  final String Function() rootProvider;
  final void Function(String ip, String device, String deviceId)? onPeerSeen;

  HttpServer? _server;
  int port = kServerPort;

  bool get running => _server != null;

  Future<bool> start() async {
    if (_server != null) return true;
    for (var candidate = kServerPort; candidate < kServerPort + 12; candidate++) {
      try {
        _server = await HttpServer.bind(InternetAddress.anyIPv4, candidate);
        port = candidate;
        break;
      } catch (_) {
        continue;
      }
    }
    if (_server == null) return false;
    _server!.listen(
      (req) {
        unawaited(_handle(req));
      },
      onError: (_) {},
      cancelOnError: false,
    );
    return true;
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  void _json(HttpResponse res, Map<String, Object?> data, [int code = 200]) {
    try {
      res.statusCode = code;
      res.headers.contentType = ContentType('application', 'json', charset: 'utf-8');
      res.write(jsonEncode(data));
      res.close();
    } catch (_) {
      try {
        res.close();
      } catch (_) {}
    }
  }

  Future<void> _handle(HttpRequest req) async {
    final res = req.response;
    try {
      final ip = req.connectionInfo?.remoteAddress.address ?? '';
      final device = Uri.decodeComponent(req.headers.value('X-Device') ?? '');
      final peerId = req.headers.value('X-Device-Id') ?? '';
      if (device.isNotEmpty || peerId.isNotEmpty) {
        onPeerSeen?.call(ip, device, peerId);
      }

      final path = req.uri.path;

      if (req.method == 'GET' && path == '/syn/ping') {
        _json(res, {
          'ok': true,
          'name': deviceName,
          't': DateTime.now().millisecondsSinceEpoch,
        });
        return;
      }

      if (req.method == 'GET' && path == '/syn/info') {
        final root = rootProvider();
        _json(res, {
          'ok': true,
          'name': deviceName,
          'id': deviceId,
          'hue': hue,
          'port': port,
          'root': root,
          'rootName': baseName(root),
          'ver': 1,
          'app': '1.0.1',
        });
        return;
      }

      if (req.method == 'GET' && path == '/syn/scan') {
        final hidden = ['1', 'true', 'yes'].contains(req.uri.queryParameters['hidden']);
        final result = await scanLocal(rootProvider(), includeHidden: hidden);
        _json(res, {
          'ok': true,
          'root': rootProvider(),
          'items': result.items
              .map((it) => [it.p, it.size, it.mtime, it.isDir ? 1 : 0])
              .toList(growable: false),
          'truncated': result.truncated,
        });
        return;
      }

      if (req.method == 'GET' && path == '/syn/get') {
        await _serveFile(res, req);
        return;
      }

      if (req.method == 'POST' && path == '/syn/put') {
        await _receiveFile(res, req);
        return;
      }

      if (req.method == 'POST' && path == '/syn/mkdir') {
        final rel = req.uri.queryParameters['rel'] ?? '';
        if (!isSafeRel(rel) || rel.isEmpty) {
          _json(res, {'ok': false, 'error': '非法路径'}, 400);
          return;
        }
        await Directory(joinPath(rootProvider(), rel)).create(recursive: true);
        _json(res, {'ok': true, 'rel': rel});
        return;
      }

      if (req.method == 'POST' && path == '/syn/del') {
        final rel = req.uri.queryParameters['rel'] ?? '';
        if (!isSafeRel(rel) || rel.isEmpty) {
          _json(res, {'ok': false, 'error': '非法路径'}, 400);
          return;
        }
        final target = joinPath(rootProvider(), rel);
        final type = await FileSystemEntity.type(target, followLinks: false);
        if (type == FileSystemEntityType.directory) {
          await Directory(target).delete(recursive: true);
        } else if (type != FileSystemEntityType.notFound) {
          await File(target).delete();
        }
        _json(res, {'ok': true});
        return;
      }

      _json(res, {'ok': false, 'error': 'not found'}, 404);
    } catch (e) {
      _json(res, {'ok': false, 'error': '$e'}, 500);
    }
  }

  Future<void> _serveFile(HttpResponse res, HttpRequest req) async {
    final rel = req.uri.queryParameters['rel'] ?? '';
    if (!isSafeRel(rel) || rel.isEmpty) {
      _json(res, {'ok': false, 'error': '非法路径'}, 400);
      return;
    }
    final file = File(joinPath(rootProvider(), rel));
    if (!await file.exists()) {
      _json(res, {'ok': false, 'error': 'file not found'}, 404);
      return;
    }
    final stat = await file.stat();
    res.statusCode = 200;
    res.headers.contentType = ContentType.binary;
    res.contentLength = stat.size;
    res.headers.set('X-Mtime', '${stat.modified.millisecondsSinceEpoch}');
    res.headers.set('X-Name', Uri.encodeComponent(baseName(rel)));
    await res.addStream(file.openRead());
    await res.close();
  }

  Future<void> _receiveFile(HttpResponse res, HttpRequest req) async {
    final rel = req.uri.queryParameters['rel'] ?? '';
    if (!isSafeRel(rel) || rel.isEmpty) {
      _json(res, {'ok': false, 'error': '非法路径'}, 400);
      return;
    }
    final target = joinPath(rootProvider(), rel);
    final file = File(target);
    await file.parent.create(recursive: true);
    if (await FileSystemEntity.isDirectory(target)) {
      await Directory(target).delete(recursive: true);
    }

    final tmp = File('$target.syn_part');
    final sink = tmp.openWrite();
    var received = 0;
    try {
      await for (final chunk in req) {
        sink.add(chunk);
        received += chunk.length;
      }
      await sink.flush();
      await sink.close();
      if (await file.exists()) await file.delete();
      await tmp.rename(target);
      final mtime = int.tryParse(req.uri.queryParameters['mtime'] ?? '');
      if (mtime != null && mtime > 0) {
        await file.setLastModified(DateTime.fromMillisecondsSinceEpoch(mtime));
      }
    } catch (e) {
      try {
        await sink.close();
      } catch (_) {}
      try {
        if (await tmp.exists()) await tmp.delete();
      } catch (_) {}
      _json(res, {'ok': false, 'error': '$e'}, 500);
      return;
    }

    _json(res, {'ok': true, 'rel': rel, 'bytes': received});
  }
}
