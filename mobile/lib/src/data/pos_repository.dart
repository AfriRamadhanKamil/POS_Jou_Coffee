import 'dart:convert';

import 'package:dio/dio.dart';

import 'api/api_client.dart';
import 'local/app_database.dart';

class PosRepository {
  const PosRepository(this._api, this._database);

  final ApiClient _api;
  final AppDatabase _database;

  Future<PosCatalog> loadCatalog() async {
    try {
      final response = await _api.getData('/menus/catalog');
      final tables = await _api.getData('/tables');
      response['tables'] = tables['items'];
      final payload = jsonEncode(response);
      await _database.cacheCatalog(payload);
      return PosCatalog.fromJson(response);
    } on DioException catch (error) {
      if (error.response != null &&
          error.requestOptions.extra['refreshUnavailable'] != true) {
        rethrow;
      }
      final cached = await _database.readCachedCatalog();
      if (cached == null) rethrow;
      return PosCatalog.fromJson(
        jsonDecode(cached) as Map<String, dynamic>,
        isOffline: true,
      );
    }
  }

  Future<CreatedOrder> createOrder(Map<String, Object?> payload) async {
    try {
      final response = await _api.postData('/orders', body: payload);
      return CreatedOrder.fromJson(response, queued: false);
    } on DioException catch (error) {
      final status = error.response?.statusCode;
      final refreshUnavailable =
          error.requestOptions.extra['refreshUnavailable'] == true;
      if (error.response != null &&
          !refreshUnavailable &&
          (status == null || status < 500)) {
        rethrow;
      }
      final key = payload['idempotency_key'];
      if (key is! String || key.isEmpty) {
        throw const FormatException('Pesanan offline membutuhkan idempotency key.');
      }
      await _database.enqueueOrder(key, jsonEncode(payload));
      return CreatedOrder(
        id: key,
        orderNumber: 'Menunggu sinkronisasi',
        status: 'QUEUED',
        total: (payload['total'] as num?)?.toDouble() ?? 0,
        queued: true,
      );
    }
  }

  Future<int> syncPendingOrders() async {
    final pending = await _database.getPendingOrders();
    var synced = 0;
    for (final item in pending) {
      try {
        final payload = jsonDecode(item.payload) as Map<String, dynamic>;
        await _api.postData('/orders', body: payload);
        await _database.removePendingOrder(item.idempotencyKey);
        synced++;
      } on DioException catch (error) {
        await _database.setPendingOrderError(
          item.idempotencyKey,
          apiErrorMessage(error),
        );
        rethrow;
      } on ApiException catch (error) {
        await _database.setPendingOrderError(
          item.idempotencyKey,
          error.message,
        );
        rethrow;
      } on FormatException catch (error) {
        await _database.setPendingOrderError(
          item.idempotencyKey,
          'Data pesanan lokal tidak valid: ${error.message}',
        );
        rethrow;
      }
    }
    return synced;
  }
}

class PosCatalog {
  const PosCatalog({
    required this.categories,
    required this.modifierGroups,
    required this.channels,
    required this.tables,
    this.isOffline = false,
  });

  final List<MenuCategory> categories;
  final List<ModifierGroup> modifierGroups;
  final List<SalesChannel> channels;
  final List<DiningTable> tables;
  final bool isOffline;

