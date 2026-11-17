import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/src/app/providers.dart';
import 'package:mobile/src/app/session_controller.dart';
import 'package:mobile/src/data/api/api_client.dart';
import 'package:mobile/src/features/auth/login_screen.dart';

class _FakeAuthController extends AuthController {
  @override
  AuthState build() => const AuthState(ready: true);
}

void main() {
  test(
    'offline credential verifier is salted and uses credential mode',
    () async {
      final passwordVerifier = await deriveOfflineCredentialVerifier(
        username: 'kasir',
        credential: '654321',
        salt: 'device-specific-salt',
        isPin: false,
      );
      final sameVerifier = await deriveOfflineCredentialVerifier(
        username: 'KASIR',
        credential: '654321',
        salt: 'device-specific-salt',
        isPin: false,
      );
      final pinVerifier = await deriveOfflineCredentialVerifier(
        username: 'kasir',
        credential: '654321',
        salt: 'device-specific-salt',
        isPin: true,
      );
      final otherSaltVerifier = await deriveOfflineCredentialVerifier(
        username: 'kasir',
        credential: '654321',
        salt: 'another-device-salt',
        isPin: false,
      );

      expect(sameVerifier, passwordVerifier);
      expect(pinVerifier, isNot(passwordVerifier));
      expect(otherSaltVerifier, isNot(passwordVerifier));
    },
  );

  test('offline session validity is limited to seven days', () {
    final now = DateTime.utc(2026, 11, 17, 7);

    expect(
      isOfflineSessionValid(now.subtract(const Duration(days: 7)), now: now),
      isTrue,
    );
    expect(
      isOfflineSessionValid(
        now.subtract(const Duration(days: 7, seconds: 1)),
        now: now,
      ),
      isFalse,
    );
    expect(
      isOfflineSessionValid(now.add(const Duration(seconds: 1)), now: now),
      isFalse,
    );
  });

  testWidgets('PIN mode uses cashier account and an in-app numeric keypad', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(
            ApiClient(baseUrl: 'https://pos.example.com/api/v1'),
          ),
          authControllerProvider.overrideWith(_FakeAuthController.new),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );

    await tester.tap(find.text('PIN Kasir'));
    await tester.pumpAndSettle();

    expect(find.text('Username kasir'), findsOneWidget);
    expect(find.text('Hapus semua'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('9'), findsOneWidget);
  });
}
