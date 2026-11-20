import 'package:flutter/material.dart';

import 'models.dart';
import 'theme.dart';

class OpRow extends StatelessWidget {
  const OpRow({super.key, required this.op, this.dense = false});

  final SyncOp op;
  final bool dense;

  Color get _kindColor => switch (op.kind) {
        OpKind.push => Palette.accent,
        OpKind.pull => Palette.mint,
        OpKind.delLocal || OpKind.delRemote => Palette.err,
        OpKind.skip => Palette.warn,
        OpKind.same => Palette.textMuted,
        _ => Palette.textDim,
      };

  IconData get _icon => switch (op.kind) {
        OpKind.push => Icons.arrow_downward_rounded,
        OpKind.pull => Icons.arrow_upward_rounded,
        OpKind.mkdirLocal || OpKind.mkdirRemote => Icons.folder_rounded,
        OpKind.delLocal || OpKind.delRemote => Icons.delete_outline_rounded,
        OpKind.skip => Icons.report_gmailerrorred_rounded,
        OpKind.same => Icons.check_circle_outline_rounded,
      };

  Color get _statusColor => switch (op.status) {
        OpStatus.pending => Palette.textMuted,
        OpStatus.running => Palette.accent,
        OpStatus.done => Palette.ok,
        OpStatus.failed => Palette.err,
        OpStatus.skipped => Palette.warn,
      };

  @override
  Widget build(BuildContext context) {
    final color = _kindColor;
    return Padding(
      padding: EdgeInsets.symmetric(vertical: dense ? 6 : 8, horizontal: 2),
      child: Row(
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(_icon, size: 15, color: color),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  op.path,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Palette.text,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Row(
                  children: [
                    if (op.status == OpStatus.running)
                      Padding(
                        padding: const EdgeInsets.only(right: 5),
                        child: SizedBox(
                          width: 9,
                          height: 9,
                          child: CircularProgressIndicator(
                            strokeWidth: 1.6,
                            value: op.progress > 0 ? op.progress : null,
                            backgroundColor: Colors.white.withValues(alpha: 0.12),
                            valueColor: const AlwaysStoppedAnimation<Color>(Palette.accent),
                          ),
                        ),
                      ),
                    Flexible(
                      child: Text(
                        op.statusText,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(color: _statusColor, fontSize: 11),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          if (op.kind.movesFile)
            Text(
              humanBytes(op.size),
              style: const TextStyle(color: Palette.textDim, fontSize: 11),
            ),
        ],
      ),
    );
  }
}
