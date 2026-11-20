import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:syn_simplify/local_server.dart';
import 'package:syn_simplify/models.dart';
import 'package:syn_simplify/net_client.dart';
import 'package:syn_simplify/sync_engine.dart';

Future<void> writeFile(String path, List<int> bytes, {int? mtimeMs}) async {
  final file = File(path);
  await file.parent.create(recursive: true);
  await file.writeAsBytes(bytes);
  if (mtimeMs != null) {
    await file.setLastModified(DateTime.fromMillisecondsSinceEpoch(mtimeMs));
  }
}

Future<Map<String, dynamic>?> waitPing(PeerApi api, {int tries = 25}) async {
  for (var i = 0; i < tries; i++) {
    try {
      final res = await api.ping();
      if (res['ok'] == true) return res;
    } catch (_) {}
    await Future<void>.delayed(const Duration(milliseconds: 200));
  }
  return null;
}

void main() {
  test('扫描和计划：新增 / 更新 / 相同 / 冲突', () {
    final local = [
      const ManifestItem('keep.txt', 10, 1000, false),
      const ManifestItem('same.txt', 10, 1000, false),
      const ManifestItem('newer_local.txt', 20, 9000, false),
      const ManifestItem('newer_remote.txt', 21, 1000, false),
      const ManifestItem('dir/a.txt', 3, 1000, false),
    ];
    final remote = [
      const ManifestItem('same.txt', 10, 1000, false),
      const ManifestItem('newer_local.txt', 12, 2000, false),
      const ManifestItem('newer_remote.txt', 22, 8000, false),
      const ManifestItem('only_remote.txt', 5, 1000, false),
    ];

    final ops = makePlan(local, remote, Direction.two);
    SyncOp? find(String p) {
      for (final op in ops) {
        if (op.path == p) return op;
      }
      return null;
    }

    expect(find('keep.txt')!.kind, OpKind.pull);
    expect(find('same.txt')!.kind, OpKind.same);
    expect(find('newer_local.txt')!.kind, OpKind.pull);
    expect(find('newer_remote.txt')!.kind, OpKind.push);
    expect(find('only_remote.txt')!.kind, OpKind.push);
    expect(find('dir/a.txt')!.kind, OpKind.pull);

    // 电脑 → 手机：远端有的都推下来
    final push = makePlan(local, remote, Direction.push);
    expect(push.where((o) => o.kind == OpKind.pull).isEmpty, true);
    expect(push.any((o) => o.path == 'only_remote.txt' && o.kind == OpKind.push), true);

    // 镜像：手机多出来的文件要被删
    final mirror = makePlan(local, remote, Direction.push, mirrorDelete: true);
    expect(mirror.any((o) => o.path == 'keep.txt' && o.kind == OpKind.delLocal), true);
  });

  test('手机端两个目录互相同步（走本地 HTTP 服务）', () async {
    final tmp = await Directory.systemTemp.createTemp('syn_pair_');
    final phoneRoot = '${tmp.path}/phone';
    final pcRoot = '${tmp.path}/pc';
    await Directory(phoneRoot).create(recursive: true);
    await Directory(pcRoot).create(recursive: true);

    final base = DateTime.now().millisecondsSinceEpoch - 60000;
    await writeFile('$phoneRoot/photo.jpg', List<int>.generate(20000, (i) => i % 251), mtimeMs: base);
    await writeFile('$phoneRoot/sub/note.md', 'from phone'.codeUnits, mtimeMs: base);
    await writeFile('$pcRoot/doc.pdf', List<int>.generate(9000, (i) => (i * 7) % 253), mtimeMs: base);
    await writeFile('$pcRoot/sub/pc.txt', 'from pc'.codeUnits, mtimeMs: base);

    final server = LocalServer(
      deviceName: 'PC',
      deviceId: 'test-pc',
      hue: 210,
      rootProvider: () => pcRoot,
    );
    expect(await server.start(), true);

    final api = PeerApi(ip: '127.0.0.1', port: server.port, deviceName: '手机', deviceId: 'test-phone');
    expect(await waitPing(api), isNotNull);

    final info = await api.info();
    expect(info['root'], pcRoot);

    final engine = SyncEngine(
      api: api,
      localRoot: phoneRoot,
      direction: Direction.two,
      includeHidden: false,
      mirrorDelete: false,
      onOpFail: (op) => print('FAIL ${op.path}: ${op.error}'),
    );
    final stats = await engine.run();
    expect(stats.failed, 0);

    expect(File('$phoneRoot/doc.pdf').existsSync(), true);
    expect(File('$phoneRoot/sub/pc.txt').existsSync(), true);
    expect(File('$pcRoot/photo.jpg').existsSync(), true);
    expect(File('$pcRoot/sub/note.md').existsSync(), true);
    expect(
      await File('$phoneRoot/doc.pdf').readAsBytes(),
      await File('$pcRoot/doc.pdf').readAsBytes(),
    );

    // 电脑上的新版本应该覆盖手机
    await writeFile('$pcRoot/doc.pdf', List<int>.generate(12000, (i) => (i * 3) % 250),
        mtimeMs: DateTime.now().millisecondsSinceEpoch);
    final push = SyncEngine(
      api: api,
      localRoot: phoneRoot,
      direction: Direction.push,
      includeHidden: false,
      mirrorDelete: false,
      onOpFail: (op) => print('FAIL ${op.path}: ${op.error}'),
    );
    await push.run();
    expect(
      await File('$phoneRoot/doc.pdf').readAsBytes(),
      await File('$pcRoot/doc.pdf').readAsBytes(),
    );

    // 手机上的新版本应该覆盖电脑
    await writeFile('$phoneRoot/sub/note.md', 'phone v2'.codeUnits,
        mtimeMs: DateTime.now().millisecondsSinceEpoch + 4000);
    final pull = SyncEngine(
      api: api,
      localRoot: phoneRoot,
      direction: Direction.pull,
      includeHidden: false,
      mirrorDelete: false,
      onOpFail: (op) => print('FAIL ${op.path}: ${op.error}'),
    );
    await pull.run();
    expect(await File('$pcRoot/sub/note.md').readAsString(), 'phone v2');

    // 越界路径必须被拒绝
    var blocked = false;
    try {
      await api.downloadFile('../pc/doc.pdf', File('${tmp.path}/evil.bin'));
    } catch (_) {
      blocked = true;
    }
    expect(blocked, true);
    expect(File('${tmp.path}/evil.bin').existsSync(), false);

    api.close();
    await server.stop();
    await tmp.delete(recursive: true);
  });

  test('和电脑端 Python 服务互通（真跨语言）', () async {
    final hostDir = Directory('../host');
    if (!hostDir.existsSync() || !Platform.isWindows) {
      return;
    }
    final tmp = await Directory.systemTemp.createTemp('syn_py_');
    final phoneRoot = '${tmp.path}/phone';
    final pcRoot = '${tmp.path}/pc';
    await Directory(phoneRoot).create(recursive: true);

    final base = DateTime.now().millisecondsSinceEpoch - 5000;
    await writeFile('$phoneRoot/up.txt', 'to pc'.codeUnits, mtimeMs: base);

    final port = 37881;
    final proc = await Process.start(
      'python',
      ['main.py', '--no-gui', '--port', '$port', '--dir', pcRoot],
      workingDirectory: hostDir.absolute.path,
    );
    proc.stderr.drain<void>();
    proc.stdout.drain<void>();

    final api = PeerApi(ip: '127.0.0.1', port: port);
    try {
      final ping = await waitPing(api);
      expect(ping, isNotNull, reason: '电脑端服务没起来');

      // 电脑上放一个文件，手机方向 = 电脑 → 手机
      await writeFile('$pcRoot/from_pc.txt', 'hello phone'.codeUnits,
          mtimeMs: DateTime.now().millisecondsSinceEpoch);

      final down = SyncEngine(
        api: api,
        localRoot: phoneRoot,
        direction: Direction.push,
        includeHidden: false,
        mirrorDelete: false,
      );
      final stats = await down.run();
      expect(stats.failed, 0);
      expect(await File('$phoneRoot/from_pc.txt').readAsString(), 'hello phone');

      // 手机方向 = 手机 → 电脑
      final up = SyncEngine(
        api: api,
        localRoot: phoneRoot,
        direction: Direction.pull,
        includeHidden: false,
        mirrorDelete: false,
      );
      await up.run();
      expect(await File('$pcRoot/up.txt').readAsString(), 'to pc');
    } finally {
      api.close();
      proc.kill();
      await tmp.delete(recursive: true);
    }
  }, timeout: const Timeout(Duration(minutes: 2)));
}
