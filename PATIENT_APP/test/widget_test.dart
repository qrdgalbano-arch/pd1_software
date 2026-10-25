import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qmmc_pd1_mobile/app/qmmc_app.dart';
import 'package:qmmc_pd1_mobile/features/auth/domain/auth_controller.dart';
import 'package:qmmc_pd1_mobile/features/auth/domain/auth_user.dart';

void main() {
  testWidgets('shows the login screen when unauthenticated', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(
            () => _UnauthenticatedAuthController(),
          ),
        ],
        child: const QmmcApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('QMMC PD1'), findsOneWidget);
    expect(find.text('Email address'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });
}

class _UnauthenticatedAuthController extends AuthController {
  @override
  Future<AuthUser?> build() async {
    return null;
  }
}