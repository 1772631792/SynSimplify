import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'models.dart';

class PeerError implements Exception {
  PeerError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// UDP 广播发现：手机广播 DISCOVER，电脑回 HOST。
///
/// 同一个 WiFi 里只有一台电脑时，App 半秒内就能连上；
/// 有多台就交给界面让用户点一个。
class DiscoveryService {
  RawDatagramSocket? _socket;
  StreamSubscription<RawSocketEvent>? _sub;
  Timer? _timer;
  List<InternetAddress> _targets = const [];

  final Map<String, PeerInfo> hosts = {};

  void Function(PeerInfo host)? onHost;
  void Function()? onTick;
  Map<String, Object?> Function()? payloadBuilder;

  int intervalMs = 700;
  bool running = false;

  Future<bool> start() async {
    if (running) return true;
    try {
      final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      socket.broadcastEnabled = true;
      _socket = socket;
      _sub = socket.listen(
        (event) {
          if (event != RawSocketEvent.read) return;
          final dg = socket.receive();
          if (dg != null) _onPacket(dg);
        },
        onError: (_) {},
      );
      _targets = await _broadcasts();
      running = true;
      _announce();
      _timer = Timer.periodic(Duration(milliseconds: intervalMs), (_) => _announce());
      return true;
    } catch (_) {
      running = false;
      return false;
    }
  }

  void setInterval(int ms) {
    if (intervalMs == ms) return;
    intervalMs = ms;
    if (!running) return;
    _timer?.cancel();
    _timer = Timer.periodic(Duration(milliseconds: ms), (_) => _announce());
  }

  Future<List<InternetAddress>> _broadcasts() async {
    final set = <String>{'255.255.255.255'};
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
      );
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          final parts = addr.address.split('.');
          if (parts.length == 4) {
            set.add('${parts[0]}.${parts[1]}.${parts[2]}.255');
          }
        }
      }
    } catch (_) {}
    return set.map(InternetAddress.new).toList();
  }

  void _announce() {
    final socket = _socket;
    final builder = payloadBuilder;
    if (socket == null || builder == null) return;
    final body = '$kDiscoverPayload ${jsonEncode(builder())}';
    final bytes = utf8.encode(body);
    for (final target in _targets) {
      try {
        socket.send(bytes, target, kDiscoveryPort);
      } catch (_) {
        // 某个网卡不让广播就跳过，换下一个
      }
    }
  }

  void _onPacket(Datagram dg) {
    final text = utf8.decode(dg.data, allowMalformed: true).trim();
    if (!text.startsWith(kHostPayload)) return;
    Map<String, dynamic> map;
    try {
      final raw = text.substring(kHostPayload.length).trim();
      map = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    final id = (map['id'] ?? dg.address.address).toString();
    final info = PeerInfo(
      id: id,
      name: (map['name'] ?? '电脑').toString(),
      ip: dg.address.address,
      port: (map['port'] as num?)?.toInt() ?? kPeerDefaultPort,
      root: (map['root'] ?? '').toString(),
      hue: (map['hue'] as num?)?.toInt() ?? 220,
      busy: map['busy'] == true,
      lastSeen: DateTime.now().millisecondsSinceEpoch,
    );
    hosts[id] = info;
    onHost?.call(info);
  }

  Future<void> stop() async {
    running = false;
    _timer?.cancel();
    _timer = null;
    await _sub?.cancel();
    _sub = null;
    _socket?.close();
    _socket = null;
  }
}

/// 访问电脑端 /syn/* 接口。
class PeerApi {
  PeerApi({
    required this.ip,
    required this.port,
    this.deviceName = '我的手机',
    this.deviceId = '',
  });

  final String ip;
  final int port;
  String deviceName;
  String deviceId;

  final HttpClient _http = HttpClient()
    ..connectionTimeout = const Duration(seconds: 6)
    ..idleTimeout = const Duration(seconds: 20)
    ..autoUncompress = true;

  void close() {
    _http.close(force: true);
  }

  Uri _uri(String path, [Map<String, String>? query]) => Uri(
        scheme: 'http',
        host: ip,
        port: port,
        path: path,
        queryParameters: query,
      );

  Map<String, String> get _headers => {
        'X-Device': Uri.encodeComponent(deviceName),
        'X-Device-Id': deviceId,
      };

