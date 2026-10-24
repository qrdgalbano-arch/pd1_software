import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/theme/qmmc_theme.dart';
import '../features/auth/domain/auth_controller.dart';
import '../features/auth/login_page.dart';
import '../features/design_b/exercise_list_page.dart';
import '../features/design_b/instructions_page.dart';
import '../features/design_b/patient_id_page.dart';
import '../features/design_b/recording_page.dart';
import '../features/design_b/session_complete_page.dart';
import '../features/design_b/sync_status_page.dart';
import '../features/home/home_page.dart';
import '../features/prescriptions/prescriptions_page.dart';

class QmmcApp extends ConsumerWidget {
  const QmmcApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);

    final router = GoRouter(
      // Design B flow starts at Patient ID. The original /login flow is kept.
      initialLocation: '/b/patient',
      redirect: (context, state) {
        // Design B screens do not use the login redirect.
        if (state.matchedLocation.startsWith('/b/')) {
          return null;
        }

        final isLoading = authState.isLoading;
        final isAuthenticated = authState.valueOrNull != null;
        final isOnLogin = state.matchedLocation == '/login';

        if (isLoading) {
          return isOnLogin ? null : '/login';
        }

        if (!isAuthenticated) {
          return isOnLogin ? null : '/login';
        }

        if (isOnLogin) {
          return '/home';
        }

        return null;
      },
      routes: [
        GoRoute(
          path: '/login',
          builder: (context, state) => const LoginPage(),
        ),
        GoRoute(
          path: '/home',
          builder: (context, state) => const HomePage(),
        ),
        GoRoute(
          path: '/prescriptions',
          builder: (context, state) => const PrescriptionsPage(),
        ),
        GoRoute(
          path: '/b/patient',
          builder: (context, state) => const PatientIdPage(),
        ),
        GoRoute(
          path: '/b/exercises',
          builder: (context, state) => const ExerciseListPage(),
        ),
        GoRoute(
          path: '/b/instructions/:key',
          builder: (context, state) =>
              InstructionsPage(exerciseKey: state.pathParameters['key'] ?? ''),
        ),
        GoRoute(
          path: '/b/record/:key',
          builder: (context, state) =>
              RecordingPage(exerciseKey: state.pathParameters['key'] ?? ''),
        ),
        GoRoute(
          path: '/b/complete',
          builder: (context, state) => const SessionCompletePage(),
        ),
        GoRoute(
          path: '/b/sync',
          builder: (context, state) => const SyncStatusPage(),
        ),
      ],
    );

    return MaterialApp.router(
      title: 'QMMC PD1',
      theme: buildQmmcTheme(),
      routerConfig: router,
    );
  }
}
