import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../auth/domain/auth_controller.dart';
import '../auth/domain/auth_user.dart';
import '../prescriptions/domain/prescriptions_controller.dart';

class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final user = authState.valueOrNull;
    final prescriptions = ref.watch(prescriptionsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Exercise Plan'),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: authState.isLoading
                ? null
                : () => ref.read(authControllerProvider.notifier).signOut(),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            _greeting(user),
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          Text(
            'Your exercise plan is ready when you are.',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 28),
          prescriptions.when(
            loading: () => const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: CircularProgressIndicator(),
              ),
            ),
            error: (error, _) => Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Unable to load your exercise plan.',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Please check your connection and try again.',
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton(
                      onPressed: () => ref.invalidate(prescriptionsProvider),
                      child: const Text('Try again'),
                    ),
                  ],
                ),
              ),
            ),
            data: (items) {
              if (items.isEmpty) {
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Text(
                      'You do not have an active exercise plan yet.',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                );
              }

              final firstPrescription = items.first;

              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Today’s exercise',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        firstPrescription.exercise.name,
                        style: const TextStyle(fontSize: 22),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        firstPrescription.exercise.description,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '${firstPrescription.repetitionsTarget} repetitions · '
                        'Up to ${firstPrescription.formattedDuration}',
                      ),
                      const SizedBox(height: 20),
                      SizedBox(
                        width: double.infinity,
                        height: 56,
                        child: FilledButton(
                          onPressed: () => context.go('/prescriptions'),
                          child: const Text(
                            'View exercise plan',
                            style: TextStyle(fontSize: 18),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  String _greeting(AuthUser? user) {
    if (user == null || user.fullName.trim().isEmpty) {
      return 'Good day';
    }

    return 'Good day, ${user.fullName}';
  }
}
