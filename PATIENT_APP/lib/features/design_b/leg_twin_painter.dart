import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';

class _Pose {
  const _Pose(this.hip, this.knee, this.ankle, this.toe);
  final Offset hip;
  final Offset knee;
  final Offset ankle;
  final Offset toe;
}

/// Side-view digital twin of ONE leg (hip, knee, ankle, foot).
/// The faint ghost leg shows the target position.
class LegTwinPainter extends CustomPainter {
  LegTwinPainter({
    required this.exerciseKey,
    required this.angleDeg,
    required this.targetDeg,
    required this.side,
    required this.reached,
  });

  final String exerciseKey;
  final double angleDeg;
  final double targetDeg;
  final LegSide side;
  final bool reached;

  _Pose _pose(Size size, double deg) {
    final dir = side == LegSide.left ? 1.0 : -1.0;
    final hip = Offset(
      size.width * (dir > 0 ? 0.14 : 0.86),
      size.height * 0.60,
    );
    final thigh = size.width * 0.32;
    final shank = size.width * 0.30;
    final foot = size.width * 0.09;
    final r = deg * math.pi / 180;

    final flat = Offset(dir, 0);
    Offset perp(Offset d) => Offset(dir * d.dy, -dir * d.dx);
    Offset unit(double rad) => Offset(dir * math.cos(rad), -math.sin(rad));

    if (exerciseKey == 'straight_leg_raise') {
      final d = unit(r);
      final knee = hip + d * thigh;
      final ankle = knee + d * shank;
      return _Pose(hip, knee, ankle, ankle + perp(d) * foot);
    }
    if (exerciseKey == 'prone_leg_flexion') {
      final knee = hip + flat * thigh;
      final d = unit(r);
      final ankle = knee + d * shank;
      return _Pose(hip, knee, ankle, ankle + perp(d) * foot);
    }
    // Ankle pump: leg flat, foot rotates about the ankle.
    final knee = hip + flat * thigh;
    final ankle = knee + flat * shank;
    final footDir = perp(flat) * math.cos(r) + flat * math.sin(r);
    return _Pose(hip, knee, ankle, ankle + footDir * foot);
  }

  void _line(Canvas canvas, Offset a, Offset b, Paint paint) {
    canvas.drawLine(a, b, paint);
  }

  void _label(Canvas canvas, String text, Offset at) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(fontSize: 11, color: QmmcColors.muted),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(at.dx - tp.width / 2, at.dy));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final hipRef = _pose(size, 0).hip;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(8, hipRef.dy + 26, size.width - 16, 10),
        const Radius.circular(5),
      ),
      Paint()..color = QmmcColors.sage,
    );

    final ghost = _pose(size, targetDeg);
    final ghostPaint = Paint()
      ..color = QmmcColors.sage
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    _line(canvas, ghost.hip, ghost.knee, ghostPaint);
    _line(canvas, ghost.knee, ghost.ankle, ghostPaint);
    _line(canvas, ghost.ankle, ghost.toe, ghostPaint);

    final live = _pose(size, angleDeg);
    final bone = Paint()
      ..color = QmmcColors.deepGreen
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;
    _line(canvas, live.hip, live.knee, bone);
    _line(canvas, live.knee, live.ankle, bone);
    _line(canvas, live.ankle, live.toe, bone..strokeWidth = 7);

    final jointColor = reached ? QmmcColors.success : QmmcColors.gold;
    for (final p in [live.hip, live.knee, live.ankle]) {
      canvas.drawCircle(p, 11, Paint()..color = Colors.white);
      canvas.drawCircle(p, 8, Paint()..color = jointColor);
    }

    _label(canvas, 'hip', live.hip + const Offset(0, 16));
    _label(canvas, 'knee', live.knee + const Offset(0, 16));
    _label(canvas, 'ankle', live.ankle + const Offset(0, 16));
  }

  @override
  bool shouldRepaint(covariant LegTwinPainter old) =>
      old.angleDeg != angleDeg ||
      old.targetDeg != targetDeg ||
      old.side != side ||
      old.reached != reached ||
      old.exerciseKey != exerciseKey;
}
