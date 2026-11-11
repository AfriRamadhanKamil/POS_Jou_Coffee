import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:uuid/uuid.dart';

import '../../app/providers.dart';
import '../../app/state_providers.dart';
import '../../data/api/api_client.dart';
import '../../data/local/app_database.dart';
import '../../data/pos_repository.dart';
import '../../data/receipt_printer.dart';

final posCatalogProvider = FutureProvider<PosCatalog>(
  (ref) => ref.watch(posRepositoryProvider).loadCatalog(),
);

class PosScreen extends ConsumerStatefulWidget {
  const PosScreen({super.key});

  @override
  ConsumerState<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends ConsumerState<PosScreen> {
  final _searchController = TextEditingController();
  final _externalOrderController = TextEditingController();
  final List<CartLine> _cart = [];
  String _search = '';
  String _orderType = 'DINE_IN';
  String? _selectedCategory;
  String? _selectedTableId;
  String? _selectedChannelId;

  @override
  void dispose() {
    _searchController.dispose();
    _externalOrderController.dispose();
    super.dispose();
  }

  double get _total =>
      _cart.fold(0, (total, line) => total + line.unitPrice * line.quantity);

  Future<void> _addProduct(
    MenuProduct product,
    List<ModifierGroup> groups,
  ) async {
    final selected = await showDialog<CartLine>(
      context: context,
      builder: (context) =>
          _ProductOptionsDialog(product: product, groups: groups),
    );
    if (selected == null || !mounted) return;
    setState(() {
      final index = _cart.indexWhere(
        (line) =>
            line.menu.id == selected.menu.id &&
            line.variant?.id == selected.variant?.id &&
            _modifierKey(line.modifiers) == _modifierKey(selected.modifiers),
      );
      if (index < 0) {
        _cart.add(selected);
      } else {
        _cart[index] = _cart[index].withQuantity(_cart[index].quantity + 1);
      }
    });
  }

  String _modifierKey(List<MenuModifier> modifiers) =>
      (modifiers.map((item) => item.id).toList()..sort()).join(',');

  void _changeQuantity(int index, int amount) {
    setState(() {
      final next = _cart[index].quantity + amount;
      if (next <= 0) {
        _cart.removeAt(index);
      } else {
        _cart[index] = _cart[index].withQuantity(next);
      }
    });
  }

  Future<void> _checkout() async {
    if (_cart.isEmpty) return;
    if (_orderType == 'DINE_IN' && _selectedTableId == null) {
      _showMessage('Pilih meja sebelum menyimpan pesanan Dine In.');
      return;
    }
    if (_orderType == 'DELIVERY' && _selectedChannelId == null) {
      _showMessage('Pilih channel pesanan online.');
      return;
    }
    if (_orderType == 'DELIVERY' &&
        _externalOrderController.text.trim().isEmpty) {
      _showMessage('ID pesanan platform wajib diisi.');
      return;
    }

    final selection = await showDialog<_PaymentSelection>(
      context: context,
      builder: (context) => _PaymentDialog(total: _total),
    );
    if (selection == null || !mounted) return;

    final catalog = ref.read(posCatalogProvider).asData?.value;
    final channel = catalog?.channels
        .where((item) => item.id == _selectedChannelId)
        .firstOrNull;
    final idempotencyKey = const Uuid().v4();
    final payload = <String, Object?>{
      'idempotency_key': idempotencyKey,
      'source': _orderType == 'DELIVERY' ? 'ONLINE_PLATFORM' : 'POS',
      'order_type': _orderType,
      if (_orderType == 'DINE_IN') 'table_id': _selectedTableId,
      if (_orderType == 'DELIVERY') ...{
        'channel_id': _selectedChannelId,
        'external_order_id': _externalOrderController.text.trim(),
        'platform_commission': _total * (channel?.commission ?? 0) / 100,
      },
      'is_paid': true,
      'total': _total,
      'items': [
        for (final line in _cart)
          {
            'menu_id': line.menu.id,
            'item_name': line.menu.name,
            'quantity': line.quantity,
            'unit_price':
                line.menu.price + (line.variant?.priceAdjustment ?? 0),
            if (line.variant != null) 'variant_id': line.variant!.id,
            'discount': 0,
            'modifiers': [
              for (final modifier in line.modifiers)
                {
                  'modifier_id': modifier.id,
                  'modifier_name': modifier.name,
                  'price': modifier.price,
                },
            ],
          },
      ],
      'payment': {
        'payment_method': _orderType == 'DELIVERY'
            ? 'PLATFORM'
            : selection.method,
        'amount': selection.amount,
      },
    };

    try {
      final order = await ref.read(posRepositoryProvider).createOrder(payload);
      ref.invalidate(pendingOrdersProvider);
      if (!mounted) return;
      final purchasedItems = List<CartLine>.of(_cart);
      setState(() {
        _cart.clear();
        _externalOrderController.clear();
      });
      await _showOrderComplete(order, purchasedItems);
    } on Exception catch (error) {
      if (mounted) {
        _showMessage('Pesanan belum tersimpan: ${apiErrorMessage(error)}');
      }
    }
  }

  Future<void> _showOrderComplete(
    CreatedOrder order,
    List<CartLine> purchasedItems,
  ) async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(
          order.queued ? 'Pesanan tersimpan offline' : 'Pesanan tersimpan',
        ),
        content: Text(
          order.queued
              ? 'Pesanan disimpan di perangkat dan menunggu koneksi untuk disinkronkan.'
              : 'Nomor pesanan ${order.orderNumber}',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Selesai'),
          ),
          FilledButton.icon(
            onPressed: () async {
              Navigator.pop(dialogContext);
              try {
                await ReceiptPrinter().printOrder(
                  context,
                  orderNumber: order.orderNumber,
                  items: purchasedItems,
                  total: order.total,
                );
                if (mounted) _showMessage('Struk berhasil dicetak.');
              } on Exception catch (error) {
                if (mounted) {
                  _showMessage('Struk gagal dicetak: ${error.toString()}');
                }
              }
            },
            icon: const Icon(Icons.print_outlined),
            label: const Text('Cetak struk'),
          ),
        ],
      ),
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final catalogAsync = ref.watch(posCatalogProvider);
    return catalogAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, stackTrace) => _LoadError(
        error: error,
        onRetry: () => ref.invalidate(posCatalogProvider),
      ),
      data: (catalog) {
        final pending =
            ref.watch(pendingOrdersProvider).asData?.value ?? const [];
        final hasNetwork = ref.watch(connectivityStatusProvider).asData?.value;
        final allProducts = catalog.categories
            .expand((category) => category.menus)
            .where(
              (product) =>
                  (_selectedCategory == null ||
                      catalog.categories
                          .firstWhere(
                            (category) => category.id == _selectedCategory,
                          )
                          .menus
                          .any((item) => item.id == product.id)) &&
                  product.name.toLowerCase().contains(_search.toLowerCase()),
            )
            .toList();

        return Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              if (catalog.isOffline || hasNetwork == false)
                _StatusBanner(
                  message: hasNetwork == false
                      ? 'Offline — transaksi tersimpan di SQLite dan akan disinkronkan saat jaringan kembali.'
                      : 'Server belum dapat dijangkau — transaksi tersimpan di SQLite dan akan disinkronkan saat tersedia.',
                  icon: Icons.cloud_off_outlined,
                ),
              if (pending.isNotEmpty)
                _PendingSyncBanner(orders: pending, onSync: _syncPending),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth >= 900;
                    final products = _productPanel(catalog, allProducts);
                    final cart = _cartPanel(catalog);
                    if (wide) {
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(flex: 7, child: products),
                          const SizedBox(width: 16),
                          SizedBox(width: 350, child: cart),
                        ],
                      );
                    }
                    return Column(
                      children: [
                        Expanded(child: products),
                        const SizedBox(height: 12),
                        SizedBox(height: 310, child: cart),
                      ],
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _syncPending() async {
    try {
      final count = await ref.read(posRepositoryProvider).syncPendingOrders();
      ref.invalidate(pendingOrdersProvider);
      if (mounted) _showMessage('$count pesanan berhasil disinkronkan.');
    } on Exception catch (error) {
      ref.invalidate(pendingOrdersProvider);
      if (mounted) {
        _showMessage('Sinkronisasi gagal: ${apiErrorMessage(error)}');
      }
    }
  }

  Widget _productPanel(PosCatalog catalog, List<MenuProduct> products) {
    return Column(
      children: [
        TextField(
          controller: _searchController,
          onChanged: (value) => setState(() => _search = value),
          decoration: const InputDecoration(
            hintText: 'Cari menu...',
            prefixIcon: Icon(Icons.search),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 44,
          child: ListView(
            scrollDirection: Axis.horizontal,
            children: [
              _CategoryChip(
                label: 'Semua',
                selected: _selectedCategory == null,
                onTap: () => setState(() => _selectedCategory = null),
              ),
              for (final category in catalog.categories)
                _CategoryChip(
                  label: category.name,
                  selected: _selectedCategory == category.id,
                  onTap: () => setState(() => _selectedCategory = category.id),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: products.isEmpty
              ? const Center(child: Text('Menu tidak ditemukan.'))
              : GridView.builder(
                  itemCount: products.length,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: MediaQuery.sizeOf(context).width > 1100
                        ? 4
                        : MediaQuery.sizeOf(context).width > 620
                        ? 3
                        : 2,
                    mainAxisSpacing: 10,
                    crossAxisSpacing: 10,
                    childAspectRatio: 1.08,
                  ),
                  itemBuilder: (context, index) {
                    final product = products[index];
                    return _ProductCard(
                      product: product,
                      onTap: product.available
                          ? () => _addProduct(product, catalog.modifierGroups)
                          : null,
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _cartPanel(PosCatalog catalog) {
    final tables = catalog.tables;
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Pesanan (${_cart.fold<int>(0, (n, line) => n + line.quantity)})',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (_cart.isNotEmpty)
                  TextButton(
                    onPressed: () => setState(_cart.clear),
                    child: const Text('Kosongkan'),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: DropdownButtonFormField<String>(
              initialValue: _orderType,
              decoration: const InputDecoration(
                labelText: 'Tipe pesanan',
                isDense: true,
              ),
              items: const [
                DropdownMenuItem(value: 'DINE_IN', child: Text('Dine In')),
                DropdownMenuItem(value: 'TAKE_AWAY', child: Text('Take Away')),
                DropdownMenuItem(
                  value: 'DELIVERY',
                  child: Text('Pesanan Online'),
                ),
              ],
              onChanged: (value) => setState(() {
                _orderType = value ?? 'DINE_IN';
                _selectedTableId = null;
                _selectedChannelId = null;
              }),
            ),
          ),
          if (_orderType == 'DINE_IN')
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
              child: DropdownButtonFormField<String>(
                initialValue: _selectedTableId,
                decoration: const InputDecoration(
                  labelText: 'Meja',
                  isDense: true,
                ),
                hint: const Text('Pilih meja'),
                items: [
                  for (final table in tables)
                    DropdownMenuItem(
                      value: table.id,
                      child: Text('Meja ${table.number}'),
                    ),
                ],
                onChanged: (value) => setState(() => _selectedTableId = value),
              ),
            ),
          if (_orderType == 'DELIVERY') ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
              child: DropdownButtonFormField<String>(
                initialValue: _selectedChannelId,
                decoration: const InputDecoration(
                  labelText: 'Channel',
                  isDense: true,
                ),
                hint: const Text('Pilih channel'),
                items: [
                  for (final channel in catalog.channels)
                    DropdownMenuItem(
                      value: channel.id,
                      child: Text(channel.name),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _selectedChannelId = value),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
              child: TextField(
                controller: _externalOrderController,
                decoration: const InputDecoration(
                  labelText: 'ID pesanan platform',
                  isDense: true,
                ),
              ),
            ),
          ],
          const Divider(height: 18),
          Expanded(
            child: _cart.isEmpty
                ? const Center(child: Text('Pilih menu untuk mulai.'))
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    itemCount: _cart.length,
                    separatorBuilder: (context, index) =>
                        const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final line = _cart[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          line.menu.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13),
                        ),
                        subtitle: Text(
                          [
                            if (line.variant != null) line.variant!.name,
                            ...line.modifiers.map((item) => item.name),
                          ].join(' · '),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: SizedBox(
                          width: 120,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.end,
                            children: [
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                onPressed: () => _changeQuantity(index, -1),
                                icon: const Icon(Icons.remove_circle_outline),
                              ),
                              Text('${line.quantity}'),
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                onPressed: () => _changeQuantity(index, 1),
                                icon: const Icon(Icons.add_circle_outline),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              children: [
                Row(
                  children: [
                    const Expanded(child: Text('Total')),
                    Text(
                      _rupiah(_total),
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _cart.isEmpty ? null : _checkout,
                    icon: const Icon(Icons.payments_outlined),
                    label: const Text('Bayar'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.product, required this.onTap});

  final MenuProduct product;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Center(
                  child: Icon(
                    Icons.coffee,
                    size: 38,
                    color: product.available
                        ? Theme.of(context).colorScheme.primary
                        : Colors.grey,
                  ),
                ),
              ),
              Text(
                product.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              Text(
                product.available ? _rupiah(product.price) : 'Habis',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: product.available
                      ? Theme.of(context).colorScheme.primary
                      : Theme.of(context).colorScheme.error,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  const _CategoryChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(right: 8),
    child: ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onTap(),
    ),
  );
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.message, required this.icon});

  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.secondaryContainer,
      borderRadius: BorderRadius.circular(10),
    ),
    child: Row(
      children: [
        Icon(icon, size: 18),
        const SizedBox(width: 8),
        Expanded(child: Text(message, style: const TextStyle(fontSize: 12))),
      ],
    ),
  );
}

class _PendingSyncBanner extends StatelessWidget {
  const _PendingSyncBanner({required this.orders, required this.onSync});

  final List<PendingOrder> orders;
  final VoidCallback onSync;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    decoration: BoxDecoration(
      color: const Color(0xfffff2dc),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Column(
      children: [
        Row(
          children: [
            const Icon(Icons.sync, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '${orders.length} pesanan menunggu sinkronisasi.',
                style: const TextStyle(fontSize: 12),
              ),
            ),
            TextButton(onPressed: onSync, child: const Text('Coba lagi')),
          ],
        ),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          title: const Text('Lihat transaksi tersimpan'),
          children: [
            for (final order in orders)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.receipt_long_outlined),
                title: Text(_pendingOrderSummary(order)),
                subtitle: order.lastError == null
                    ? Text(
                        'Tersimpan ${DateFormat('dd/MM/yyyy HH:mm').format(order.createdAt.toLocal())}',
                      )
                    : Text('Gagal sinkron: ${order.lastError}'),
              ),
          ],
        ),
      ],
    ),
  );
}

String _pendingOrderSummary(PendingOrder order) {
  try {
    final payload = jsonDecode(order.payload);
    if (payload is Map<String, dynamic>) {
      final type = payload['order_type'];
      final total = payload['total'];
      if (type is String && total is num) {
        return '$type • ${_rupiah(total)}';
      }
    }
  } on FormatException {
    return 'Data pesanan lokal tidak dapat dibaca';
  }
  return 'Pesanan lokal ${order.idempotencyKey}';
}

class _ProductOptionsDialog extends StatefulWidget {
  const _ProductOptionsDialog({required this.product, required this.groups});

  final MenuProduct product;
  final List<ModifierGroup> groups;

  @override
  State<_ProductOptionsDialog> createState() => _ProductOptionsDialogState();
}

class _ProductOptionsDialogState extends State<_ProductOptionsDialog> {
  MenuVariant? _variant;
  final Map<String, List<MenuModifier>> _selected = {};
  String? _error;

  @override
  void initState() {
    super.initState();
    _variant = widget.product.variants.firstOrNull;
  }

  void _toggle(ModifierGroup group, MenuModifier modifier, bool checked) {
    final selected = [...?_selected[group.name]];
    if (checked) {
      if (group.maxSelection > 0 && selected.length >= group.maxSelection) {
        setState(
          () => _error =
              'Maksimal ${group.maxSelection} pilihan untuk ${group.name}.',
        );
        return;
      }
      selected.add(modifier);
    } else {
      selected.removeWhere((item) => item.id == modifier.id);
    }
    setState(() {
      _selected[group.name] = selected;
      _error = null;
    });
  }

  void _add() {
    final missing = widget.groups.where((group) {
      return group.required &&
          (_selected[group.name]?.length ?? 0) < group.minSelection;
    });
    if (missing.isNotEmpty) {
      setState(() => _error = 'Pilih ${missing.first.name} terlebih dahulu.');
      return;
    }
    Navigator.of(context).pop(
      CartLine(
        menu: widget.product,
        variant: _variant,
        modifiers: _selected.values.expand((items) => items).toList(),
        quantity: 1,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.product.name),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (widget.product.variants.isNotEmpty) ...[
                const Text('Ukuran'),
                const SizedBox(height: 4),
                RadioGroup<MenuVariant>(
                  groupValue: _variant,
                  onChanged: (value) => setState(() => _variant = value),
                  child: Column(
                    children: [
                      for (final variant in widget.product.variants)
                        RadioListTile<MenuVariant>(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(variant.name),
                          subtitle: variant.priceAdjustment == 0
                              ? null
                              : Text('+${_rupiah(variant.priceAdjustment)}'),
                          value: variant,
                        ),
                    ],
                  ),
                ),
              ],
              for (final group in widget.groups) ...[
                const Divider(),
                Text(
                  group.required ? '${group.name} · Wajib' : group.name,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                for (final modifier in group.modifiers)
                  CheckboxListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(modifier.name),
                    subtitle: modifier.price == 0
                        ? null
                        : Text('+${_rupiah(modifier.price)}'),
                    value:
                        _selected[group.name]?.any(
                          (item) => item.id == modifier.id,
                        ) ??
                        false,
                    onChanged: (value) =>
                        _toggle(group, modifier, value ?? false),
                  ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Batal'),
        ),
        FilledButton(onPressed: _add, child: const Text('Tambah')),
      ],
    );
  }
}

class _PaymentSelection {
  const _PaymentSelection(this.method, this.amount);

  final String method;
  final double amount;
}

class _PaymentDialog extends StatefulWidget {
  const _PaymentDialog({required this.total});

  final double total;

  @override
  State<_PaymentDialog> createState() => _PaymentDialogState();
}

class _PaymentDialogState extends State<_PaymentDialog> {
  late final TextEditingController _amountController;
  String _method = 'TUNAI';
  bool _qrisReceived = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _amountController = TextEditingController(
      text: widget.total.toStringAsFixed(0),
    );
  }

  @override
  void dispose() {
    _amountController.dispose();
    super.dispose();
  }

  void _confirm() {
    final amount = _method == 'QRIS_STATIS'
        ? widget.total
        : double.tryParse(_amountController.text.replaceAll('.', '')) ?? 0;
    if (amount < widget.total) {
      setState(() => _error = 'Nominal pembayaran kurang dari total.');
      return;
    }
    if (_method == 'QRIS_STATIS' && !_qrisReceived) {
      setState(() => _error = 'Konfirmasikan dana QRIS telah masuk.');
      return;
    }
    Navigator.of(context).pop(_PaymentSelection(_method, amount));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Pembayaran'),
    content: SizedBox(
      width: 380,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Total ${_rupiah(widget.total)}'),
          const SizedBox(height: 16),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'TUNAI', label: Text('Tunai')),
              ButtonSegment(value: 'QRIS_STATIS', label: Text('QRIS')),
            ],
            selected: {_method},
            onSelectionChanged: (values) => setState(() {
              _method = values.first;
              _error = null;
            }),
          ),
          if (_method == 'TUNAI') ...[
            const SizedBox(height: 14),
            TextField(
              controller: _amountController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Uang diterima',
                prefixText: 'Rp ',
              ),
            ),
          ] else
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _qrisReceived,
              onChanged: (value) =>
                  setState(() => _qrisReceived = value ?? false),
              title: const Text('Dana QRIS sudah masuk'),
              subtitle: const Text(
                'Periksa bukti pembayaran sebelum konfirmasi.',
              ),
            ),
          if (_error != null)
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Batal'),
      ),
      FilledButton(onPressed: _confirm, child: const Text('Konfirmasi')),
    ],
  );
}

class _LoadError extends StatelessWidget {
  const _LoadError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_outlined, size: 44),
          const SizedBox(height: 12),
          const Text('Katalog belum tersedia di perangkat.'),
          const SizedBox(height: 6),
          Text(
            apiErrorMessage(error),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('Coba lagi')),
        ],
      ),
    ),
  );
}

String _rupiah(num amount) => NumberFormat.currency(
  locale: 'id_ID',
  symbol: 'Rp ',
  decimalDigits: 0,
).format(amount);
