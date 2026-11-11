import 'dart:io';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/src/data/local/app_database.dart';

void main() {
  late AppDatabase database;
  var setUpDatabaseClosed = false;

  setUp(() {
    database = AppDatabase(NativeDatabase.memory());
    setUpDatabaseClosed = false;
  });

  tearDown(() async {
    if (!setUpDatabaseClosed) await database.close();
  });

  test('persists cached catalog and pending orders', () async {
    const catalog = '{"categories":[]}';
    await database.cacheCatalog(catalog);
    await database.enqueueOrder('key-1', '{"idempotency_key":"key-1"}');

    expect(await database.readCachedCatalog(), catalog);
    expect((await database.getPendingOrders()).single.idempotencyKey, 'key-1');

    await database.removePendingOrder('key-1');
    expect(await database.getPendingOrders(), isEmpty);
  });

  test('records an actionable sync error on the queued order', () async {
    await database.enqueueOrder('key-2', '{"idempotency_key":"key-2"}');
    await database.setPendingOrderError('key-2', 'Server tidak tersedia');

    expect(
      (await database.getPendingOrders()).single.lastError,
      'Server tidak tersedia',
    );
  });

  test('persists queued orders across database reopen', () async {
    await database.close();
    setUpDatabaseClosed = true;
    final directory = await Directory.systemTemp.createTemp('jou-coffee-db-');
    final file = File(
      '${directory.path}${Platform.pathSeparator}offline.sqlite',
    );
    AppDatabase? fileDatabase;
    try {
      fileDatabase = AppDatabase(NativeDatabase(file));
      await fileDatabase.enqueueOrder(
        'persistent-key',
        '{"idempotency_key":"persistent-key","total":12000}',
      );
      await fileDatabase.close();

      fileDatabase = AppDatabase(NativeDatabase(file));
      expect(
        (await fileDatabase.getPendingOrders()).single.idempotencyKey,
        'persistent-key',
      );
    } finally {
      await fileDatabase?.close();
      await directory.delete(recursive: true);
    }
  });
}
