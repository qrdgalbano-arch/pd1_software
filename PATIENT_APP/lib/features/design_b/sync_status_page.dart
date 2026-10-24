import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';
import 'design_b_widgets.dart';

class SyncStatusPage extends ConsumerWidget {
  const SyncStatusPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(designBProvider);
    final notifier = ref.read(designBProvider.notifier);
    final pending = s.pending;
    final allSynced = pending.isEmpty;
    final last = s.lastSynced;

    return Scaffold(
      appBar: AppBar(title: const Text('Sync Status')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SoftCard(
            child: Column(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor:
                      allSynced ? QmmcColors.success : QmmcColors.gold,
                  child: Icon(
                    allSynced ? Icons.check : Icons.cloud_off,
                    color: Colors.white,
                    size: 30,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  allSynced
                      ? 'All sessions synced'
                      : '${pending.length} session(s) waiting to sync',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  last == null
                      ? 'Not synced yet'
                      : 'Last synced: ${formatShortDate(last)}, ${formatClock(last)}',
                  style: const TextStyle(color: QmmcColors.muted),
                ),
                if (!allSynced) ...[
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: s.syncing ? null : notifier.syncAll,
                    child: Text(s.syncing ? 'Syncing...' : 'Sync all'),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Pending Sessions',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (allSynced)
            const Text(
              'Nothing pending.',
              style: TextStyle(color: QmmcColors.muted),
            ),
          for (final p in pending) ...[
            SoftCard(
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          p.exerciseName,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          '${p.setsCompleted} sets · ${p.totalReps} reps · ${formatMmSs(p.durationSeconds)}',
                          style: const TextStyle(
                            fontSize: 12,
                            color: QmmcColors.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(72, 40),
                    ),
                    onPressed: s.syncing ? null : () => notifier.syncOne(p.id),
                    child: const Text('Sync'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          const SizedBox(height: 12),
          const Text(
            'Note: upload to the server is simulated in this build.',
            style: TextStyle(fontSize: 12, color: QmmcColors.muted),
          ),
        ],
      ),
    );
  }
}
