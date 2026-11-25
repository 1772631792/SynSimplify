import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../theme.dart';
import '../widgets.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.app});

  final AppState app;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _manual =
      TextEditingController(text: widget.app.settings.manualHost);

  AppState get app => widget.app;

  @override
  void dispose() {
    _manual.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: ListenableBuilder(
        listenable: app,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 120),
            children: [
              const Text(
                '设置',
                style: TextStyle(
                  color: Palette.text,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 14),
              _deviceCard(context),
              const SizedBox(height: 12),
              _folderCard(context),
              const SizedBox(height: 12),
              _connectionCard(context),
              const SizedBox(height: 12),
              _aboutCard(),
            ],
          );
        },
      ),
    );
  }

  Widget _card({required String title, required List<Widget> children}) {
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(title),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }

  Widget _row({
    required String label,
    required String value,
    Widget? trailing,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(color: Palette.textDim, fontSize: 11)),
                const SizedBox(height: 3),
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Palette.text,
                    fontSize: 12.5,
                    height: 1.35,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 10), trailing],
        ],
      ),
    );
  }

  Widget _deviceCard(BuildContext context) {
    return _card(
      title: '这台手机',
      children: [
        _row(
          label: '设备名',
          value: app.settings.deviceName,
          trailing: GhostButton(
            label: '修改',
            height: 34,
            compact: true,
            onTap: () => _editName(context),
          ),
        ),
        Row(
          children: [
            Icon(
              app.serverReady ? Icons.check_circle_rounded : Icons.warning_amber_rounded,
              size: 15,
              color: app.serverReady ? Palette.ok : Palette.warn,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                app.serverReady
                    ? '${app.settings.p2pMode ? '另一台手机' : '电脑'}也能主动把文件推过来（端口 ${app.notice.contains('占用') ? '异常' : '37131'}）'
                    : '手机端服务没起来，对方无法主动推送',
                style: TextStyle(
                  color: app.serverReady ? Palette.textMuted : Palette.warn,
                  fontSize: 11,
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _folderCard(BuildContext context) {
    return _card(
      title: '手机文件夹',
      children: [
        Text(
          app.localRoot,
          style: const TextStyle(
            color: Palette.text,
            fontSize: 12.5,
            height: 1.4,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Icon(
              app.allFiles ? Icons.verified_rounded : Icons.lock_outline_rounded,
              size: 14,
              color: app.allFiles ? Palette.ok : Palette.warn,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                app.allFiles
                    ? '已获得「所有文件访问」，可以同步任意文件夹'
                    : '未授权，只能同步 App 自己的目录',
                style: TextStyle(
                  color: app.allFiles ? Palette.textMuted : Palette.warn,
                  fontSize: 11,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: GhostButton(
                label: '选择文件夹',
                icon: Icons.folder_open_rounded,
                height: 42,
                compact: false,
                onTap: app.pickLocalRoot,
              ),
            ),
            const SizedBox(width: 9),
            GhostButton(
              label: '默认',
              height: 42,
              compact: true,
              onTap: app.useDefaultRoot,
            ),
          ],
        ),
        if (!app.allFiles) ...[
          const SizedBox(height: 9),
          SizedBox(
            width: double.infinity,
            child: GradientButton(
              label: '去授予「所有文件访问」',
              icon: Icons.admin_panel_settings_rounded,
              height: 44,
              gradient: const LinearGradient(
                colors: [Palette.warn, Color(0xFFFF7A45)],
              ),
              onTap: app.requestAllFiles,
            ),
          ),
        ],
      ],
    );
  }

  Widget _connectionCard(BuildContext context) {
    final peer = app.peer;
    return _card(
      title: '连接',
      children: [
        _row(
          label: app.settings.p2pMode ? '当前手机' : '当前电脑',
          value: peer == null
              ? '还没连上'
              : '${peer.name} · ${peer.ip}:${peer.port}',
          trailing: peer == null
              ? null
              : GhostButton(
                  label: '换一台',
                  height: 34,
                  compact: true,
                  onTap: app.switchPeer,
                ),
        ),
        Text(
          peer?.root.isNotEmpty == true
              ? '${app.settings.p2pMode ? '对方手机' : '电脑'}文件夹：${peer!.root}'
              : '${app.settings.p2pMode ? '对方手机' : '电脑'}文件夹：连上后显示',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Palette.textMuted, fontSize: 11, height: 1.4),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _manual,
          keyboardType: TextInputType.text,
          style: const TextStyle(fontSize: 13, color: Palette.text),
          decoration: InputDecoration(
            isDense: true,
            hintText: app.settings.p2pMode
                ? '手动填另一台手机地址，例如 192.168.1.9:37131'
                : '手动填电脑地址，例如 192.168.1.8:37121',
            hintStyle: const TextStyle(color: Palette.textMuted, fontSize: 12),
            filled: true,
            fillColor: Colors.white.withValues(alpha: 0.04),
            contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        const SizedBox(height: 9),
        Row(
          children: [
            Expanded(
              child: GhostButton(
                label: '重新搜索',
                icon: Icons.refresh_rounded,
                height: 42,
                onTap: () => app.startDiscovery(),
              ),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: GradientButton(
                label: '连接',
                icon: Icons.link_rounded,
                height: 42,
                onTap: () async {
                  final messenger = ScaffoldMessenger.of(context);
                  await app.connectManual(_manual.text);
                  messenger.showSnackBar(
                    SnackBar(
                      content: Text(app.connected
                          ? '已连接 ${app.peer?.name}'
                          : (app.notice.isEmpty ? '连接失败' : app.notice)),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _aboutCard() {
    return _card(
      title: '关于',
      children: [
        const Text(
          'SynSimplify 1.0.0 · 协议 v1\n'
          '手机和电脑（或另一台手机）在同一个 WiFi 里直连，文件不经过任何服务器。\n'
          '手机互传只需一端开启，网内只有两台手机时自动连上。\n'
          '端口：发现 37120 / 电脑 37121 / 手机 37131',
          style: TextStyle(color: Palette.textMuted, fontSize: 11.5, height: 1.6),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            const Icon(Icons.lightbulb_outline_rounded, size: 15, color: Palette.accent),
            const SizedBox(width: 6),
            Text(
              app.settings.p2pMode
                  ? '推荐「双向同步」：两台手机取新、缺的补齐'
                  : '推荐「电脑 → 手机」：电脑上整理好，手机一开就同步',
              style: const TextStyle(color: Palette.textDim, fontSize: 11),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _editName(BuildContext context) async {
    final controller = TextEditingController(text: app.settings.deviceName);
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('设备名', style: TextStyle(fontSize: 17)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              app.settings.p2pMode
                  ? '这台手机会以这个名字出现在另一台手机上'
                  : '这台手机会以这个名字出现在电脑上',
              style: const TextStyle(color: Palette.textDim, fontSize: 12),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              autofocus: true,
              maxLength: 24,
              inputFormatters: [LengthLimitingTextInputFormatter(24)],
              decoration: InputDecoration(
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
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (name != null && name.trim().isNotEmpty) {
      app.setDeviceName(name);
    }
  }
}
