import 'dart:async';
import 'dart:io';

import 'models.dart';
import 'net_client.dart';


const int kMaxScan = 40000;

const Set<String> kJunkNames = {
  '.DS_Store',
  'Thumbs.db',
  'desktop.ini',
  'ehthumbs.db',
  r'$RECYCLE.BIN',
  'System Volume Information',
  '.syn_part',
};

const List<String> kJunkSuffix = ['.syn_part', '.crdownload', '.partial', '.tmp~'];

bool _isJunk(String name) {
  if (kJunkNames.contains(name)) return true;
  for (final s in kJunkSuffix) {
    if (name.endsWith(s)) return true;
  }
  return false;
}

String baseName(String path) {
  final i = path.lastIndexOf(RegExp(r'[\\/]'));
  return i >= 0 ? path.substring(i + 1) : path;
}

String joinPath(String root, String rel) {
  if (rel.isEmpty) return root;
  if (root.endsWith('/')) return '$root$rel';
  return '$root/$rel';
}

bool isSafeRel(String rel) {
  final text = rel.replaceAll('\\', '/').trim();
  if (text.startsWith('/')) return false;
  for (final part in text.split('/')) {
    if (part == '..') return false;
    if (part.contains('\u0000')) return false;
  }
  return true;
}

/// 列出本地整棵树。返回的路径都是相对 root 的 posix 路径。
Future<ScanResult> scanLocal(
  String root, {
  bool includeHidden = false,
  int limit = kMaxScan,
}) async {
  final items = <ManifestItem>[];
  final base = Directory(root);
  if (!await base.exists()) {
    try {
      await base.create(recursive: true);
    } catch (_) {
      return const ScanResult([]);
    }
    return const ScanResult([]);
  }

  final stack = <MapEntry<String, String>>[MapEntry(root, '')];
  while (stack.isNotEmpty) {
    final current = stack.removeLast();
    List<FileSystemEntity> entries;
    try {
      entries = await Directory(current.key).list(followLinks: false).toList();
    } catch (_) {
      continue;
    }
    for (final entity in entries) {
      final name = baseName(entity.path);
      if (name.isEmpty || _isJunk(name)) continue;
      if (!includeHidden && name.startsWith('.')) continue;
      if (entity is Link) continue;

      final rel = '${current.value}$name';
      try {
        final stat = await entity.stat();
        if (entity is Directory) {
          items.add(ManifestItem(rel, 0, stat.modified.millisecondsSinceEpoch, true));
          stack.add(MapEntry(entity.path, '$rel/'));
        } else if (entity is File) {
          items.add(ManifestItem(rel, stat.size, stat.modified.millisecondsSinceEpoch, false));
        }
      } catch (_) {
        continue;
      }
      if (items.length >= limit) {
        items.sort((a, b) => a.p.compareTo(b.p));
        return ScanResult(items, truncated: true);
      }
    }
  }
  items.sort((a, b) => a.p.compareTo(b.p));
  return ScanResult(items);
}

