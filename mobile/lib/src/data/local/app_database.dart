import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';

part 'app_database.g.dart';

class CachedCatalogs extends Table {
  IntColumn get id => integer()();
  TextColumn get payload => text()();

  @override
  Set<Column<Object>> get primaryKey => {id};
}

class PendingOrders extends Table {
  TextColumn get idempotencyKey => text()();
  TextColumn get payload => text()();
  TextColumn get lastError => text().nullable()();
  DateTimeColumn get createdAt => dateTime()();

  @override
  Set<Column<Object>> get primaryKey => {idempotencyKey};
}

@DriftDatabase(tables: [CachedCatalogs, PendingOrders])
class AppDatabase extends _$AppDatabase {
  AppDatabase([QueryExecutor? executor])
    : super(executor ?? driftDatabase(name: 'jou_coffee'));

  @override
  int get schemaVersion => 1;

  Future<void> cacheCatalog(String payload) {
    return into(cachedCatalogs).insertOnConflictUpdate(
      CachedCatalogsCompanion.insert(id: const Value(1), payload: payload),
    );
  }

  Future<String?> readCachedCatalog() async {
    final row = await (select(cachedCatalogs)..where((table) => table.id.equals(1)))
        .getSingleOrNull();
    return row?.payload;
  }

  Future<void> enqueueOrder(String key, String payload) {
    return into(pendingOrders).insertOnConflictUpdate(
      PendingOrdersCompanion.insert(
        idempotencyKey: key,
        payload: payload,
        lastError: const Value(null),
        createdAt: DateTime.now().toUtc(),
      ),
    );
  }

  Stream<List<PendingOrder>> watchPendingOrders() {
    return (select(pendingOrders)
          ..orderBy([(table) => OrderingTerm.asc(table.createdAt)]))
        .watch();
  }

  Future<List<PendingOrder>> getPendingOrders() {
    return (select(pendingOrders)
          ..orderBy([(table) => OrderingTerm.asc(table.createdAt)]))
        .get();
  }

  Future<void> removePendingOrder(String key) {
    return (delete(pendingOrders)..where((table) => table.idempotencyKey.equals(key)))
        .go();
  }

  Future<void> setPendingOrderError(String key, String error) {
    return (update(pendingOrders)..where((table) => table.idempotencyKey.equals(key)))
        .write(PendingOrdersCompanion(lastError: Value(error)));
  }
}
