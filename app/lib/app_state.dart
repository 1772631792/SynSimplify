import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'local_server.dart';
import 'models.dart';
import 'native.dart';
import 'net_client.dart';
import 'sync_engine.dart';

enum LinkState { scanning, choosing, connected, offline }

class AppSettings {
  String deviceName = '我的手机';
  String localRoot = '';
  Direction direction = Direction.push;
  bool includeHidden = false;
  bool mirrorDelete = false;
  String peerId = '';
  String manualHost = '';
  String deviceId = '';
  bool p2pMode = false; // 手机互传：只连另一台手机
}

class AppState extends ChangeNotifier {
  AppState();

  final AppSettings settings = AppSettings();
  final DiscoveryService discovery = DiscoveryService();

  LocalServer? _server;
  PeerApi? _api;
  SyncEngine? _engine;
  SharedPreferences? _prefs;

  LinkState link = LinkState.scanning;
  PeerInfo? peer;
  final Map<String, PeerInfo> candidates = {};
  int latency = 0;
  String notice = '';
  bool allFiles = true;
  bool serverReady = false;

  bool running = false;
  bool dryRun = false;
  String phase = '';
  String currentFile = '';
  List<SyncOp> ops = [];
  SyncStats stats = SyncStats();
  int totalBytes = 0;
  int doneBytes = 0;
  int liveBytes = 0;
  int finishedAt = 0;
  bool stopped = false;

  Timer? _heartbeat;
  Timer? _settleTimer;
  DateTime? _scanStartedAt;
  bool _settled = false;
  bool _adopting = false;
  bool _manual = false;
  int _fails = 0;

  String _defaultRoot = '/storage/emulated/0/SynSimplify';
  String _appRoot = '';

  bool get connected => link == LinkState.connected && peer != null;

  List<PeerInfo> get peerList {
    final list = candidates.values.toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
    return list;
  }

  String get remoteRoot => peer?.root ?? '';

  String get localRoot => settings.localRoot;

  int get hue {
    final id = settings.deviceId.isEmpty ? 'phone' : settings.deviceId;
    var total = 0;
    for (var i = 0; i < id.length; i++) {
      total += id.codeUnitAt(i) * (i + 7);
    }
    return total % 360;
  }

  double get progress {
    if (totalBytes <= 0) {
      return running ? 0 : (finishedAt > 0 ? 1 : 0);
    }
    return ((doneBytes + liveBytes) / totalBytes).clamp(0.0, 1.0);
  }

  int get movedFiles => ops.where((o) => o.kind.movesFile && o.status == OpStatus.done).length;

  int get pendingFiles =>
      ops.where((o) => o.kind.movesFile && o.status != OpStatus.done).length;

  // ------------------------------------------------------------- 启动
  Future<void> boot() async {
    _prefs = await SharedPreferences.getInstance();
    settings
      ..deviceName = _prefs!.getString('deviceName') ?? '我的手机'
      ..localRoot = _prefs!.getString('localRoot') ?? ''
      ..direction = DirectionX.fromWire(_prefs!.getString('direction') ?? 'push')
      ..includeHidden = _prefs!.getBool('includeHidden') ?? false
      ..mirrorDelete = _prefs!.getBool('mirrorDelete') ?? false
      ..peerId = _prefs!.getString('peerId') ?? ''
      ..manualHost = _prefs!.getString('manualHost') ?? ''
      ..deviceId = _prefs!.getString('deviceId') ?? ''
      ..p2pMode = _prefs!.getBool('p2pMode') ?? false;

    if (settings.deviceId.isEmpty) {
      settings.deviceId =
          '${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}${math.Random().nextInt(46656).toRadixString(16)}';
      await _prefs!.setString('deviceId', settings.deviceId);
    }

    final paths = await Native.paths();
    _defaultRoot = (paths['root'] ?? '/storage/emulated/0').trim();
    _appRoot = (paths['app'] ?? '').trim();
    allFiles = await Native.isAllFiles();

    if (settings.localRoot.isEmpty) {
      settings.localRoot = _pickDefaultRoot();
    }
    await _ensureLocalRoot();

    _server = LocalServer(
      deviceName: settings.deviceName,
      deviceId: settings.deviceId,
      hue: hue,
      rootProvider: () => settings.localRoot,
      p2pProvider: () => settings.p2pMode,
      onPeerSeen: (ip, device, id) {
        if (device.isNotEmpty && notice.isEmpty) {
          notice = '$device 正在连接这台手机';
          notifyListeners();
        }
      },
    );
    serverReady = await _server!.start();
    if (!serverReady) {
      notice = '手机端服务端口被占用，对方无法主动取文件';
    }
    notifyListeners();
    await startDiscovery();
  }