/// 生成同步计划。
///
/// 约定：[OpKind.push] 表示「文件从电脑流向手机」，[OpKind.pull] 表示
/// 「文件从手机流向电脑」。手机上执行时，push 就是下载、pull 就是上传。
List<SyncOp> makePlan(
  List<ManifestItem> local,
  List<ManifestItem> remote,
  Direction direction, {
  bool mirrorDelete = false,
}) {
  final L = {for (final it in local) it.p: it};
  final R = {for (final it in remote) it.p: it};
  final ops = <SyncOp>[];

  final lDirs = {for (final e in L.entries) if (e.value.isDir) e.key};
  final rDirs = {for (final e in R.entries) if (e.value.isDir) e.key};

  if (direction != Direction.pull) {
    final missing = lDirs.difference(rDirs).toList()
      ..sort((a, b) => _depth(a).compareTo(_depth(b)));
    for (final p in missing) {
      ops.add(SyncOp(kind: OpKind.mkdirRemote, path: p, why: '目录'));
    }
  }
  if (direction != Direction.push) {
    final missing = rDirs.difference(lDirs).toList()
      ..sort((a, b) => _depth(a).compareTo(_depth(b)));
    for (final p in missing) {
      ops.add(SyncOp(kind: OpKind.mkdirLocal, path: p, why: '目录'));
    }
  }

  if (direction == Direction.push || direction == Direction.two) {
    // 电脑 → 手机：以远端清单为源
    for (final item in R.values) {
      if (item.isDir) continue;
      final mine = L[item.p];
      if (mine == null) {
        ops.add(SyncOp(kind: OpKind.push, path: item.p, size: item.size,
            mtime: item.mtime, why: '新增'));
        continue;
      }
      if (mine.isDir) {
        ops.add(SyncOp(kind: OpKind.skip, path: item.p, why: '类型冲突'));
        continue;
      }
      if (mine.size == item.size) {
        ops.add(SyncOp(kind: OpKind.same, path: item.p, size: item.size,
            mtime: item.mtime, why: '相同'));
        continue;
      }
      if (direction == Direction.two) {
        final dt = item.mtime - mine.mtime;
        if (dt.abs() <= 1500) {
          ops.add(SyncOp(kind: OpKind.push, path: item.p, size: item.size,
              mtime: item.mtime, why: '冲突 · 以电脑为准'));
        } else if (dt > 0) {
          ops.add(SyncOp(kind: OpKind.push, path: item.p, size: item.size,
              mtime: item.mtime, why: '电脑较新'));
        } else {
          ops.add(SyncOp(kind: OpKind.pull, path: item.p, size: mine.size,
              mtime: mine.mtime, why: '手机较新'));
        }
      } else {
        ops.add(SyncOp(kind: OpKind.push, path: item.p, size: item.size,
            mtime: item.mtime, why: '更新'));
      }
    }
  }

  if (direction == Direction.pull) {
    for (final item in L.values) {
      if (item.isDir) continue;
      final other = R[item.p];
      if (other == null) {
        ops.add(SyncOp(kind: OpKind.pull, path: item.p, size: item.size,
            mtime: item.mtime, why: '新增'));
        continue;
      }
      if (other.isDir) {
        ops.add(SyncOp(kind: OpKind.skip, path: item.p, why: '类型冲突'));
        continue;
      }
      if (other.size == item.size) {
        ops.add(SyncOp(kind: OpKind.same, path: item.p, size: item.size,
            mtime: item.mtime, why: '相同'));
        continue;
      }
      ops.add(SyncOp(kind: OpKind.pull, path: item.p, size: item.size,
          mtime: item.mtime, why: '更新'));
    }
  }

  if (direction == Direction.two) {
    for (final item in L.values) {
      if (item.isDir) continue;
      if (R.containsKey(item.p)) continue;
      ops.add(SyncOp(kind: OpKind.pull, path: item.p, size: item.size,
          mtime: item.mtime, why: '新增'));
    }
  }

  if (mirrorDelete && direction != Direction.two) {
    if (direction == Direction.push) {
      for (final item in L.values) {
        if (item.isDir) continue;
        if (!R.containsKey(item.p)) {
          ops.add(SyncOp(kind: OpKind.delLocal, path: item.p, size: item.size,
              why: '多余'));
        }
      }
    } else {
      for (final item in R.values) {
        if (item.isDir) continue;
        if (!L.containsKey(item.p)) {
          ops.add(SyncOp(kind: OpKind.delRemote, path: item.p, size: item.size,
              why: '多余'));
        }
      }
    }
  }

  int rank(SyncOp op) => switch (op.kind) {
        OpKind.mkdirRemote || OpKind.mkdirLocal => 0,
        OpKind.push || OpKind.pull => 1,
        OpKind.delRemote || OpKind.delLocal => 2,
        _ => 3,
      };
  ops.sort((a, b) {
    final r = rank(a).compareTo(rank(b));
    return r != 0 ? r : a.path.compareTo(b.path);
  });
  return ops;
}

int _depth(String p) => '/'.allMatches(p).length;

class SyncEngine {
  SyncEngine({
    required this.api,
    required this.localRoot,
    required this.direction,
    required this.includeHidden,
    required this.mirrorDelete,
    this.onPhase,
    this.onPlan,
    this.onOpStart,
    this.onOpProgress,
    this.onOpDone,
    this.onOpFail,
    this.onFinish,
  });

  final PeerApi api;
  final String localRoot;
  final Direction direction;
  final bool includeHidden;
  final bool mirrorDelete;

  final void Function(String text)? onPhase;
  final void Function(List<SyncOp> ops, SyncStats stats)? onPlan;
  final void Function(SyncOp op)? onOpStart;
  final void Function(SyncOp op)? onOpProgress;
  final void Function(SyncOp op)? onOpDone;
  final void Function(SyncOp op)? onOpFail;
  final void Function(SyncStats stats, bool dry)? onFinish;