  factory PosCatalog.fromJson(
    Map<String, dynamic> json, {
    bool isOffline = false,
  }) {
    return PosCatalog(
      categories: (json['categories'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(MenuCategory.fromJson)
          .toList(),
      modifierGroups: (json['modifier_groups'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(ModifierGroup.fromJson)
          .toList(),
      channels: (json['channels'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(SalesChannel.fromJson)
          .toList(),
      tables: (json['tables'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(DiningTable.fromJson)
          .toList(),
      isOffline: isOffline,
    );
  }
}

class DiningTable {
  const DiningTable(this.id, this.number);

  final String id;
  final String number;

  factory DiningTable.fromJson(Map<String, dynamic> json) => DiningTable(
    json['id'] as String? ?? '',
    json['table_number'] as String? ?? '',
  );
}

class MenuCategory {
  const MenuCategory(this.id, this.name, this.menus);

  final String id;
  final String name;
  final List<MenuProduct> menus;

  factory MenuCategory.fromJson(Map<String, dynamic> json) => MenuCategory(
    json['id'] as String? ?? '',
    json['name'] as String? ?? 'Menu',
    (json['menus'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(MenuProduct.fromJson)
        .toList(),
  );
}

class MenuProduct {
  const MenuProduct({
    required this.id,
    required this.name,
    required this.price,
    required this.available,
    required this.variants,
  });

  final String id;
  final String name;
  final double price;
  final bool available;
  final List<MenuVariant> variants;

  factory MenuProduct.fromJson(Map<String, dynamic> json) => MenuProduct(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? 'Menu',
    price: (json['base_price'] as num?)?.toDouble() ?? 0,
    available: json['is_available'] as bool? ?? true,
    variants: (json['variants'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(MenuVariant.fromJson)
        .toList(),
  );
}

class MenuVariant {
  const MenuVariant({
    required this.id,
    required this.name,
    required this.priceAdjustment,
  });

  final String id;
  final String name;
  final double priceAdjustment;

  factory MenuVariant.fromJson(Map<String, dynamic> json) => MenuVariant(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    priceAdjustment: (json['price_adjustment'] as num?)?.toDouble() ?? 0,
  );
}

class ModifierGroup {
  const ModifierGroup({
    required this.name,
    required this.minSelection,
    required this.maxSelection,
    required this.required,
    required this.modifiers,
  });

  final String name;
  final int minSelection;
  final int maxSelection;
  final bool required;
  final List<MenuModifier> modifiers;

  factory ModifierGroup.fromJson(Map<String, dynamic> json) => ModifierGroup(
    name: json['name'] as String? ?? '',
    minSelection: json['min_selection'] as int? ?? 0,
    maxSelection: json['max_selection'] as int? ?? 0,
    required: json['is_required'] as bool? ?? false,
    modifiers: (json['modifiers'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(MenuModifier.fromJson)
        .toList(),
  );
}

class MenuModifier {
  const MenuModifier({
    required this.id,
    required this.name,
    required this.price,
  });

  final String id;
  final String name;
  final double price;

  factory MenuModifier.fromJson(Map<String, dynamic> json) => MenuModifier(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    price: (json['price'] as num?)?.toDouble() ?? 0,
  );
}

class SalesChannel {
  const SalesChannel(this.id, this.name, this.commission);

  final String id;
  final String name;
  final double commission;

  factory SalesChannel.fromJson(Map<String, dynamic> json) => SalesChannel(
    json['id'] as String? ?? '',
    json['name'] as String? ?? '',
    (json['commission_percent'] as num?)?.toDouble() ?? 0,
  );
}

class CreatedOrder {
  const CreatedOrder({
    required this.id,
    required this.orderNumber,
    required this.status,
    required this.total,
    required this.queued,
  });

  final String id;
  final String orderNumber;
  final String status;
  final double total;
  final bool queued;

  factory CreatedOrder.fromJson(
    Map<String, dynamic> json, {
    required bool queued,
  }) => CreatedOrder(
    id: json['id'] as String? ?? '',
    orderNumber: json['order_no'] as String? ?? '',
    status: json['status'] as String? ?? 'APPROVED',
    total: (json['total'] as num?)?.toDouble() ?? 0,
    queued: queued,
  );
}

class CartLine {
  const CartLine({
    required this.menu,
    required this.variant,
    required this.modifiers,
    required this.quantity,
  });

  final MenuProduct menu;
  final MenuVariant? variant;
  final List<MenuModifier> modifiers;
  final int quantity;

  double get unitPrice =>
      menu.price +
      (variant?.priceAdjustment ?? 0) +
      modifiers.fold(0, (total, modifier) => total + modifier.price);

  CartLine withQuantity(int value) => CartLine(
    menu: menu,
    variant: variant,
    modifiers: modifiers,
    quantity: value,
  );
}