  String _pickDefaultRoot() {
    final base = _defaultRoot.endsWith('/')
        ? _defaultRoot.substring(0, _defaultRoot.length - 1)
        : _defaultRoot;
    if (allFiles) return '$base/SynSimplify';
    return _appRoot.isEmpty ? '$base/Android/data' : _appRoot;
  }

  Future<void> _ensureLocalRoot() async {
    try {
      await Directory(settings.localRoot).create(recursive: true);
    } catch (_) {}
  }

  Future<void> _save() async {
    final p = _prefs;
    if (p == null) return;
    await p.setString('deviceName', settings.deviceName);
    await p.setString('localRoot', settings.localRoot);
    await p.setString('direction', settings.direction.wire);
    await p.setBool('includeHidden', settings.includeHidden);
    await p.setBool('mirrorDelete', settings.mirrorDelete);
    await p.setString('peerId', settings.peerId);
    await p.setString('manualHost', settings.manualHost);
    await p.setBool('p2pMode', settings.p2pMode);
  }

  // ------------------------------------------------------------- 发现
  Map<String, Object?> _payload() => {
        'id': settings.deviceId,
        'name': settings.deviceName,
        'port': _server?.port ?? kServerPort,
        'root': settings.localRoot,
        'hue': hue,
        'role': 'phone',
        'p2p': settings.p2pMode,
        'app': '1.0.0',
      };

  Future<void> startDiscovery({bool manual = false}) async {
    _manual = manual;
    _settled = false;
    _adopting = false;
    _fails = 0;
    candidates.clear();
    discovery.hosts.clear();
    latency = 0;
    if (!manual) {
      peer = null;
      link = LinkState.scanning;
    }
    _scanStartedAt = DateTime.now();
    notice = '';

    _heartbeat?.cancel();
    _settleTimer?.cancel();

    discovery.payloadBuilder = _payload;
    discovery.onHost = _onHost;
    discovery.selfId = settings.deviceId;
    discovery.p2pMode = settings.p2pMode;
    final beaconMs = settings.p2pMode ? 300 : 700;
    discovery.intervalMs = beaconMs;
    final ok = await discovery.start();
    if (!ok) {
      link = LinkState.offline;
      notice = '打不开局域网广播，确认已连上 WiFi';
    }
    discovery.setInterval(beaconMs);
    _settleTimer = Timer.periodic(const Duration(milliseconds: 220), (_) => _maybeSettle());
    notifyListeners();
  }

  void _onHost(PeerInfo host) {
    candidates[host.id] = host;
    if (link == LinkState.connected && peer?.id == host.id) {
      peer = host.copyWith(latency: latency);
      notifyListeners();
      return;
    }
    notifyListeners();
  }

  void _maybeSettle() {
    if (_settled || _adopting || link == LinkState.connected) return;
    if (candidates.isEmpty) return;
    final started = _scanStartedAt;
    if (started == null) return;
    final wait = settings.p2pMode
        ? const Duration(milliseconds: 150)
        : const Duration(milliseconds: 500);
    if (DateTime.now().difference(started) < wait) return;

    _settled = true;
    final preferred = settings.peerId;
    if (preferred.isNotEmpty && candidates.containsKey(preferred)) {
      unawaited(_adopt(candidates[preferred]!));
      return;
    }
    if (candidates.length == 1 && !_manual && peer == null) {
      unawaited(_adopt(candidates.values.first));
      return;
    }
    if (candidates.length > 1 || _manual) {
      link = LinkState.choosing;
      final kind = settings.p2pMode ? '手机' : '电脑';
      notice = candidates.length > 1
          ? '发现 ${candidates.length} 台$kind，选一台同步'
          : '找到 1 台$kind，点一下连上';
    }
    notifyListeners();
  }

  Future<void> pickPeer(PeerInfo host) async {
    _settled = true;
    _settleTimer?.cancel();
    await _adopt(host);
  }

