import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/src/data/local/app_database.dart';

void main() {
  late AppDatabase database;

  setUp(() {
    database = AppDatabase(NativeDatabase.memory());
  });

  tearDown(() async {
    await database.close();
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
}