  bool _cancelled = false;
  void cancel() => _cancelled = true;

  String _path(String rel) => joinPath(localRoot, rel);

  Future<SyncStats> run({bool dryRun = false}) async {
    final stats = SyncStats();
    final started = DateTime.now();

    onPhase?.call('读取电脑文件列表…');
    final remote = await api.scan(hidden: includeHidden);
    onPhase?.call('扫描手机文件夹…');
    final local = await scanLocal(localRoot, includeHidden: includeHidden);

    final ops = makePlan(local.items, remote.items, direction, mirrorDelete: mirrorDelete);

    stats.totalFiles = ops.where((o) => o.kind.movesFile).length;
    onPlan?.call(ops, stats);
    if (local.truncated || remote.truncated) {
      onPhase?.call('文件较多，本次只处理前 $kMaxScan 项');
    }

    if (dryRun) {
      stats.elapsed = DateTime.now().difference(started).inMilliseconds / 1000;
      onFinish?.call(stats, true);
      return stats;
    }

    var doneBytes = 0;
    var consecutiveFails = 0;

    for (final op in ops) {
      if (_cancelled) {
        onPhase?.call('已停止');
        break;
      }
      if (op.kind == OpKind.same) continue;
      if (op.kind == OpKind.skip) {
        op.status = OpStatus.skipped;
        stats.skipped++;
        onOpDone?.call(op);
        continue;
      }

      op.status = OpStatus.running;
      op.progress = 0;
      onOpStart?.call(op);
      final sw = Stopwatch()..start();

      try {
        switch (op.kind) {
          case OpKind.push:
            // 电脑 → 手机：手机这边是下载
            await api.downloadFile(
              op.path,
              File(_path(op.path)),
              onProgress: (sent, total) {
                op.progress = total > 0 ? sent / total : 0;
                onOpProgress?.call(op);
              },
            );
            stats.upFiles++;
            stats.upBytes += op.size;
          case OpKind.pull:
            // 手机 → 电脑：手机这边是上传
            await api.uploadFile(
              op.path,
              File(_path(op.path)),
              mtime: op.mtime,
              onProgress: (sent, total) {
                op.progress = total > 0 ? sent / total : 0;
                onOpProgress?.call(op);
              },
            );
            stats.downFiles++;
            stats.downBytes += op.size;
          case OpKind.mkdirRemote:
            await api.mkdir(op.path);
          case OpKind.mkdirLocal:
            await Directory(_path(op.path)).create(recursive: true);
          case OpKind.delRemote:
            await api.delete(op.path);
          case OpKind.delLocal:
            await _deleteLocal(_path(op.path));
          case OpKind.same:
          case OpKind.skip:
            break;
        }
        op.status = OpStatus.done;
        op.ms = sw.elapsedMilliseconds;
        op.progress = 1;
        consecutiveFails = 0;
        if (op.kind.movesFile) doneBytes += op.size;
        onOpDone?.call(op);
      } catch (e) {
        op.status = OpStatus.failed;
        op.error = _shortError(e);
        stats.failed++;
        consecutiveFails++;
        onOpFail?.call(op);
        if (consecutiveFails >= 4 && _isNetworkError(e)) {
          onPhase?.call('网络中断，同步提前结束');
          break;
        }
        if (consecutiveFails >= 12) break;
      }
      stats.elapsed = DateTime.now().difference(started).inMilliseconds / 1000;
      stats.speed = stats.elapsed > 0.2
          ? (doneBytes / 1024 / 1024) / stats.elapsed
          : 0;
    }

    stats.elapsed = DateTime.now().difference(started).inMilliseconds / 1000;
    final moved = stats.upBytes + stats.downBytes;
    stats.speed = stats.elapsed > 0.05 ? (moved / 1024 / 1024) / stats.elapsed : 0;
    onFinish?.call(stats, false);
    return stats;
  }

  Future<void> _deleteLocal(String path) async {
    final type = await FileSystemEntity.type(path, followLinks: false);
    if (type == FileSystemEntityType.directory) {
      await Directory(path).delete(recursive: true);
    } else if (type != FileSystemEntityType.notFound) {
      await File(path).delete();
    }
  }

  String _shortError(Object e) {
    final text = e.toString().replaceFirst('PeerError: ', '');
    return text.length > 90 ? '${text.substring(0, 90)}…' : text;
  }

  bool _isNetworkError(Object e) =>
      e is SocketException || e is HttpException || e is TimeoutException;
}