  Future<void> _adopt(PeerInfo host) async {
    if (_adopting) return;
    _adopting = true;
    final api = PeerApi(
      ip: host.ip,
      port: host.port,
      deviceName: settings.deviceName,
      deviceId: settings.deviceId,
    );
    final sw = Stopwatch()..start();
    try {
      await api.ping().timeout(const Duration(seconds: 3));
      sw.stop();
      _api?.close();
      _api = api;
      latency = sw.elapsedMilliseconds;
      peer = host.copyWith(latency: latency);
      settings.peerId = host.id;
      await _save();
      link = LinkState.connected;
      notice = '';
      _fails = 0;
      _settleTimer?.cancel();
      discovery.setInterval(1500);
      _startHeartbeat();
      notifyListeners();
      unawaited(refreshRemoteInfo());
    } catch (_) {
      api.close();
      link = candidates.length > 1 ? LinkState.choosing : LinkState.scanning;
      notice = '连不上 ${host.name}，确认对方已打开 SynSimplify 并放行防火墙';
      notifyListeners();
    } finally {
      _adopting = false;
    }
  }

  Future<void> refreshRemoteInfo() async {
    final api = _api;
    if (api == null) return;
    try {
      final info = await api.info();
      final p = peer;
      if (p == null) return;
      peer = p.copyWith(
        root: (info['root'] ?? p.root).toString(),
        name: (info['name'] ?? p.name).toString(),
        busy: info['busy'] == true,
      );
      notifyListeners();
    } catch (_) {}
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 5), (timer) async {
      final api = _api;
      final p = peer;
      if (api == null || p == null) {
        timer.cancel();
        return;
      }
      final sw = Stopwatch()..start();
      try {
        final info = await api.info().timeout(const Duration(seconds: 4));
        sw.stop();
        latency = sw.elapsedMilliseconds;
        _fails = 0;
        peer = p.copyWith(
          root: (info['root'] ?? p.root).toString(),
          busy: info['busy'] == true,
          latency: latency,
        );
        notifyListeners();
      } catch (_) {
        _fails++;
        if (_fails >= 3) {
          timer.cancel();
          _api?.close();
          _api = null;
          peer = null;
          link = LinkState.offline;
          notice = '和对方断开了，正在重新寻找…';
          notifyListeners();
          unawaited(startDiscovery());
        }
      }
    });
  }

  Future<bool> connectManual(String text) async {
    var input = text.trim();
    if (input.isEmpty) return false;
    input = input.replaceFirst('http://', '');
    final head = input.split('/').first;
    final parts = head.split(':');
    final ip = parts.first;
    final defaultPort = settings.p2pMode ? kServerPort : kPeerDefaultPort;
    final port = parts.length > 1
        ? (int.tryParse(parts[1]) ?? defaultPort)
        : defaultPort;
    if (!RegExp(r'^\d{1,3}(\.\d{1,3}){3}$').hasMatch(ip)) {
      notice = '地址格式：192.168.1.8 或 192.168.1.8:$defaultPort';
      notifyListeners();
      return false;
    }
    settings.manualHost = '$ip:$port';
    await _save();

    _settleTimer?.cancel();
    link = LinkState.scanning;
    notice = '正在连接 $ip:$port…';
    notifyListeners();

    final host = PeerInfo(
      id: 'manual-$ip',
      name: settings.p2pMode ? '手机' : '电脑',
      ip: ip,
      port: port,
      hue: 220,
      role: settings.p2pMode ? 'phone' : 'host',
    );
    await _adopt(host);
    return connected;
  }

  Future<void> switchPeer() async {
    _heartbeat?.cancel();
    _api?.close();
    _api = null;
    peer = null;
    settings.peerId = '';
    await _save();
    await startDiscovery(manual: true);
  }

  // ------------------------------------------------------------- 设置
  void setDirection(Direction d) {
    settings.direction = d;
    unawaited(_save());
    notifyListeners();
  }

  void setIncludeHidden(bool v) {
    settings.includeHidden = v;
    unawaited(_save());
    notifyListeners();
  }

  void setMirrorDelete(bool v) {
    settings.mirrorDelete = v;
    unawaited(_save());
    notifyListeners();
  }

  /// 切换手机互传模式。换模式后清掉旧对端，立刻重新发现。
  Future<void> setP2pMode(bool v) async {
    if (settings.p2pMode == v) return;
    settings.p2pMode = v;
    await _save();
    _heartbeat?.cancel();
    _api?.close();
    _api = null;
    peer = null;
    settings.peerId = '';
    await _save();
    link = LinkState.scanning;
    notifyListeners();
    await startDiscovery();
  }

  void setDeviceName(String name) {
    final text = name.trim();
    if (text.isEmpty) return;
    settings.deviceName = text;
    unawaited(_save());
    notifyListeners();
  }

  Future<void> requestAllFiles() async {
    await Native.requestAllFiles();
    await Future<void>.delayed(const Duration(milliseconds: 400));
    final granted = await Native.isAllFiles();
    if (granted != allFiles) {
      allFiles = granted;
      if (granted && settings.localRoot.contains('/Android/data/')) {
        settings.localRoot = _pickDefaultRoot();
        await _ensureLocalRoot();
        await _save();
      }
      notifyListeners();
    }
  }

  Future<void> pickLocalRoot() async {
    if (!allFiles) {
      await requestAllFiles();
      if (!allFiles) return;
    }
    final path = await Native.pickFolder();
    if (path == null || path.isEmpty) return;
    settings.localRoot = path;
    await _ensureLocalRoot();
    await _save();
    notifyListeners();
  }

  Future<void> useDefaultRoot() async {
    settings.localRoot = _pickDefaultRoot();
    await _ensureLocalRoot();
    await _save();
    notifyListeners();
  }

  // ------------------------------------------------------------- 同步
  Future<void> startSync({bool dry = false}) async {
    if (running) return;
    final api = _api;
    if (api == null || peer == null) {
      notice = '先连上${settings.p2pMode ? '手机' : '电脑'}再同步';
      notifyListeners();
      return;
    }
    await _ensureLocalRoot();

    running = true;
    dryRun = dry;
    stopped = false;
    ops = [];
    stats = SyncStats();
    totalBytes = 0;
    doneBytes = 0;
    liveBytes = 0;
    finishedAt = 0;
    currentFile = '';
    phase = dry
        ? '正在对比两边文件…'
        : '正在读取${settings.p2pMode ? '对方手机' : '电脑'}文件列表…';
    notifyListeners();

    final engine = SyncEngine(
      api: api,
      localRoot: settings.localRoot,
      direction: settings.direction,
      includeHidden: settings.includeHidden,
      mirrorDelete: settings.mirrorDelete,
      remoteLabel: settings.p2pMode ? '对方手机' : '电脑',
      onPhase: (text) {
        phase = text;
        notifyListeners();
      },
      onPlan: (list, s) {
        ops = list;
        totalBytes = list
            .where((o) => o.kind.movesFile)
            .fold<int>(0, (sum, o) => sum + o.size);
        phase = '计划 ${list.where((o) => o.kind.movesFile).length} 个文件';
        notifyListeners();
      },
      onOpStart: (op) {
        currentFile = op.path;
        liveBytes = 0;
        notifyListeners();
      },
      onOpProgress: (op) {
        liveBytes = (op.size * op.progress).round();
        notifyListeners();
      },
      onOpDone: (op) {
        if (op.kind.movesFile) {
          doneBytes += op.size;
          liveBytes = 0;
        }
        notifyListeners();
      },
      onOpFail: (op) {
        liveBytes = 0;
        notifyListeners();
      },
      onFinish: (s, dryRun) {
        stats = s;
        finishedAt = DateTime.now().millisecondsSinceEpoch;
        liveBytes = 0;
        notifyListeners();
      },
    );
    _engine = engine;
    await Native.keepAwake(true);
    try {
      await engine.run(dryRun: dry);
      phase = dry ? '预览完成，没有改动任何文件' : '同步完成';
    } catch (e) {
      phase = '同步失败：${e.toString().replaceFirst('PeerError: ', '')}';
    } finally {
      running = false;
      _engine = null;
      await Native.keepAwake(false);
      notifyListeners();
    }
  }

  void stopSync() {
    if (!running) return;
    stopped = true;
    _engine?.cancel();
    notifyListeners();
  }

  @override
  void dispose() {
    _heartbeat?.cancel();
    _settleTimer?.cancel();
    _api?.close();
    unawaited(discovery.stop());
    unawaited(_server?.stop() ?? Future<void>.value());
    super.dispose();
  }
}
