// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'app_database.dart';

// ignore_for_file: type=lint
class $CachedCatalogsTable extends CachedCatalogs
    with TableInfo<$CachedCatalogsTable, CachedCatalog> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $CachedCatalogsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _payloadMeta = const VerificationMeta(
    'payload',
  );
  @override
  late final GeneratedColumn<String> payload = GeneratedColumn<String>(
    'payload',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [id, payload];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'cached_catalogs';
  @override
  VerificationContext validateIntegrity(
    Insertable<CachedCatalog> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('payload')) {
      context.handle(
        _payloadMeta,
        payload.isAcceptableOrUnknown(data['payload']!, _payloadMeta),
      );
    } else if (isInserting) {
      context.missing(_payloadMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  CachedCatalog map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return CachedCatalog(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      payload: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}payload'],
      )!,
    );
  }

  @override
  $CachedCatalogsTable createAlias(String alias) {
    return $CachedCatalogsTable(attachedDatabase, alias);
  }
}

class CachedCatalog extends DataClass implements Insertable<CachedCatalog> {
  final int id;
  final String payload;
  const CachedCatalog({required this.id, required this.payload});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['payload'] = Variable<String>(payload);
    return map;
  }

  CachedCatalogsCompanion toCompanion(bool nullToAbsent) {
    return CachedCatalogsCompanion(id: Value(id), payload: Value(payload));
  }

  factory CachedCatalog.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return CachedCatalog(
      id: serializer.fromJson<int>(json['id']),
      payload: serializer.fromJson<String>(json['payload']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'payload': serializer.toJson<String>(payload),
    };
  }

  CachedCatalog copyWith({int? id, String? payload}) =>
      CachedCatalog(id: id ?? this.id, payload: payload ?? this.payload);
  CachedCatalog copyWithCompanion(CachedCatalogsCompanion data) {
    return CachedCatalog(
      id: data.id.present ? data.id.value : this.id,
      payload: data.payload.present ? data.payload.value : this.payload,
    );
  }

  @override
  String toString() {
    return (StringBuffer('CachedCatalog(')
          ..write('id: $id, ')
          ..write('payload: $payload')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(id, payload);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is CachedCatalog &&
          other.id == this.id &&
          other.payload == this.payload);
}

class CachedCatalogsCompanion extends UpdateCompanion<CachedCatalog> {
  final Value<int> id;
  final Value<String> payload;
  const CachedCatalogsCompanion({
    this.id = const Value.absent(),
    this.payload = const Value.absent(),
  });
  CachedCatalogsCompanion.insert({
    this.id = const Value.absent(),
    required String payload,
  }) : payload = Value(payload);
  static Insertable<CachedCatalog> custom({
    Expression<int>? id,
    Expression<String>? payload,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (payload != null) 'payload': payload,
    });
  }

  CachedCatalogsCompanion copyWith({Value<int>? id, Value<String>? payload}) {
    return CachedCatalogsCompanion(
      id: id ?? this.id,
      payload: payload ?? this.payload,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (payload.present) {
      map['payload'] = Variable<String>(payload.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('CachedCatalogsCompanion(')
          ..write('id: $id, ')
          ..write('payload: $payload')
          ..write(')'))
        .toString();
  }
}

class $PendingOrdersTable extends PendingOrders
    with TableInfo<$PendingOrdersTable, PendingOrder> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $PendingOrdersTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idempotencyKeyMeta = const VerificationMeta(
    'idempotencyKey',
  );
  @override
  late final GeneratedColumn<String> idempotencyKey = GeneratedColumn<String>(
    'idempotency_key',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _payloadMeta = const VerificationMeta(
    'payload',
  );
  @override
  late final GeneratedColumn<String> payload = GeneratedColumn<String>(
    'payload',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _lastErrorMeta = const VerificationMeta(
    'lastError',
  );
  @override
  late final GeneratedColumn<String> lastError = GeneratedColumn<String>(
    'last_error',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _createdAtMeta = const VerificationMeta(
    'createdAt',
  );
  @override
  late final GeneratedColumn<DateTime> createdAt = GeneratedColumn<DateTime>(
    'created_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    idempotencyKey,
    payload,
    lastError,
    createdAt,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'pending_orders';
  @override
  VerificationContext validateIntegrity(
    Insertable<PendingOrder> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('idempotency_key')) {
      context.handle(
        _idempotencyKeyMeta,
        idempotencyKey.isAcceptableOrUnknown(
          data['idempotency_key']!,
          _idempotencyKeyMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_idempotencyKeyMeta);
    }
    if (data.containsKey('payload')) {
      context.handle(
        _payloadMeta,
        payload.isAcceptableOrUnknown(data['payload']!, _payloadMeta),
      );
    } else if (isInserting) {
      context.missing(_payloadMeta);
    }
    if (data.containsKey('last_error')) {
      context.handle(
        _lastErrorMeta,
        lastError.isAcceptableOrUnknown(data['last_error']!, _lastErrorMeta),
      );
    }
    if (data.containsKey('created_at')) {
      context.handle(
        _createdAtMeta,
        createdAt.isAcceptableOrUnknown(data['created_at']!, _createdAtMeta),
      );
    } else if (isInserting) {
      context.missing(_createdAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {idempotencyKey};
  @override
  PendingOrder map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return PendingOrder(
      idempotencyKey: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}idempotency_key'],
      )!,
      payload: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}payload'],
      )!,
      lastError: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}last_error'],
      ),
      createdAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}created_at'],
      )!,
    );
  }

  @override
  $PendingOrdersTable createAlias(String alias) {
    return $PendingOrdersTable(attachedDatabase, alias);
  }
}

