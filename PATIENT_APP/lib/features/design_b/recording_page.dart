import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';
import 'design_b_widgets.dart';
import 'leg_twin_painter.dart';

/// Recording screen. Joint angles are SIMULATED (sine wave) for this build.
/// Order: all sets on the left leg, then all sets on the right leg.
class RecordingPage extends ConsumerStatefulWidget {
  const RecordingPage({super.key, required this.exerciseKey});

  final String exerciseKey;

  @override
  ConsumerState<RecordingPage> createState() => _RecordingPageState();
}

class _RecordingPageState extends ConsumerState<RecordingPage> {
  static const Duration _tick = Duration(milliseconds: 50);
  static const double _period = 4.0;

  late final ExerciseDef _ex;
  Timer? _timer;

  LegSide _side = LegSide.left;
  int _set = 1;
  int _reps = 0;
  int _totalReps = 0;
  int _setsDone = 0;
  double _cycle = 0;
  double _elapsed = 0;
  bool _paused = false;
  bool _prompting = false;

  @override
  void initState() {
    super.initState();
    _ex = designBExercises.firstWhere(
      (e) => e.key == widget.exerciseKey,
      orElse: () => designBExercises.first,
    );
    _timer = Timer.periodic(_tick, (_) => _onTick());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  double get _angle {
    final frac = _cycle / _period;
    final peak = _ex.targetDeg * (1.0 + 0.04 * math.sin(_reps * 1.7));
    return peak * (0.5 - 0.5 * math.cos(2 * math.pi * frac));
  }

  bool get _reached => _angle >= _ex.targetDeg * 0.9;

  void _onTick() {
    if (_paused || _prompting || !mounted) return;
    const dt = 0.05;
    _elapsed += dt;
    _cycle += dt;
    if (_cycle >= _period) {
      _cycle -= _period;
      _reps++;
      _totalReps++;
      if (_reps >= _ex.reps) {
        _handleSetComplete();
        return;
      }
    }
    setState(() {});
  }

  Future<void> _handleSetComplete() async {
    final lastSetOfSide = _set >= _ex.sets;
    final isFinal = lastSetOfSide && _side == LegSide.right;

    setState(() {
      _setsDone++;
      _prompting = true;
    });

    if (isFinal) {
      _finish(completed: true);
      return;
    }

    final String title;
    final String body;
    final String button;
    if (lastSetOfSide) {
      title = '${_side.label} Leg Complete!';
      body = 'Rest, then switch to your right leg.';
      button = 'Start Right Leg';
    } else {
      title = 'Set $_set Complete!';
      body = 'Rest before beginning your next set.';
      button = 'Start Set ${_set + 1}';
    }

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => Dialog(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircleAvatar(
                radius: 24,
                backgroundColor: QmmcColors.mint,
                child: Icon(Icons.check, color: QmmcColors.success),
              ),
              const SizedBox(height: 16),
              Text(
                title,
                textAlign: TextAlign.center,
                style: Theme.of(ctx)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text('${_ex.reps} / ${_ex.reps} reps on the ${_side.label.toLowerCase()} leg'),
              const SizedBox(height: 4),
              Text(body, textAlign: TextAlign.center),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: Text(button),
              ),
            ],
          ),
        ),
      ),
    );

    if (!mounted) return;
    setState(() {
      if (lastSetOfSide) {
        _side = LegSide.right;
        _set = 1;
      } else {
        _set++;
      }
      _reps = 0;
      _cycle = 0;
      _prompting = false;
    });
  }

  Future<void> _confirmEnd() async {
    final wasPaused = _paused;
    setState(() => _paused = true);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('End session?'),
        content: const Text(
          'Your progress will be saved, but this exercise will stay marked as not done.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep going'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('End session'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    if (ok == true) {
      _finish(completed: false);
    } else {
      setState(() => _paused = wasPaused);
    }
  }

  void _finish({required bool completed}) {
    _timer?.cancel();
    final patientId = ref.read(designBProvider).patientId ?? 'UNKNOWN';
    final record = SessionRecord(
      id: 'sessB-${DateTime.now().microsecondsSinceEpoch}',
      patientId: patientId,
      exerciseKey: _ex.key,
      exerciseName: _ex.name,
      setsCompleted: _setsDone,
      setsTotal: _ex.sets * 2,
      totalReps: _totalReps,
      repsTotal: _ex.reps * _ex.sets * 2,
      durationSeconds: _elapsed.round(),
      recordedAt: DateTime.now(),
      completed: completed,
    );
    ref.read(designBProvider.notifier).completeSession(record);
    context.go('/b/complete');
  }

  @override
  Widget build(BuildContext context) {
    final angle = _angle;
    final reached = _reached;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Text(_ex.name),
        actions: [
          IconButton(
            tooltip: 'End session',
            icon: const Icon(Icons.close),
            onPressed: _confirmEnd,
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: InfoChip(
                      label: 'AFFECTED LEG',
                      value: '${_side.label} leg',
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: InfoChip(
                      label: 'SET',
                      value: '$_set of ${_ex.sets}',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(
                child: SoftCard(
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            formatMmSs(_elapsed.round()),
                            style: const TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                              color: QmmcColors.deepGreen,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: QmmcColors.gold,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Text(
                              'SIMULATED DATA',
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w800,
                                color: QmmcColors.ink,
                              ),
                            ),
                          ),
                        ],
                      ),
                      Expanded(
                        child: CustomPaint(
                          size: Size.infinite,
                          painter: LegTwinPainter(
                            exerciseKey: _ex.key,
                            angleDeg: angle,
                            targetDeg: _ex.targetDeg,
                            side: _side,
                            reached: reached,
                          ),
                        ),
                      ),
                      Text(
                        '${angle.round()}°',
                        style: const TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      Text(
                        reached ? 'Target reached' : 'Keep moving',
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          color: reached ? QmmcColors.success : QmmcColors.muted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Rep $_reps / ${_ex.reps}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(height: 6),
              LinearProgressIndicator(
                value: _reps / _ex.reps,
                minHeight: 8,
                color: QmmcColors.success,
                backgroundColor: QmmcColors.sage,
                borderRadius: BorderRadius.circular(4),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => setState(() => _paused = !_paused),
                      child: Text(_paused ? 'Resume' : 'Pause'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: _confirmEnd,
                      child: const Text('End Session'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
