import 'package:flutter/material.dart';

import '../app_state.dart';
import '../models.dart';
import '../op_row.dart';
import '../theme.dart';
import '../widgets.dart';

class LogPage extends StatefulWidget {
  const LogPage({super.key, required this.app});

  final AppState app;

  @override
  State<LogPage> createState() => _LogPageState();
}

class _LogPageState extends State<LogPage> {
  int _filter = 0;

  static const _filters = ['全部', '上行', '下行', '跳过', '失败'];

  List<SyncOp> get _visible {
    final ops = widget.app.ops;
    switch (_filter) {
      case 1:
        return ops.where((o) => o.kind == OpKind.push).toList();
      case 2:
        return ops.where((o) => o.kind == OpKind.pull).toList();
      case 3:
        return ops
            .where((o) => o.kind == OpKind.skip || o.kind == OpKind.same)
            .toList();
      case 4:
        return ops.where((o) => o.status == OpStatus.failed).toList();
      default:
        return ops;
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = widget.app;
    return SafeArea(
      bottom: false,
      child: ListenableBuilder(
        listenable: app,
        builder: (context, _) {
          final list = _visible;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                child: Row(
                  children: [
                    const Text(
                      '同步记录',
                      style: TextStyle(
                        color: Palette.text,
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Pill(
                      label: '${app.ops.length} 项',
                      color: app.running ? Palette.accent : Palette.textDim,
                      dense: true,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Text(
                  app.running
                      ? (app.phase.isEmpty ? '正在同步…' : app.phase)
                      : app.finishedAt == 0
                          ? '还没有同步过：回到「同步」页，选好文件夹点开始'
                          : '上次同步：上行 ${app.stats.upFiles} · 下行 ${app.stats.downFiles} · '
                              '失败 ${app.stats.failed} · ${app.stats.elapsed.toStringAsFixed(1)}s',
                  maxLines: 2,
                  style: const TextStyle(color: Palette.textMuted, fontSize: 11.5, height: 1.4),
                ),
              ),
              const SizedBox(height: 12),
              SizedBox(
                height: 32,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  itemCount: _filters.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 8),
                  itemBuilder: (context, i) {
                    final selected = _filter == i;
                    return GestureDetector(
                      onTap: () => setState(() => _filter = i),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          gradient: selected ? Palette.grad : null,
                          color: selected ? null : Colors.white.withValues(alpha: 0.045),
                          borderRadius: BorderRadius.circular(100),
                          border: Border.all(
                            color: selected
                                ? Colors.transparent
                                : Colors.white.withValues(alpha: 0.07),
                          ),
                        ),
                        child: Text(
                          _filters[i],
                          style: TextStyle(
                            color: selected ? Colors.white : Palette.textDim,
                            fontSize: 12,
                            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 14),
              Expanded(
                child: list.isEmpty
                    ? const Center(
                        child: EmptyHint(
                          text: '这里会列出每一个文件的状态\n方向、大小、耗时都写在上面',
                          icon: Icons.receipt_long_rounded,
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.fromLTRB(18, 0, 18, 120),
                        itemCount: list.length,
                        itemBuilder: (context, i) {
                          final op = list[i];
                          return Container(
                            margin: const EdgeInsets.only(bottom: 6),
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.032),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.05),
                              ),
                            ),
                            child: OpRow(op: op),
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
