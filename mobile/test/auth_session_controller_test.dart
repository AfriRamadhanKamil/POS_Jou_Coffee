import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/src/app/providers.dart';
import 'package:mobile/src/data/api/api_client.dart';
import 'package:mobile/src/data/local/app_database.dart';
import 'package:drift/native.dart';

class _MemorySecureStorage extends FlutterSecureStorage {
  final Map<String, String> values = {};

  @override
  Future<String?> read({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async => values[key];

  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    values.remove(key);
  }
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'https://pos.example.com/api/v1');

  bool networkUnavailable = false;

  @override
  Future<Map<String, dynamic>> postData(
    String path, {
    Map<String, Object?>? body,
  }) async {
    if (networkUnavailable) {
      throw DioException(requestOptions: RequestOptions(path: path));
    }
    return {
      'access_token': 'access-token',
      'refresh_token': 'refresh-token',
      'user': {
        'id': 'user-id',
        'username': body?['username'],
        'name': 'Kasir Test',
        'role': 'kasir',
      },
    };
  }
}

void main() {
  test('cashier can authenticate offline for up to seven days', () async {
    final storage = _MemorySecureStorage();
    final api = _FakeApiClient();
    final database = AppDatabase(NativeDatabase.memory());
    final container = ProviderContainer(
      overrides: [
        secureStorageProvider.overrideWithValue(storage),
        apiClientProvider.overrideWithValue(api),
        appDatabaseProvider.overrideWithValue(database),
      ],
    );
    addTearDown(() async {
      container.dispose();
      await database.close();
    });
    final controller = container.read(authControllerProvider.notifier);
    await controller.restore();
    await controller.login('kasir', '654321', isPin: true);

    api.networkUnavailable = true;
    await controller.login('kasir', '654321', isPin: true);

    expect(container.read(authControllerProvider).session?.isOffline, isTrue);
    expect(jsonDecode(storage.values['jou_offline_auth']!)['is_pin'], isTrue);

    await database.cacheCatalog('{"categories":[]}');
    await database.enqueueOrder('pending-1', '{"idempotency_key":"pending-1"}');
    await controller.logout();

    expect(container.read(authControllerProvider).session, isNull);
    expect(storage.values.containsKey('jou_offline_auth'), isFalse);
    expect(await database.readCachedCatalog(), isNull);
    expect(
      (await database.getPendingOrders()).single.idempotencyKey,
      'pending-1',
    );
  });
}
