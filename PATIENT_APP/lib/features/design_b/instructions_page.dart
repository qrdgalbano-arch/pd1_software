import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';
import 'design_b_widgets.dart';

class InstructionsPage extends StatelessWidget {
  const InstructionsPage({super.key, required this.exerciseKey});

  final String exerciseKey;

  @override
  Widget build(BuildContext context) {
    final matches = designBExercises.where((e) => e.key == exerciseKey);
    if (matches.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Exercise')),
        body: const Center(child: Text('Exercise not found.')),
      );
    }
    final ex = matches.first;

    return Scaffold(
      appBar: AppBar(title: const Text('Back to Exercises')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                ex.name,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  color: QmmcColors.deepGreen,
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: InfoChip(
                      label: 'PRESCRIPTION',
                      value: ex.prescription,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: InfoChip(label: 'FREQUENCY', value: ex.frequency),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView(
                  children: [
                    SoftCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Instructions',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 8),
                          for (var i = 0; i < ex.steps.length; i++)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 4),
                              child: Text('${i + 1}. ${ex.steps[i]}'),
                            ),
                          const SizedBox(height: 8),
                          const Text(
                            'You will do the left leg first, then the right leg.',
                            style: TextStyle(
                              fontSize: 12,
                              color: QmmcColors.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    // Placeholder: replace with the real video player later.
                    Container(
                      height: 170,
                      decoration: BoxDecoration(
                        color: QmmcColors.sage,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.play_circle_outline,
                            size: 48,
                            color: QmmcColors.deepGreen,
                          ),
                          SizedBox(height: 8),
                          Text(
                            '[VIDEO DEMONSTRATION]',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              color: QmmcColors.deepGreen,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => context.push('/b/record/${ex.key}'),
                child: const Text('Start Session'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
