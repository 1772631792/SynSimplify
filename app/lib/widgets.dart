import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'models.dart';
import 'theme.dart';

class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.radius = 24,
    this.onTap,
    this.borderColor,
    this.gradient = Palette.cardGrad,
  });

  final Widget child;
  final EdgeInsets padding;
  final double radius;
  final VoidCallback? onTap;
  final Color? borderColor;
  final Gradient gradient;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: borderColor ?? Palette.stroke),
      ),
      padding: padding,
      child: child,
    );
    if (onTap == null) return content;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Material(
        color: Colors.transparent,
        child: InkWell(onTap: onTap, child: content),
      ),
    );
  }
}

class GradientButton extends StatelessWidget {
  const GradientButton({
    super.key,
    required this.label,
    this.icon,
    this.onTap,
    this.height = 56,
    this.enabled = true,
    this.gradient = Palette.grad,
    this.compact = false,
    this.busy = false,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final double height;
  final bool enabled;
  final Gradient gradient;
  final bool compact;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(height / 2);
    return Opacity(
      opacity: enabled ? 1 : 0.45,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: gradient,
          borderRadius: radius,
          boxShadow: [
            BoxShadow(
              color: Palette.accent.withValues(alpha: 0.32),
              blurRadius: 24,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: radius,
            onTap: enabled ? onTap : null,
            child: SizedBox(
              height: height,
              width: compact ? null : double.infinity,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: compact ? 22 : 18),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
                  children: [
                    if (busy) ...[
                      const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      ),
                      const SizedBox(width: 10),
                    ] else if (icon != null) ...[
                      Icon(icon, size: compact ? 18 : 21, color: Colors.white),
                      const SizedBox(width: 9),
                    ],
                    Flexible(
                      child: Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: compact ? 14 : 16,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.2,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class GhostButton extends StatelessWidget {
  const GhostButton({
    super.key,
    required this.label,
    this.icon,
    this.onTap,
    this.height = 46,
    this.color,
    this.enabled = true,
    this.compact = false,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final double height;
  final Color? color;
  final bool enabled;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(height / 2);
    return Opacity(
      opacity: enabled ? 1 : 0.4,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: radius,
          onTap: enabled ? onTap : null,
          child: Container(
            height: height,
            width: compact ? null : double.infinity,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.04),
              borderRadius: radius,
              border: Border.all(color: Colors.white.withValues(alpha: 0.09)),
            ),
            padding: EdgeInsets.symmetric(horizontal: compact ? 16 : 18),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 17, color: color ?? Palette.text),
                  const SizedBox(width: 7),
                ],
                Text(
                  label,
                  style: TextStyle(
                    color: color ?? Palette.text,
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill({
    super.key,
    required this.label,
    this.color = Palette.accent,
    this.icon,
    this.dense = false,
  });

  final String label;
  final Color color;
  final IconData? icon;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 8 : 11, vertical: dense ? 3 : 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(100),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: dense ? 11 : 13, color: color),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: dense ? 10.5 : 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

LinearGradient hueGradient(int hue) {
  final h = hue % 360;
  return LinearGradient(
    colors: [
      HSLColor.fromAHSL(1, h.toDouble(), 0.68, 0.64).toColor(),
      HSLColor.fromAHSL(1, (h + 46) % 360, 0.72, 0.48).toColor(),
    ],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}

class DeviceAvatar extends StatelessWidget {
  const DeviceAvatar({
    super.key,
    required this.hue,
    this.size = 46,
    this.icon = Icons.smartphone_rounded,
    this.online = false,
  });

  final int hue;
  final double size;
  final IconData? icon;
  final bool online;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: hueGradient(hue),
              border: Border.all(color: Colors.white.withValues(alpha: 0.22)),
              boxShadow: [
                BoxShadow(
                  color: hueColor(hue).withValues(alpha: 0.35),
                  blurRadius: 14,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            alignment: Alignment.center,
            child: icon == null
                ? Text(
                    initialOf(''),
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: size * 0.4,
                      fontWeight: FontWeight.w800,
                    ),
                  )
                : Icon(icon, size: size * 0.46, color: Colors.white),
          ),
          if (online)
            Positioned(
              right: -1,
              bottom: -1,
              child: Container(
                width: size * 0.28,
                height: size * 0.28,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Palette.ok,
                  border: Border.all(color: Palette.bg, width: 2),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

String initialOf(String name) {
  final text = name.trim();
  if (text.isEmpty) return '?';
  final first = String.fromCharCode(text.runes.first);
  if (RegExp(r'[a-zA-Z]').hasMatch(first)) return first.toUpperCase();
  return first;
}

class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.trailing, this.padding});

  final String text;
  final Widget? trailing;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding ?? EdgeInsets.zero,
      child: Row(
        children: [
          Text(
            text,
            style: const TextStyle(
              color: Palette.textDim,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.6,
            ),
          ),
          const Spacer(),
          ?trailing,
        ],
      ),
    );
  }
}

class StatTile extends StatelessWidget {
  const StatTile({
    super.key,
    required this.label,
    required this.value,
    this.color,
  });

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.035),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: [
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: color ?? Palette.text,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 3),
          Text(label, style: const TextStyle(color: Palette.textDim, fontSize: 11)),
        ],
      ),
    );
  }
}

/// 方向选项：左侧一条渐变色带，选中时整块泛色。
class DirectionTile extends StatelessWidget {
  const DirectionTile({
    super.key,
    required this.direction,
    required this.selected,
    required this.onTap,
    this.p2p = false,
  });

  final Direction direction;
  final bool selected;
  final VoidCallback onTap;
  final bool p2p;

  @override
  Widget build(BuildContext context) {
    final grad = Palette.gradOf(direction);
    final color = Palette.colorOf(direction);
    final icon = switch (direction) {
      Direction.push => Icons.arrow_downward_rounded,
      Direction.pull => Icons.arrow_upward_rounded,
      Direction.two => Icons.swap_vert_rounded,
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: selected
                      ? [
                          color.withValues(alpha: 0.18),
                          color.withValues(alpha: 0.05),
                        ]
                      : [
                          Colors.white.withValues(alpha: 0.035),
                          Colors.white.withValues(alpha: 0.015),
                        ],
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                ),
                borderRadius: BorderRadius.circular(18),
                border: Border.all(
                  color: selected
                      ? color.withValues(alpha: 0.55)
                      : Colors.white.withValues(alpha: 0.07),
                ),
              ),
              child: Row(
                children: [
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: 4,
                    height: 58,
                    decoration: BoxDecoration(
                      gradient: selected ? grad : null,
                      borderRadius: const BorderRadius.horizontal(
                        right: Radius.circular(4),
                      ),
                    ),
                  ),
                  const SizedBox(width: 11),
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      gradient: grad,
                      borderRadius: BorderRadius.circular(10),
                      boxShadow: selected
                          ? [
                              BoxShadow(
                                color: color.withValues(alpha: 0.3),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ]
                          : null,
                    ),
                    child: Icon(icon, size: 18, color: Colors.white),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              direction.titleFor(p2p),
                              style: const TextStyle(
                                color: Palette.text,
                                fontSize: 13.5,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            if (direction.badge.isNotEmpty) ...[
                              const SizedBox(width: 7),
                              Pill(
                                label: direction.badge,
                                color: direction == Direction.push
                                    ? Palette.accent2
                                    : Palette.mint,
                                dense: true,
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          direction.subtitleFor(p2p),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Palette.textMuted,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 14, left: 6),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      width: 18,
                      height: 18,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: selected ? color : Colors.white.withValues(alpha: 0.18),
                          width: 2,
                        ),
                      ),
                      child: selected
                          ? Center(
                              child: Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: color,
                                ),
                              ),
                            )
                          : null,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class GradientProgress extends StatelessWidget {
  const GradientProgress({
    super.key,
    required this.value,
    required this.gradient,
    this.height = 9,
  });

  final double value;
  final Gradient gradient;
  final double height;

  @override
  Widget build(BuildContext context) {
    final v = value.clamp(0.0, 1.0);
    return ClipRRect(
      borderRadius: BorderRadius.circular(height),
      child: Stack(
        children: [
          Container(
            height: height,
            color: Colors.white.withValues(alpha: 0.07),
          ),
          FractionallySizedBox(
            widthFactor: v,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              height: height,
              decoration: BoxDecoration(
                gradient: gradient,
                borderRadius: BorderRadius.circular(height),
                boxShadow: [
                  BoxShadow(
                    color: Palette.accent.withValues(alpha: 0.4),
                    blurRadius: 10,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 扫描雷达：三圈向外扩散，连上后中间亮起。
class RadarOrb extends StatefulWidget {
  const RadarOrb({
    super.key,
    required this.active,
    required this.connected,
    this.size = 190,
  });

  final bool active;
  final bool connected;
  final double size;

  @override
  State<RadarOrb> createState() => _RadarOrbState();
}

class _RadarOrbState extends State<RadarOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2400),
  );

  @override
  void initState() {
    super.initState();
    if (widget.active) _c.repeat();
  }

  @override
  void didUpdateWidget(covariant RadarOrb old) {
    super.didUpdateWidget(old);
    if (widget.active && !_c.isAnimating) {
      _c.repeat();
    } else if (!widget.active && _c.isAnimating) {
      _c.stop();
      _c.value = 0;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final size = widget.size;
    final connected = widget.connected;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          AnimatedBuilder(
            animation: _c,
            builder: (context, _) => CustomPaint(
              size: Size(size, size),
              painter: _RadarPainter(
                t: _c.value,
                animate: widget.active,
                color: connected ? Palette.accent : Palette.accent2,
              ),
            ),
          ),
          AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            width: size * 0.44,
            height: size * 0.44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: connected
                  ? Palette.grad
                  : LinearGradient(
                      colors: [
                        Palette.accent.withValues(alpha: 0.18),
                        Palette.accent2.withValues(alpha: 0.12),
                      ],
                    ),
              border: Border.all(
                color: Colors.white.withValues(alpha: connected ? 0.35 : 0.12),
              ),
              boxShadow: connected
                  ? [
                      BoxShadow(
                        color: Palette.accent.withValues(alpha: 0.45),
                        blurRadius: 32,
                        spreadRadius: 2,
                      ),
                    ]
                  : null,
            ),
            child: Icon(
              connected ? Icons.check_rounded : Icons.wifi_tethering_rounded,
              size: size * 0.19,
              color: connected ? Colors.white : Palette.accent.withValues(alpha: 0.9),
            ),
          ),
        ],
      ),
    );
  }
}

class _RadarPainter extends CustomPainter {
  _RadarPainter({required this.t, required this.animate, required this.color});

  final double t;
  final bool animate;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final maxR = size.width / 2;

    canvas.drawCircle(
      center,
      maxR * 0.86,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = Colors.white.withValues(alpha: 0.06),
    );
    canvas.drawCircle(
      center,
      maxR * 0.6,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = Colors.white.withValues(alpha: 0.045),
    );

    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..color = color;

    for (var i = 0; i < 3; i++) {
      final p = animate ? (t + i / 3) % 1.0 : (i + 1) / 3 * 0.9;
      final r = maxR * (0.34 + p * 0.62);
      stroke.color = color.withValues(alpha: animate ? (1 - p) * 0.32 : 0.08);
      canvas.drawCircle(center, r, stroke);
    }

    if (animate) {
      final sweep = Paint()
        ..shader = SweepGradient(
          colors: [color.withValues(alpha: 0.0), color.withValues(alpha: 0.16)],
          stops: const [0.72, 1.0],
          transform: GradientRotation(t * math.pi * 2),
        ).createShader(Rect.fromCircle(center: center, radius: maxR * 0.86));
      canvas.drawCircle(center, maxR * 0.86, sweep);
    }
  }

  @override
  bool shouldRepaint(covariant _RadarPainter old) =>
      old.t != t || old.animate != animate || old.color != color;
}

class ToggleRow extends StatelessWidget {
  const ToggleRow({
    super.key,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.titleColor,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final Color? titleColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  color: titleColor ?? Palette.text,
                  fontSize: 13.5,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: const TextStyle(color: Palette.textMuted, fontSize: 11.5),
              ),
            ],
          ),
        ),
        Switch(value: value, onChanged: onChanged),
      ],
    );
  }
}

class EmptyHint extends StatelessWidget {
  const EmptyHint({super.key, required this.text, this.icon = Icons.inbox_rounded});

  final String text;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 34),
      child: Column(
        children: [
          Icon(icon, size: 34, color: Colors.white.withValues(alpha: 0.12)),
          const SizedBox(height: 10),
          Text(
            text,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Palette.textMuted, fontSize: 12.5),
          ),
        ],
      ),
    );
  }
}

String shortPathText(String path, [int limit = 34]) {
  if (path.length <= limit) return path;
  return '${path.substring(0, 14)} … ${path.substring(path.length - 18)}';
}
