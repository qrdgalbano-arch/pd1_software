import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';
import 'design_b_widgets.dart';

class ExerciseListPage extends ConsumerWidget {
  const ExerciseListPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(designBProvider);

    if (s.patientId == null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: FilledButton(
              onPressed: () => context.go('/b/patient'),
              child: const Text('Enter Patient ID first'),
            ),
          ),
        ),
      );
    }

    final done = s.completedToday;
    final next = s.nextIndex;
    final pending = s.pending.length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Exercises'),
        actions: [
          IconButton(
            tooltip: 'Sync status',
            onPressed: () => context.push('/b/sync'),
            icon: Badge(
              isLabelVisible: pending > 0,
              label: Text('$pending'),
              child: const Icon(Icons.sync),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SoftCard(
            color: QmmcColors.sage,
            child: Column(
              children: [
                const Text(
                  'EXERCISES TODAY',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: QmmcColors.deepGreen,
                  ),
                ),
                const SizedBox(height: 4),
                Text(formatShortDate(DateTime.now())),
                const SizedBox(height: 2),
                Text(
                  'Patient ${s.patientId}',
                  style: const TextStyle(color: QmmcColors.muted),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          for (var i = 0; i < designBExercises.length; i++) ...[
            _ExerciseTile(
              index: i,
              exercise: designBExercises[i],
              doneAt: done[designBExercises[i].key],
              isActive: i == next,
            ),
            const SizedBox(height: 12),
          ],
          if (next >= designBExercises.length)
            const SoftCard(
              child: Text(
                'All exercises for today are done. Great work!',
                textAlign: TextAlign.center,
              ),
            ),
        ],
      ),
    );
  }
}

class _ExerciseTile extends StatelessWidget {
  const _ExerciseTile({
    required this.index,
    required this.exercise,
    required this.doneAt,
    required this.isActive,
  });

  final int index;
  final ExerciseDef exercise;
  final DateTime? doneAt;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    final isDone = doneAt != null;
    final locked = !isDone && !isActive;

    Widget trailing;
    if (isDone) {
      trailing = Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.check_circle, color: QmmcColors.success, size: 28),
          Text(
            formatClock(doneAt!),
            style: const TextStyle(fontSize: 11, color: QmmcColors.muted),
          ),
        ],
      );
    } else if (isActive) {
      trailing = FilledButton(
        style: FilledButton.styleFrom(minimumSize: const Size(92, 42)),
        onPressed: () => context.push('/b/instructions/${exercise.key}'),
        child: const Text('Record'),
      );
    } else {
      trailing = const Icon(
        Icons.remove_circle_outline,
        color: QmmcColors.muted,
        size: 28,
      );
    }

    return Opacity(
      opacity: locked ? 0.6 : 1,
      child: SoftCard(
        child: Row(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor:
                  isActive ? QmmcColors.deepGreen : QmmcColors.sage,
              child: Text(
                '${index + 1}',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: isActive ? Colors.white : QmmcColors.deepGreen,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    exercise.prescription,
                    style: const TextStyle(
                      fontSize: 12,
                      color: QmmcColors.muted,
                    ),
                  ),
                  if (locked)
                    const Text(
                      'Locked: finish the previous exercise first',
                      style: TextStyle(fontSize: 11, color: QmmcColors.muted),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            trailing,
          ],
        ),
      ),
    );
  }
}
