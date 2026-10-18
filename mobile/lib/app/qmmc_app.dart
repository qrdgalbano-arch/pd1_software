import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/domain/auth_controller.dart';
import '../features/auth/login_page.dart';
import '../features/home/home_page.dart';
import '../features/prescriptions/prescriptions_page.dart';

class QmmcApp extends ConsumerWidget {
  const QmmcApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);

    final router = GoRouter(
      initialLocation: '/login',
      redirect: (context, state) {
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
      ],
    );

    return MaterialApp.router(
      title: 'QMMC PD1',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0B5D8C),
        ),
        useMaterial3: true,
      ),
      routerConfig: router,
    );
  }
}