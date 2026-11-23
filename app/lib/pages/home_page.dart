import 'package:flutter/material.dart';

import '../app_state.dart';
import '../models.dart';
import '../op_row.dart';
import '../theme.dart';
import '../widgets.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.app, required this.onOpenLog});

  final AppState app;
  final VoidCallback onOpenLog;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final ScrollController _scroll = ScrollController();
  bool _wasRunning = false;

  AppState get app => widget.app;
  VoidCallback get onOpenLog => widget.onOpenLog;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToProgress() {
    if (!_scroll.hasClients) return;
    _scroll.animateTo(
      _scroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 420),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: ListenableBuilder(
        listenable: app,
        builder: (context, _) {
          if (app.running && !_wasRunning) {
            WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToProgress());
          }
          _wasRunning = app.running;

          final bottomInset = MediaQuery.paddingOf(context).bottom;
          // 列表和操作条上下排开，操作条不再盖住内容
          return Column(
            children: [
              Expanded(
                child: ListView(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(18, 8, 18, 16),
                  children: [
                    _header(context),
                    const SizedBox(height: 16),
                    _connectionCard(context),
                    const SizedBox(height: 14),
                    _folderCard(context),
                    const SizedBox(height: 12),
                    _directionCard(),
                    const SizedBox(height: 12),
                    _optionsCard(),
                    if (app.running || app.finishedAt > 0) ...[
                      const SizedBox(height: 14),
                      _progressCard(),
                    ],
                    if (app.ops.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      _recentCard(context),
                    ],
                    const SizedBox(height: 6),
                  ],
                ),
              ),
              Container(
                padding: EdgeInsets.fromLTRB(18, 8, 18, bottomInset + 30),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Palette.bg.withValues(alpha: 0.0),
                      Palette.bg.withValues(alpha: 0.92),
                      Palette.bg,
                    ],
                    stops: const [0.0, 0.30, 1.0],
                  ),
                ),
                child: _actions(context),
              ),
            ],
          );
        },
      ),
    );
  }

  // ------------------------------------------------------------ 顶部
  Widget _header(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ShaderMask(
                shaderCallback: (rect) => Palette.grad.createShader(rect),
                blendMode: BlendMode.srcIn,
                child: const Text(
                  'SynSimplify',
                  style: TextStyle(
                    fontSize: 27,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5,
                    color: Colors.white,
                  ),
                ),
              ),
              const SizedBox(height: 3),
              const Text(
                '同一 WiFi · 双向文件夹同步',
                style: TextStyle(color: Palette.textDim, fontSize: 12),
              ),
            ],
          ),
        ),
        _glassIcon(
          app.link == LinkState.scanning ? Icons.search_rounded : Icons.refresh_rounded,
          () => app.startDiscovery(manual: app.link == LinkState.choosing),
          tip: '重新搜索',
        ),
      ],
    );
  }

  Widget _glassIcon(IconData icon, VoidCallback onTap, {String? tip}) {
    return Padding(
      padding: const EdgeInsets.only(left: 8),
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withValues(alpha: 0.06),
              border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
            ),
            child: Icon(icon, size: 20, color: Palette.text),
          ),
        ),
      ),
    );
  }

  // ------------------------------------------------------------ 连接
  Widget _connectionCard(BuildContext context) {
    switch (app.link) {
      case LinkState.connected:
        return _connectedCard(context);
      case LinkState.choosing:
        return _choosingCard(context);
      case LinkState.offline:
        return _offlineCard(context);
      case LinkState.scanning:
        return _scanningCard(context);
    }
  }

  Widget _scanningCard(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(18, 10, 18, 16),
      child: Column(
        children: [
          const RadarOrb(active: true, connected: false, size: 148),
          const SizedBox(height: 4),
          const Text(
            '正在同一 WiFi 内寻找电脑…',
            style: TextStyle(color: Palette.text, fontSize: 14, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 5),
          Text(
            app.notice.isEmpty ? '只有一台电脑时会自动连上，不用点任何东西' : app.notice,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: app.notice.isEmpty ? Palette.textMuted : Palette.warn,
              fontSize: 11.5,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 6),
          TextButton.icon(
            onPressed: () => _manualDialog(context),
            icon: const Icon(Icons.link_rounded, size: 16),
            label: const Text('找不到？手动填电脑地址'),
            style: TextButton.styleFrom(foregroundColor: Palette.textDim),
          ),
        ],
      ),
    );
  }

  Widget _choosingCard(BuildContext context) {
    final peers = app.peerList;
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(
            '发现 ${peers.length} 台电脑',
            trailing: Pill(label: '选一台', color: Palette.accent2, dense: true),
          ),
          const SizedBox(height: 12),
          for (final peer in peers) ...[
            _peerTile(peer),
            const SizedBox(height: 8),
          ],
          if (app.notice.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(app.notice, style: const TextStyle(color: Palette.warn, fontSize: 11.5)),
            ),
          GhostButton(
            label: '手动填写地址',
            icon: Icons.link_rounded,
            height: 40,
            onTap: () => _manualDialog(context),
          ),
        ],
      ),
    );
  }

  Widget _peerTile(PeerInfo peer) {
    final selected = app.peer?.id == peer.id;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => app.pickPeer(peer),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.035),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected
                ? Palette.accent.withValues(alpha: 0.5)
                : Colors.white.withValues(alpha: 0.07),
          ),
        ),
        child: Row(
          children: [
            DeviceAvatar(
              hue: peer.hue,
              size: 40,
              icon: Icons.desktop_windows_rounded,
              online: true,
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    peer.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Palette.text,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${peer.ip}:${peer.port}',
                    style: const TextStyle(color: Palette.textMuted, fontSize: 11),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right_rounded, color: Palette.textDim, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _connectedCard(BuildContext context) {
    final peer = app.peer!;
    return GlassCard(
      borderColor: Palette.accent.withValues(alpha: 0.4),
      gradient: LinearGradient(
        colors: [
          Palette.accent.withValues(alpha: 0.14),
          Palette.accent2.withValues(alpha: 0.05),
        ],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      child: Column(
        children: [
          Row(
            children: [
              DeviceAvatar(
                hue: peer.hue,
                size: 44,
                icon: Icons.desktop_windows_rounded,
                online: true,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      peer.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Palette.text,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${peer.ip}:${peer.port}${app.latency > 0 ? ' · ${app.latency} ms' : ''}',
                      style: const TextStyle(color: Palette.textDim, fontSize: 11.5),
                    ),
                  ],
                ),
              ),
              Pill(
                label: '已连接',
                color: Palette.ok,
                icon: Icons.bolt_rounded,
                dense: true,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(
                  peer.busy ? '电脑正在同步…' : '电脑端也能点「立即同步」把文件推过来',
                  style: const TextStyle(color: Palette.textMuted, fontSize: 11),
                ),
              ),
              TextButton(
                onPressed: app.switchPeer,
                style: TextButton.styleFrom(
                  foregroundColor: Palette.textDim,
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  minimumSize: const Size(0, 28),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text('换一台', style: TextStyle(fontSize: 11.5)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _offlineCard(BuildContext context) {
    return GlassCard(
      borderColor: Palette.warn.withValues(alpha: 0.35),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.wifi_off_rounded, color: Palette.warn, size: 20),
              const SizedBox(width: 9),
              const Expanded(
                child: Text(
                  '没找到电脑',
                  style: TextStyle(
                    color: Palette.text,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Pill(label: '离线', color: Palette.warn, dense: true),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            app.notice.isEmpty
                ? '确认手机和电脑连的是同一个 WiFi，电脑端已打开 SynSimplify 并放行防火墙'
                : app.notice,
            style: const TextStyle(color: Palette.textMuted, fontSize: 11.5, height: 1.45),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: GradientButton(
                  label: '重新搜索',
                  icon: Icons.refresh_rounded,
                  height: 44,
                  compact: true,
                  onTap: () => app.startDiscovery(),
                ),
              ),
              const SizedBox(width: 9),
              Expanded(
                child: GhostButton(
                  label: '手动连接',
                  icon: Icons.link_rounded,
                  height: 44,
                  compact: true,
                  onTap: () => _manualDialog(context),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ 文件夹
  Widget _folderCard(BuildContext context) {
    final remote = app.remoteRoot;
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(
            '同步文件夹',
            trailing: app.allFiles
                ? null
                : const Pill(label: '需要文件权限', color: Palette.warn, dense: true),
          ),
          const SizedBox(height: 13),
          _folderRow(
            icon: Icons.desktop_windows_rounded,
            gradient: Palette.pushGrad,
            title: '电脑文件夹',
            path: remote.isEmpty ? '连上电脑后显示' : remote,
            trailing: const Pill(label: '只读', color: Palette.textDim, dense: true),
          ),
          _connector(),
          _folderRow(
            icon: Icons.smartphone_rounded,
            gradient: Palette.pullGrad,
            title: '手机文件夹',
            path: app.localRoot,
            onTap: app.pickLocalRoot,
            trailing: const Pill(label: '点这里换', color: Palette.mint, dense: true),
          ),
          if (!app.allFiles) ...[
            const SizedBox(height: 10),
            GestureDetector(
              onTap: app.requestAllFiles,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                decoration: BoxDecoration(
                  color: Palette.warn.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Palette.warn.withValues(alpha: 0.3)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.folder_special_rounded, size: 16, color: Palette.warn),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '想同步任意文件夹？点这里授予「所有文件访问」',
                        style: TextStyle(color: Palette.warn, fontSize: 11.5),
                      ),
                    ),
                    Icon(Icons.chevron_right_rounded, size: 18, color: Palette.warn),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _folderRow({
    required IconData icon,
    required Gradient gradient,
    required String title,
    required String path,
    Widget? trailing,
    VoidCallback? onTap,
  }) {
    final content = Row(
      children: [
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            gradient: gradient,
            borderRadius: BorderRadius.circular(11),
          ),
          child: Icon(icon, size: 18, color: Colors.white),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Palette.textDim, fontSize: 11)),
              const SizedBox(height: 2),
              Text(
                path,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Palette.text,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
        if (trailing != null) ...[const SizedBox(width: 8), trailing],
      ],
    );
    if (onTap == null) return content;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: content,
        ),
      ),
    );
  }

  Widget _connector() {
    final direction = app.settings.direction;
    final icon = switch (direction) {
      Direction.push => Icons.arrow_downward_rounded,
      Direction.pull => Icons.arrow_upward_rounded,
      Direction.two => Icons.swap_vert_rounded,
    };
    return SizedBox(
      height: 34,
      child: Row(
        children: [
          const SizedBox(width: 16),
          Container(
            width: 2,
            height: 10,
            color: Colors.white.withValues(alpha: 0.08),
          ),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 4),
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: Palette.gradOf(direction),
              boxShadow: [
                BoxShadow(
                  color: Palette.colorOf(direction).withValues(alpha: 0.35),
                  blurRadius: 10,
                ),
              ],
            ),
            child: Icon(icon, size: 12, color: Colors.white),
          ),
          Expanded(
            child: Container(
              height: 10,
              alignment: Alignment.centerLeft,
              child: Container(
                width: 2,
                height: 10,
                color: Colors.white.withValues(alpha: 0.08),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ 方向 / 选项
  Widget _directionCard() {
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionLabel('同步方向'),
          const SizedBox(height: 10),
          for (final d in Direction.values)
            DirectionTile(
              direction: d,
              selected: app.settings.direction == d,
              onTap: () => app.setDirection(d),
            ),
        ],
      ),
    );
  }

  Widget _optionsCard() {
    final twoWay = app.settings.direction == Direction.two;
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 10, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionLabel('选项', padding: EdgeInsets.only(left: 2)),
          const SizedBox(height: 4),
          ToggleRow(
            title: '删除对方多余的文件',
            subtitle: twoWay ? '双向同步时不生效' : '镜像效果，小心使用',
            value: app.settings.mirrorDelete,
            onChanged: app.setMirrorDelete,
          ),
          const SizedBox(height: 6),
          ToggleRow(
            title: '包含隐藏文件',
            subtitle: '以 . 开头的文件和文件夹',
            value: app.settings.includeHidden,
            onChanged: app.setIncludeHidden,
          ),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ 按钮
  Widget _actions(BuildContext context) {
    final connected = app.connected;
    final grad = Palette.gradOf(app.settings.direction);

    if (app.running) {
      final pct = (app.progress * 100).round();
      return Row(
        children: [
          Expanded(
            flex: 3,
            child: GradientButton(
              label: '同步中 $pct%',
              gradient: grad,
              busy: true,
              enabled: false,
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 104,
            height: 56,
            child: GhostButton(
              label: '停止',
              icon: Icons.stop_rounded,
              height: 56,
              color: Palette.err,
              onTap: app.stopSync,
            ),
          ),
        ],
      );
    }

    return Column(
      children: [
        GradientButton(
          label: connected ? '开始同步' : '先连上电脑',
          icon: Icons.sync_rounded,
          gradient: grad,
          enabled: connected,
          onTap: () => app.startSync(),
        ),
        const SizedBox(height: 2),
        TextButton.icon(
          onPressed: connected ? () => app.startSync(dry: true) : null,
          icon: const Icon(Icons.compare_arrows_rounded, size: 16),
          label: const Text('只预览差异，不动文件'),
          style: TextButton.styleFrom(
            foregroundColor: Palette.textDim,
            disabledForegroundColor: Palette.textMuted,
            minimumSize: const Size(0, 34),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            visualDensity: VisualDensity.compact,
            textStyle: const TextStyle(fontSize: 12.5),
          ),
        ),
      ],
    );
  }

  Widget _progressCard() {
    final moved = app.doneBytes + app.liveBytes;
    final speed = app.stats.speed;
    final pct = (app.progress * 100).round();
    final failed = app.stats.failed;

    return GlassCard(
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  app.phase.isEmpty ? '同步中…' : app.phase,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Palette.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              Text(
                '$pct%',
                style: TextStyle(
                  color: Palette.colorOf(app.settings.direction),
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          GradientProgress(
            value: app.progress,
            gradient: Palette.gradOf(app.settings.direction),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  app.currentFile.isEmpty ? '—' : app.currentFile,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Palette.textMuted, fontSize: 11),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                app.totalBytes > 0
                    ? '${humanBytes(moved)} / ${humanBytes(app.totalBytes)}'
                    : humanBytes(moved),
                style: const TextStyle(color: Palette.textDim, fontSize: 11),
              ),
              if (humanSpeed(speed).isNotEmpty) ...[
                const SizedBox(width: 8),
                Text(
                  humanSpeed(speed),
                  style: const TextStyle(color: Palette.mint, fontSize: 11),
                ),
              ],
            ],
          ),
          const SizedBox(height: 13),
          Row(
            children: [
              _stat('上行', '${app.stats.upFiles}', Palette.accent),
              const SizedBox(width: 8),
              _stat('下行', '${app.stats.downFiles}', Palette.mint),
              const SizedBox(width: 8),
              _stat('失败', '$failed', failed > 0 ? Palette.err : Palette.textDim),
              const SizedBox(width: 8),
              _stat('耗时', app.stats.elapsed > 0
                  ? '${app.stats.elapsed.toStringAsFixed(1)}s'
                  : '—', Palette.textDim),
            ],
          ),
          if (!app.running && app.finishedAt > 0) ...[
            const SizedBox(height: 11),
            Row(
              children: [
                Icon(
                  failed == 0 ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                  size: 16,
                  color: failed == 0 ? Palette.ok : Palette.err,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    failed == 0
                        ? (app.dryRun ? '预览完成，没有改动任何文件' : '同步完成，两边已经一致')
                        : '$failed 个文件失败，重新同步会自动重试',
                    style: TextStyle(
                      color: failed == 0 ? Palette.ok : Palette.err,
                      fontSize: 11.5,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _stat(String label, String value, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 9),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.035),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        child: Column(
          children: [
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(color: Palette.textMuted, fontSize: 10)),
          ],
        ),
      ),
    );
  }

  Widget _recentCard(BuildContext context) {
    final shown = app.ops.take(6).toList();
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(
            '最近的文件',
            trailing: TextButton(
              onPressed: onOpenLog,
              style: TextButton.styleFrom(
                foregroundColor: Palette.accent,
                padding: const EdgeInsets.symmetric(horizontal: 6),
                minimumSize: const Size(0, 26),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text('全部 ${app.ops.length} 项',
                  style: const TextStyle(fontSize: 11.5)),
            ),
          ),
          const SizedBox(height: 6),
          for (final op in shown) OpRow(op: op, dense: true),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ 手动连接
  Future<void> _manualDialog(BuildContext context) async {
    final controller = TextEditingController(text: app.settings.manualHost);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('手动连接电脑', style: TextStyle(fontSize: 17)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '在电脑端窗口右上角能看到这个地址，例如 192.168.1.8:37121',
              style: TextStyle(color: Palette.textDim, fontSize: 12, height: 1.4),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.text,
              decoration: InputDecoration(
                hintText: '192.168.1.8:37121',
                filled: true,
                fillColor: Colors.white.withValues(alpha: 0.04),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            style: TextButton.styleFrom(foregroundColor: Palette.textDim),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('连接'),
          ),
        ],
      ),
    );
    if (result != null && result.trim().isNotEmpty) {
      await app.connectManual(result);
    }
  }
}
