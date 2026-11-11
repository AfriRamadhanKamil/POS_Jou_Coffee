import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:workmanager/workmanager.dart';

import '../data/api/api_client.dart';
import '../data/local/app_database.dart';
import '../data/pos_repository.dart';

@pragma('vm:entry-point')
void backgroundSyncDispatcher() {
  Workmanager().executeTask((taskName, inputData) async {
    if (taskName != 'syncPendingOrders') return true;

    final database = AppDatabase();
    try {
      const storage = FlutterSecureStorage();
      final sessionJson = await storage.read(key: 'jou_session');
      if (sessionJson == null) return true;
      final session = jsonDecode(sessionJson) as Map<String, dynamic>;
      final accessToken = session['access_token'];
      final refreshToken = session['refresh_token'];
      if (accessToken is! String || refreshToken is! String) {
        throw const FormatException('Sesi tersimpan tidak berisi token valid.');
      }
      final api = ApiClient()..setSession(accessToken, refreshToken);
      await PosRepository(api, database).syncPendingOrders();
      return true;
    } on Exception catch (error, stackTrace) {
      developer.log(
        'Background order sync failed.',
        name: 'jou_coffee.sync',
        error: error,
        stackTrace: stackTrace,
      );
      return false;
    } finally {
      await database.close();
    }
  });
}

Future<String?> initializeBackgroundSync() async {
  if (!Platform.isAndroid) return null;
  try {
    await Workmanager().initialize(backgroundSyncDispatcher);
    await Workmanager().registerPeriodicTask(
      'jou-coffee-order-sync',
      'syncPendingOrders',
      frequency: const Duration(minutes: 15),
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
    );
    return null;
  } on Exception catch (error, stackTrace) {
    developer.log(
      'Could not schedule Android background order sync.',
      name: 'jou_coffee.sync',
      error: error,
      stackTrace: stackTrace,
    );
    return 'Sinkronisasi otomatis latar belakang tidak tersedia: $error';
  }
}
