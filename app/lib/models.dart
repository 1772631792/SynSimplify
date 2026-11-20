import 'package:flutter/painting.dart';

/// 同步方向
enum Direction {
  push, // 电脑 → 手机
  pull, // 手机 → 电脑
  two,  // 双向
}

extension DirectionX on Direction {
  String get wire => switch (this) {
        Direction.push => 'push',
        Direction.pull => 'pull',
        Direction.two => 'two',
      };

  String get title => switch (this) {
        Direction.push => '电脑 → 手机',
        Direction.pull => '手机 → 电脑',
        Direction.two => '双向同步',
      };

  String get subtitle => switch (this) {
        Direction.push => '电脑上的新文件覆盖到手机，日常最常用',
        Direction.pull => '手机上的新文件覆盖到电脑',
        Direction.two => '两边取新、缺的补齐，谁也丢不了',
      };

  String get badge => switch (this) {
        Direction.push => '推荐',
        Direction.pull => '',
        Direction.two => '稳',
      };

  static Direction fromWire(String v) => switch (v) {
        'pull' => Direction.pull,
        'two' => Direction.two,
        _ => Direction.push,
      };
}

/// 对端（电脑）
class PeerInfo {
  const PeerInfo({
    required this.id,
    required this.name,
    required this.ip,
    required this.port,
    this.root = '',
    this.hue = 210,
    this.busy = false,
    this.lastSeen = 0,
    this.latency = 0,
  });

  final String id;
  final String name;
  final String ip;
  final int port;
  final String root;
  final int hue;
  final bool busy;
  final int lastSeen;
  final int latency;

  String get label => '$ip:$port';

  PeerInfo copyWith({
    String? name,
    String? root,
    int? port,
    bool? busy,
    int? lastSeen,
    int? latency,
    String? ip,
  }) =>
      PeerInfo(
        id: id,
        name: name ?? this.name,
        ip: ip ?? this.ip,
        port: port ?? this.port,
        root: root ?? this.root,
        hue: hue,
        busy: busy ?? this.busy,
        lastSeen: lastSeen ?? this.lastSeen,
        latency: latency ?? this.latency,
      );
}

class ScanResult {
  const ScanResult(this.items, {this.truncated = false});

  final List<ManifestItem> items;
  final bool truncated;
}

/// 清单里的一项：[相对路径, 字节, 毫秒时间戳, 是否文件夹]
class ManifestItem {
  const ManifestItem(this.p, this.size, this.mtime, this.isDir);

  final String p;
  final int size;
  final int mtime;
  final bool isDir;

  static ManifestItem fromList(List<dynamic> raw) => ManifestItem(
        (raw.isNotEmpty ? raw[0] : '').toString(),
        raw.length > 1 ? (raw[1] as num).toInt() : 0,
        raw.length > 2 ? (raw[2] as num).toInt() : 0,
        raw.length > 3 ? (raw[3] as num).toInt() == 1 : false,
      );
}

enum OpKind { push, pull, mkdirRemote, mkdirLocal, delRemote, delLocal, same, skip }

extension OpKindX on OpKind {
  bool get movesFile => this == OpKind.push || this == OpKind.pull;
  bool get transfers => movesFile;
  String get label => switch (this) {
        OpKind.push => '↓ 到手机',
        OpKind.pull => '↑ 到电脑',
        OpKind.mkdirRemote || OpKind.mkdirLocal => '目录',
        OpKind.delRemote => '删除手机',
        OpKind.delLocal => '删除电脑',
        OpKind.same => '已相同',
        OpKind.skip => '跳过',
      };
}

enum OpStatus { pending, running, done, failed, skipped }

class SyncOp {
  SyncOp({
    required this.kind,
    required this.path,
    this.size = 0,
    this.mtime = 0,
    this.why = '',
  });

  final OpKind kind;
  final String path;
  final int size;
  final int mtime;
  final String why;

  OpStatus status = OpStatus.pending;
  double progress = 0;
  int ms = 0;
  String error = '';

  String get statusText {
    switch (status) {
      case OpStatus.pending:
        return why.isEmpty ? '待同步' : why;
      case OpStatus.running:
        return '传输中 ${(progress * 100).round()}%';
      case OpStatus.done:
        if (kind.movesFile) return ms > 0 ? '完成 · $ms ms' : '完成';
        if (kind == OpKind.delLocal || kind == OpKind.delRemote) return '已删除';
        if (kind == OpKind.mkdirLocal || kind == OpKind.mkdirRemote) return '已创建';
        return '完成';
      case OpStatus.failed:
        return error.isEmpty ? '失败' : '失败：$error';
      case OpStatus.skipped:
        return why.isEmpty ? '跳过' : why;
    }
  }
}

class SyncStats {
  int upFiles = 0;
  int upBytes = 0;
  int downFiles = 0;
  int downBytes = 0;
  int skipped = 0;
  int failed = 0;
  int totalFiles = 0;
  double elapsed = 0;
  double speed = 0;

  void reset() {
    upFiles = upBytes = downFiles = downBytes = skipped = failed = totalFiles = 0;
    elapsed = 0;
    speed = 0;
  }
}

const int kDiscoveryPort = 37120;
const int kServerPort = 37131;
const int kPeerDefaultPort = 37121;
const String kTag = 'SYNSIMPLIFY';
const String kDiscoverPayload = '$kTag/DISCOVER';
const String kHostPayload = '$kTag/HOST';

const double kAccentHue = 220;

Color hueColor(int hue, [double light = 0.62]) =>
    HSLColor.fromAHSL(1, (hue % 360).toDouble(), 0.68, light).toColor();

String humanBytes(num n) {
  final v = n.toDouble();
  if (v >= 1024 * 1024 * 1024) {
    return '${(v / 1024 / 1024 / 1024).toStringAsFixed(2)} GB';
  }
  if (v >= 1024 * 1024) return '${(v / 1024 / 1024).toStringAsFixed(1)} MB';
  if (v >= 1024) return '${(v / 1024).toStringAsFixed(0)} KB';
  return '${v.toStringAsFixed(0)} B';
}

String humanSpeed(double mbps) =>
    mbps >= 0.05 ? '${mbps.toStringAsFixed(1)} MB/s' : '';

