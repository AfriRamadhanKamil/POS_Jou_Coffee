import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../data/api/api_client.dart';
import '../data/local/app_database.dart';
import '../data/pos_repository.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final appDatabaseProvider = Provider<AppDatabase>((ref) {
  final database = AppDatabase();
  ref.onDispose(database.close);
  return database;
});

final posRepositoryProvider = Provider<PosRepository>(
  (ref) => PosRepository(
    ref.watch(apiClientProvider),
    ref.watch(appDatabaseProvider),
  ),
);

final secureStorageProvider = Provider<FlutterSecureStorage>(
  (ref) => const FlutterSecureStorage(),
);