  Future<Map<String, dynamic>> _getJson(Uri uri,
      {Duration timeout = const Duration(seconds: 8)}) async {
    try {
      final req = await _http.getUrl(uri).timeout(timeout);
      _headers.forEach(req.headers.set);
      final resp = await req.close().timeout(timeout);
      final body = await resp.transform(utf8.decoder).join().timeout(timeout);
      if (resp.statusCode >= 400) {
        throw PeerError('电脑返回 ${resp.statusCode}');
      }
      final map = jsonDecode(body);
      if (map is! Map<String, dynamic>) throw PeerError('电脑返回格式不对');
      return map;
    } on PeerError {
      rethrow;
    } on TimeoutException {
      throw PeerError('连接超时');
    } on SocketException catch (e) {
      throw PeerError('连不上电脑：${e.message}');
    } on FormatException {
      throw PeerError('电脑返回的不是 JSON');
    }
  }

  Future<Map<String, dynamic>> ping() => _getJson(_uri('/syn/ping'),
      timeout: const Duration(seconds: 3));

  Future<Map<String, dynamic>> info() => _getJson(_uri('/syn/info'));

  Future<ScanResult> scan({bool hidden = false}) async {
    final data = await _getJson(
      _uri('/syn/scan', hidden ? {'hidden': '1'} : null),
      timeout: const Duration(seconds: 25),
    );
    final list = data['items'];
    if (list is! List) return const ScanResult([]);
    return ScanResult(
      list
          .whereType<List>()
          .map((raw) => ManifestItem.fromList(raw))
          .toList(growable: false),
      truncated: data['truncated'] == true,
    );
  }

  Future<void> mkdir(String rel) async {
    final req = await _http.postUrl(_uri('/syn/mkdir', {'rel': rel}));
    _headers.forEach(req.headers.set);
    req.contentLength = 0;
    final resp = await req.close();
    await resp.drain<void>();
    if (resp.statusCode >= 400) throw PeerError('建目录失败 ${resp.statusCode}');
  }

  Future<void> delete(String rel) async {
    final req = await _http.postUrl(_uri('/syn/del', {'rel': rel}));
    _headers.forEach(req.headers.set);
    req.contentLength = 0;
    final resp = await req.close();
    await resp.drain<void>();
    if (resp.statusCode >= 400) throw PeerError('删除失败 ${resp.statusCode}');
  }

  Future<int> downloadFile(
    String rel,
    File dest, {
    void Function(int done, int total)? onProgress,
  }) async {
    await dest.parent.create(recursive: true);
    final tmp = File('${dest.path}.syn_part');
    final sink = tmp.openWrite();
    var written = 0;
    try {
      final req = await _http.getUrl(_uri('/syn/get', {'rel': rel}));
      _headers.forEach(req.headers.set);
      final resp = await req.close();
      if (resp.statusCode != 200) {
        await sink.close();
        throw PeerError('下载失败 ${resp.statusCode}');
      }
      final total = resp.contentLength > 0 ? resp.contentLength : 0;
      final mtime = int.tryParse(resp.headers.value('X-Mtime') ?? '') ?? 0;

      await for (final chunk in resp) {
        sink.add(chunk);
        written += chunk.length;
        onProgress?.call(written, total);
      }
      await sink.flush();
      await sink.close();

      if (await dest.exists()) await dest.delete();
      await tmp.rename(dest.path);
      if (mtime > 0) {
        await dest.setLastModified(DateTime.fromMillisecondsSinceEpoch(mtime));
      }
      return written;
    } catch (_) {
      try {
        await sink.close();
      } catch (_) {}
      try {
        if (await tmp.exists()) await tmp.delete();
      } catch (_) {}
      rethrow;
    }
  }

  Future<int> uploadFile(
    String rel,
    File src, {
    required int mtime,
    void Function(int done, int total)? onProgress,
  }) async {
    final length = await src.length();
    final req = await _http.postUrl(
      _uri('/syn/put', {'rel': rel, 'mtime': '$mtime'}),
    );
    _headers.forEach(req.headers.set);
    req.headers.contentType = ContentType.binary;
    req.contentLength = length;

    var sent = 0;
    var lastReport = 0;
    final stream = src.openRead().transform<List<int>>(
      StreamTransformer.fromHandlers(
        handleData: (data, sink) {
          final now = DateTime.now().millisecondsSinceEpoch;
          sent += data.length;
          if (now - lastReport > 90 || sent >= length) {
            lastReport = now;
            onProgress?.call(sent, length);
          }
          sink.add(data);
        },
      ),
    );

    await req.addStream(stream);
    final resp = await req.close();
    final body = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      throw PeerError('上传失败 ${resp.statusCode} ${body.substring(0, math.min(60, body.length))}');
    }
    return sent;
  }
}
