import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';
import 'design_b_widgets.dart';

class SessionCompletePage extends ConsumerWidget {
  const SessionCompletePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final r = ref.watch(designBProvider).lastSession;

    if (r == null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: FilledButton(
              onPressed: () => context.go('/b/exercises'),
              child: const Text('Back to Exercises'),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Text(r.exerciseName),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Expanded(
                child: ListView(
                  children: [
                    const SizedBox(height: 24),
                    Center(
                      child: CircleAvatar(
                        radius: 36,
                        backgroundColor:
                            r.completed ? QmmcColors.success : QmmcColors.gold,
                        child: Icon(
                          r.completed ? Icons.check : Icons.pause,
                          size: 40,
                          color: Colors.white,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      r.completed ? 'Session Complete!' : 'Session Ended Early',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: QmmcColors.deepGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Session saved locally. It will automatically upload once an internet connection is established.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 20),
                    SoftCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'SESSION SUMMARY',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                              color: QmmcColors.muted,
                            ),
                          ),
                          const SizedBox(height: 8),
                          _Row(
                            'Sets Completed',
                            '${r.setsCompleted} / ${r.setsTotal} sets',
                          ),
                          _Row(
                            'Total Repetitions',
                            '${r.totalReps} / ${r.repsTotal} reps',
                          ),
                          _Row('Duration', formatMmSs(r.durationSeconds)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              FilledButton(
                onPressed: () => context.go('/b/exercises'),
                child: const Text('Finish Session'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