class PendingOrder extends DataClass implements Insertable<PendingOrder> {
  final String idempotencyKey;
  final String payload;
  final String? lastError;
  final DateTime createdAt;
  const PendingOrder({
    required this.idempotencyKey,
    required this.payload,
    this.lastError,
    required this.createdAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['idempotency_key'] = Variable<String>(idempotencyKey);
    map['payload'] = Variable<String>(payload);
    if (!nullToAbsent || lastError != null) {
      map['last_error'] = Variable<String>(lastError);
    }
    map['created_at'] = Variable<DateTime>(createdAt);
    return map;
  }

  PendingOrdersCompanion toCompanion(bool nullToAbsent) {
    return PendingOrdersCompanion(
      idempotencyKey: Value(idempotencyKey),
      payload: Value(payload),
      lastError: lastError == null && nullToAbsent
          ? const Value.absent()
          : Value(lastError),
      createdAt: Value(createdAt),
    );
  }

  factory PendingOrder.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return PendingOrder(
      idempotencyKey: serializer.fromJson<String>(json['idempotencyKey']),
      payload: serializer.fromJson<String>(json['payload']),
      lastError: serializer.fromJson<String?>(json['lastError']),
      createdAt: serializer.fromJson<DateTime>(json['createdAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'idempotencyKey': serializer.toJson<String>(idempotencyKey),
      'payload': serializer.toJson<String>(payload),
      'lastError': serializer.toJson<String?>(lastError),
      'createdAt': serializer.toJson<DateTime>(createdAt),
    };
  }

  PendingOrder copyWith({
    String? idempotencyKey,
    String? payload,
    Value<String?> lastError = const Value.absent(),
    DateTime? createdAt,
  }) => PendingOrder(
    idempotencyKey: idempotencyKey ?? this.idempotencyKey,
    payload: payload ?? this.payload,
    lastError: lastError.present ? lastError.value : this.lastError,
    createdAt: createdAt ?? this.createdAt,
  );
  PendingOrder copyWithCompanion(PendingOrdersCompanion data) {
    return PendingOrder(
      idempotencyKey: data.idempotencyKey.present
          ? data.idempotencyKey.value
          : this.idempotencyKey,
      payload: data.payload.present ? data.payload.value : this.payload,
      lastError: data.lastError.present ? data.lastError.value : this.lastError,
      createdAt: data.createdAt.present ? data.createdAt.value : this.createdAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('PendingOrder(')
          ..write('idempotencyKey: $idempotencyKey, ')
          ..write('payload: $payload, ')
          ..write('lastError: $lastError, ')
          ..write('createdAt: $createdAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode =>
      Object.hash(idempotencyKey, payload, lastError, createdAt);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PendingOrder &&
          other.idempotencyKey == this.idempotencyKey &&
          other.payload == this.payload &&
          other.lastError == this.lastError &&
          other.createdAt == this.createdAt);
}

class PendingOrdersCompanion extends UpdateCompanion<PendingOrder> {
  final Value<String> idempotencyKey;
  final Value<String> payload;
  final Value<String?> lastError;
  final Value<DateTime> createdAt;
  final Value<int> rowid;
  const PendingOrdersCompanion({
    this.idempotencyKey = const Value.absent(),
    this.payload = const Value.absent(),
    this.lastError = const Value.absent(),
    this.createdAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  PendingOrdersCompanion.insert({
    required String idempotencyKey,
    required String payload,
    this.lastError = const Value.absent(),
    required DateTime createdAt,
    this.rowid = const Value.absent(),
  }) : idempotencyKey = Value(idempotencyKey),
       payload = Value(payload),
       createdAt = Value(createdAt);
  static Insertable<PendingOrder> custom({
    Expression<String>? idempotencyKey,
    Expression<String>? payload,
    Expression<String>? lastError,
    Expression<DateTime>? createdAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (idempotencyKey != null) 'idempotency_key': idempotencyKey,
      if (payload != null) 'payload': payload,
      if (lastError != null) 'last_error': lastError,
      if (createdAt != null) 'created_at': createdAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  PendingOrdersCompanion copyWith({
    Value<String>? idempotencyKey,
    Value<String>? payload,
    Value<String?>? lastError,
    Value<DateTime>? createdAt,
    Value<int>? rowid,
  }) {
    return PendingOrdersCompanion(
      idempotencyKey: idempotencyKey ?? this.idempotencyKey,
      payload: payload ?? this.payload,
      lastError: lastError ?? this.lastError,
      createdAt: createdAt ?? this.createdAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (idempotencyKey.present) {
      map['idempotency_key'] = Variable<String>(idempotencyKey.value);
    }
    if (payload.present) {
      map['payload'] = Variable<String>(payload.value);
    }
    if (lastError.present) {
      map['last_error'] = Variable<String>(lastError.value);
    }
    if (createdAt.present) {
      map['created_at'] = Variable<DateTime>(createdAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('PendingOrdersCompanion(')
          ..write('idempotencyKey: $idempotencyKey, ')
          ..write('payload: $payload, ')
          ..write('lastError: $lastError, ')
          ..write('createdAt: $createdAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

abstract class _$AppDatabase extends GeneratedDatabase {
  _$AppDatabase(QueryExecutor e) : super(e);
  $AppDatabaseManager get managers => $AppDatabaseManager(this);
  late final $CachedCatalogsTable cachedCatalogs = $CachedCatalogsTable(this);
  late final $PendingOrdersTable pendingOrders = $PendingOrdersTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [
    cachedCatalogs,
    pendingOrders,
  ];
}

typedef $$CachedCatalogsTableCreateCompanionBuilder =
    CachedCatalogsCompanion Function({Value<int> id, required String payload});
typedef $$CachedCatalogsTableUpdateCompanionBuilder =
    CachedCatalogsCompanion Function({Value<int> id, Value<String> payload});

class $$CachedCatalogsTableFilterComposer
    extends Composer<_$AppDatabase, $CachedCatalogsTable> {
  $$CachedCatalogsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnFilters(column),
  );
}

class $$CachedCatalogsTableOrderingComposer
    extends Composer<_$AppDatabase, $CachedCatalogsTable> {
  $$CachedCatalogsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$CachedCatalogsTableAnnotationComposer
    extends Composer<_$AppDatabase, $CachedCatalogsTable> {
  $$CachedCatalogsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<String> get payload =>
      $composableBuilder(column: $table.payload, builder: (column) => column);
}

class $$CachedCatalogsTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $CachedCatalogsTable,
          CachedCatalog,
          $$CachedCatalogsTableFilterComposer,
          $$CachedCatalogsTableOrderingComposer,
          $$CachedCatalogsTableAnnotationComposer,
          $$CachedCatalogsTableCreateCompanionBuilder,
          $$CachedCatalogsTableUpdateCompanionBuilder,
          (
            CachedCatalog,
            BaseReferences<_$AppDatabase, $CachedCatalogsTable, CachedCatalog>,
          ),
          CachedCatalog,
          PrefetchHooks Function()
        > {
  $$CachedCatalogsTableTableManager(
    _$AppDatabase db,
    $CachedCatalogsTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$CachedCatalogsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$CachedCatalogsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$CachedCatalogsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<String> payload = const Value.absent(),
              }) => CachedCatalogsCompanion(id: id, payload: payload),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required String payload,
              }) => CachedCatalogsCompanion.insert(id: id, payload: payload),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$CachedCatalogsTable, CachedCatalog>(table),
                  BaseReferences<
                    _$AppDatabase,
                    $CachedCatalogsTable,
                    CachedCatalog
                  >(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$CachedCatalogsTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $CachedCatalogsTable,
      CachedCatalog,
      $$CachedCatalogsTableFilterComposer,
      $$CachedCatalogsTableOrderingComposer,
      $$CachedCatalogsTableAnnotationComposer,
      $$CachedCatalogsTableCreateCompanionBuilder,
      $$CachedCatalogsTableUpdateCompanionBuilder,
      (
        CachedCatalog,
        BaseReferences<_$AppDatabase, $CachedCatalogsTable, CachedCatalog>,
      ),
      CachedCatalog,
      PrefetchHooks Function()
    >;
typedef $$PendingOrdersTableCreateCompanionBuilder =
    PendingOrdersCompanion Function({
      required String idempotencyKey,
      required String payload,
      Value<String?> lastError,
      required DateTime createdAt,
      Value<int> rowid,
    });
typedef $$PendingOrdersTableUpdateCompanionBuilder =
    PendingOrdersCompanion Function({
      Value<String> idempotencyKey,
      Value<String> payload,
      Value<String?> lastError,
      Value<DateTime> createdAt,
      Value<int> rowid,
    });

class $$PendingOrdersTableFilterComposer
    extends Composer<_$AppDatabase, $PendingOrdersTable> {
  $$PendingOrdersTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get idempotencyKey => $composableBuilder(
    column: $table.idempotencyKey,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get lastError => $composableBuilder(
    column: $table.lastError,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnFilters(column),
  );
}

class $$PendingOrdersTableOrderingComposer
    extends Composer<_$AppDatabase, $PendingOrdersTable> {
  $$PendingOrdersTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get idempotencyKey => $composableBuilder(
    column: $table.idempotencyKey,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get lastError => $composableBuilder(
    column: $table.lastError,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$PendingOrdersTableAnnotationComposer
    extends Composer<_$AppDatabase, $PendingOrdersTable> {
  $$PendingOrdersTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get idempotencyKey => $composableBuilder(
    column: $table.idempotencyKey,
    builder: (column) => column,
  );

  GeneratedColumn<String> get payload =>
      $composableBuilder(column: $table.payload, builder: (column) => column);

  GeneratedColumn<String> get lastError =>
      $composableBuilder(column: $table.lastError, builder: (column) => column);

  GeneratedColumn<DateTime> get createdAt =>
      $composableBuilder(column: $table.createdAt, builder: (column) => column);
}

class $$PendingOrdersTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $PendingOrdersTable,
          PendingOrder,
          $$PendingOrdersTableFilterComposer,
          $$PendingOrdersTableOrderingComposer,
          $$PendingOrdersTableAnnotationComposer,
          $$PendingOrdersTableCreateCompanionBuilder,
          $$PendingOrdersTableUpdateCompanionBuilder,
          (
            PendingOrder,
            BaseReferences<_$AppDatabase, $PendingOrdersTable, PendingOrder>,
          ),
          PendingOrder,
          PrefetchHooks Function()
        > {
  $$PendingOrdersTableTableManager(_$AppDatabase db, $PendingOrdersTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$PendingOrdersTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$PendingOrdersTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$PendingOrdersTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> idempotencyKey = const Value.absent(),
                Value<String> payload = const Value.absent(),
                Value<String?> lastError = const Value.absent(),
                Value<DateTime> createdAt = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => PendingOrdersCompanion(
                idempotencyKey: idempotencyKey,
                payload: payload,
                lastError: lastError,
                createdAt: createdAt,
                rowid: rowid,
              ),
          createCompanionCallback:
              ({
                required String idempotencyKey,
                required String payload,
                Value<String?> lastError = const Value.absent(),
                required DateTime createdAt,
                Value<int> rowid = const Value.absent(),
              }) => PendingOrdersCompanion.insert(
                idempotencyKey: idempotencyKey,
                payload: payload,
                lastError: lastError,
                createdAt: createdAt,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$PendingOrdersTable, PendingOrder>(table),
                  BaseReferences<
                    _$AppDatabase,
                    $PendingOrdersTable,
                    PendingOrder
                  >(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$PendingOrdersTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $PendingOrdersTable,
      PendingOrder,
      $$PendingOrdersTableFilterComposer,
      $$PendingOrdersTableOrderingComposer,
      $$PendingOrdersTableAnnotationComposer,
      $$PendingOrdersTableCreateCompanionBuilder,
      $$PendingOrdersTableUpdateCompanionBuilder,
      (
        PendingOrder,
        BaseReferences<_$AppDatabase, $PendingOrdersTable, PendingOrder>,
      ),
      PendingOrder,
      PrefetchHooks Function()
    >;

class $AppDatabaseManager {
  final _$AppDatabase _db;
  $AppDatabaseManager(this._db);
  $$CachedCatalogsTableTableManager get cachedCatalogs =>
      $$CachedCatalogsTableTableManager(_db, _db.cachedCatalogs);
  $$PendingOrdersTableTableManager get pendingOrders =>
      $$PendingOrdersTableTableManager(_db, _db.pendingOrders);
}
