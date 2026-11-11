import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../app/providers.dart';
import '../../data/api/api_client.dart';

final managementDataProvider = FutureProvider<ManagementData>((ref) async {
  final api = ref.watch(apiClientProvider);
  final role = ref.watch(authControllerProvider).session?.role;
  Future<List<Map<String, dynamic>>> list(String path) async {
    final response = await api.getData(path);
    return (response['items'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  return ManagementData(
    categories: await list('/categories'),
    menus: await list('/menus'),
    ingredients: await list('/ingredients'),
    units: await list('/units'),
    recipes: await list('/recipes'),
    expenseCategories: await list('/expense-categories'),
    tables: await list('/tables'),
    users: await list('/users'),
    devices: await list('/devices'),
    channels: await list('/channels'),
    auditLogs: role == 'super_admin' ? await list('/audit-logs') : const [],
    canAudit: role == 'super_admin',
  );
});

class ManagementData {
  const ManagementData({
    required this.categories,
    required this.menus,
    required this.ingredients,
    required this.units,
    required this.recipes,
    required this.expenseCategories,
    required this.tables,
    required this.users,
    required this.devices,
    required this.channels,
    required this.auditLogs,
    required this.canAudit,
  });

  final List<Map<String, dynamic>> categories;
  final List<Map<String, dynamic>> menus;
  final List<Map<String, dynamic>> ingredients;
  final List<Map<String, dynamic>> units;
  final List<Map<String, dynamic>> recipes;
  final List<Map<String, dynamic>> expenseCategories;
  final List<Map<String, dynamic>> tables;
  final List<Map<String, dynamic>> users;
  final List<Map<String, dynamic>> devices;
  final List<Map<String, dynamic>> channels;
  final List<Map<String, dynamic>> auditLogs;
  final bool canAudit;
}

class ManagementScreen extends ConsumerWidget {
  const ManagementScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(managementDataProvider);
    return data.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, stackTrace) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Data administrasi belum dapat dimuat.'),
              const SizedBox(height: 8),
              Text(apiErrorMessage(error), textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => ref.invalidate(managementDataProvider),
                child: const Text('Coba lagi'),
              ),
            ],
          ),
        ),
      ),
      data: (management) => _ManagementOverview(data: management),
    );
  }
}

class _ManagementOverview extends ConsumerWidget {
  const _ManagementOverview({required this.data});

  final ManagementData data;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.read(apiClientProvider);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(managementDataProvider.future),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Manajemen outlet',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              IconButton(
                tooltip: 'Muat ulang',
                onPressed: () => _refresh(ref),
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          _DataSection(
            title: 'Menu dan kategori',
            count:
                '${data.menus.length} menu · ${data.categories.length} kategori',
            actions: [
              _ActionButton(
                label: 'Kategori',
                onPressed: () => _createCategory(context, api, ref),
              ),
              _ActionButton(
                label: 'Menu',
                onPressed: () =>
                    _createMenu(context, api, ref, data.categories),
              ),
            ],
            children: [
              for (final item in data.menus)
                _RecordRow(
                  title: item['name'] as String? ?? 'Menu',
                  subtitle: item['category_name'] as String? ?? '',
                  trailing: Text(
                    _rupiah((item['base_price'] as num?)?.toDouble() ?? 0),
                  ),
                ),
            ],
          ),
          _DataSection(
            title: 'Bahan baku dan resep',
            count:
                '${data.ingredients.length} bahan · ${data.recipes.length} resep',
            actions: [
              _ActionButton(
                label: 'Tambah bahan',
                onPressed: data.units.isEmpty
                    ? null
                    : () => _createIngredient(context, api, ref, data.units),
              ),
              _ActionButton(
                label: 'Pembelian',
                onPressed: data.ingredients.isEmpty
                    ? null
                    : () =>
                          _createPurchase(context, api, ref, data.ingredients),
              ),
              _ActionButton(
                label: 'Stok opname',
                onPressed: data.ingredients.isEmpty
                    ? null
                    : () => _createStockOpname(
                        context,
                        api,
                        ref,
                        data.ingredients,
                      ),
              ),
              _ActionButton(
                label: 'Penyesuaian stok',
                onPressed: data.ingredients.isEmpty
                    ? null
                    : () => _stockMovement(context, api, ref, data.ingredients),
              ),
              _ActionButton(
                label: 'Resep',
                onPressed: data.ingredients.isEmpty || data.menus.isEmpty
                    ? null
                    : () => _createRecipe(
                        context,
                        api,
                        ref,
                        data.menus,
                        data.ingredients,
                      ),
              ),
            ],
            children: [
              for (final item in data.ingredients)
                _RecordRow(
                  title: item['name'] as String? ?? 'Bahan',
                  subtitle:
                      'Stok ${item['current_stock'] ?? 0} ${item['unit_symbol'] ?? ''}'
                      '${item['is_low_stock'] == true ? ' · Menipis' : ''}',
                  trailing: Text(
                    _rupiah(
                      (item['last_purchase_price'] as num?)?.toDouble() ?? 0,
                    ),
                  ),
                  warning: item['is_low_stock'] == true,
                ),
              for (final item in data.recipes)
                _RecordRow(
                  title: item['menu_name'] as String? ?? 'Resep',
                  subtitle:
                      '${(item['items'] as List<dynamic>? ?? []).length} bahan',
                  trailing: Text(
                    'HPP ${_rupiah((item['cogs'] as num?)?.toDouble() ?? 0)}',
                  ),
                ),
            ],
          ),
          _DataSection(
            title: 'Satuan bahan baku',
            count: '${data.units.length} satuan',
            actions: [
              _ActionButton(
                label: 'Tambah satuan',
                onPressed: () => _createUnit(context, api, ref),
              ),
            ],
            children: [
              for (final unit in data.units)
                _RecordRow(
                  title: unit['name'] as String? ?? 'Satuan',
                  subtitle: unit['symbol'] as String? ?? '',
                  trailing: const SizedBox.shrink(),
                ),
            ],
          ),
          _DataSection(
            title: 'Kategori pengeluaran',
            count: '${data.expenseCategories.length} kategori',
            actions: [
              _ActionButton(
                label: 'Tambah kategori',
                onPressed: () => _createExpenseCategory(context, api, ref),
              ),
            ],
            children: [
              for (final category in data.expenseCategories)
                _RecordRow(
                  title: category['name'] as String? ?? 'Kategori',
                  subtitle: category['description'] as String? ?? '',
                  trailing: const SizedBox.shrink(),
                ),
            ],
          ),
          _DataSection(
            title: 'Meja dan QR',
            count: '${data.tables.length} meja',
            actions: [
              _ActionButton(
                label: 'Tambah meja',
                onPressed: () => _createTable(context, api, ref),
              ),
            ],
            children: [
              for (final table in data.tables)
                _RecordRow(
                  title: 'Meja ${table['table_number'] ?? ''}',
                  subtitle: table['is_active'] == true
                      ? 'Aktif'
                      : 'Tidak aktif',
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        tooltip: 'Tampilkan QR meja',
                        icon: const Icon(Icons.qr_code_2),
                        onPressed: table['qr_token'] is String
                            ? () => _showQr(
                                context,
                                table['qr_token'] as String,
                                '${table['table_number']}',
                              )
                            : null,
                      ),
                      IconButton(
                        tooltip: 'Buat ulang token QR',
                        icon: const Icon(Icons.refresh),
                        onPressed: () => _regenerateToken(
                          context,
                          api,
                          ref,
                          table['id'] as String,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          _DataSection(
            title: 'Pengguna dan perangkat',
            count:
                '${data.users.length} pengguna · ${data.devices.length} perangkat',
            actions: [
              _ActionButton(
                label: 'Tambah pengguna',
                onPressed: () => _createUser(context, api, ref),
              ),
            ],
            children: [
              for (final user in data.users)
                _RecordRow(
                  title: user['name'] as String? ?? 'Pengguna',
                  subtitle:
                      '@${user['username'] ?? ''} · ${user['role'] ?? ''}',
                  trailing: Text(
                    user['is_active'] == true ? 'Aktif' : 'Nonaktif',
                  ),
                ),
              for (final device in data.devices)
                _RecordRow(
                  title: device['device_name'] as String? ?? 'Perangkat',
                  subtitle: device['user_name'] as String? ?? '',
                  trailing: device['is_revoked'] == true
                      ? const Text('Dicabut')
                      : TextButton(
                          onPressed: () => _revokeDevice(
                            context,
                            api,
                            ref,
                            device['id'] as String,
                          ),
                          child: const Text('Cabut akses'),
                        ),
                ),
            ],
          ),
          _DataSection(
            title: 'Channel pesanan',
            count: '${data.channels.length} channel',
            actions: [
              _ActionButton(
                label: 'Tambah channel',
                onPressed: () => _createChannel(context, api, ref),
              ),
            ],
            children: [
              for (final channel in data.channels)
                _RecordRow(
                  title: channel['name'] as String? ?? 'Channel',
                  subtitle: channel['code'] as String? ?? '',
                  trailing: Text(
                    '${channel['commission_percent'] ?? 0}% komisi',
                  ),
                ),
            ],
          ),
          if (data.canAudit)
            _DataSection(
              title: 'Audit log',
              count: '${data.auditLogs.length} catatan terbaru',
              children: [
                for (final item in data.auditLogs.take(15))
                  _RecordRow(
                    title: item['action'] as String? ?? 'Aksi',
                    subtitle:
                        '${item['entity'] ?? ''} · ${item['created_at'] ?? ''}',
                    trailing: Text(item['user_name'] as String? ?? ''),
                  ),
              ],
            ),
        ],
      ),
    );
  }

  Future<void> _createCategory(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final name = await _askText(context, 'Kategori baru', 'Nama kategori');
    if (name == null || !context.mounted) return;
    await _run(context, api.postData('/categories', body: {'name': name}), ref);
  }

  Future<void> _createMenu(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> categories,
  ) async {
    if (categories.isEmpty) {
      _notify(context, 'Buat kategori terlebih dahulu.');
      return;
    }

    final result = await showDialog<_MenuInput>(
      context: context,
      builder: (context) => _MenuDialog(categories: categories),
    );
    if (result == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/menus',
        body: {
          'name': result.name,
          'category_id': result.categoryId,
          'description': result.description,
          'base_price': result.price,
        },
      ),
      ref,
    );
  }

  Future<void> _createUnit(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final name = await _askText(context, 'Satuan baru', 'Nama satuan');
    if (name == null || !context.mounted) return;
    final symbol = await _askText(
      context,
      'Simbol satuan',
      'Contoh: g, ml, pcs',
    );
    if (symbol == null || !context.mounted) return;
    await _run(
      context,
      api.postData('/units', body: {'name': name, 'symbol': symbol}),
      ref,
    );
  }

  Future<void> _createIngredient(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> units,
  ) async {
    final input = await showDialog<_IngredientInput>(
      context: context,
      builder: (context) => _IngredientDialog(units: units),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/ingredients',
        body: {
          'name': input.name,
          'unit_id': input.unitId,
          'min_stock': input.minStock,
          'last_purchase_price': input.lastPurchasePrice,
        },
      ),
      ref,
    );
  }

  Future<void> _createExpenseCategory(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final name = await _askText(
      context,
      'Kategori pengeluaran',
      'Nama kategori',
    );
    if (name == null || !context.mounted) return;
    await _run(
      context,
      api.postData('/expense-categories', body: {'name': name}),
      ref,
    );
  }

  Future<void> _createPurchase(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> ingredients,
  ) async {
    final input = await showDialog<_PurchaseInput>(
      context: context,
      builder: (context) => _PurchaseDialog(ingredients: ingredients),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/purchases',
        body: {
          'supplier_name': input.supplier,
          'invoice_no': input.invoiceNumber,
          'notes': input.notes,
          'items': [
            {
              'ingredient_id': input.ingredientId,
              'quantity': input.quantity,
              'unit_price': input.unitPrice,
            },
          ],
        },
      ),
      ref,
    );
  }

  Future<void> _createStockOpname(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> ingredients,
  ) async {
    final input = await showDialog<_OpnameInput>(
      context: context,
      builder: (context) => _StockOpnameDialog(ingredients: ingredients),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/stock/opname',
        body: {
          'notes': input.notes,
          'items': [
            {
              'ingredient_id': input.ingredientId,
              'actual_stock': input.actualStock,
            },
          ],
        },
      ),
      ref,
    );
  }

  Future<void> _createTable(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final number = await _askText(context, 'Meja baru', 'Nomor meja');
    if (number == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/tables',
        body: {'table_number': number, 'name': 'Meja $number'},
      ),
      ref,
    );
  }

  Future<void> _regenerateToken(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    String id,
  ) async {
    final confirm = await _confirm(
      context,
      'Token QR lama tidak akan berlaku lagi. Lanjutkan?',
    );
    if (!confirm || !context.mounted) return;
    try {
      final result = await api.postData('/tables/$id/regenerate-token');
      _refresh(ref);
      final token = result['new_qr_token'];
      if (context.mounted && token is String) {
        await _showQr(context, token, 'Meja');
      }
    } on Exception catch (error) {
      if (context.mounted) _notify(context, apiErrorMessage(error));
    }
  }

  Future<void> _createUser(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final result = await showDialog<_UserInput>(
      context: context,
      builder: (context) => const _UserDialog(),
    );
    if (result == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/users',
        body: {
          'name': result.name,
          'username': result.username,
          'password': result.password,
          'pin': result.pin,
          'role': result.role,
        },
      ),
      ref,
    );
  }

  Future<void> _revokeDevice(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    String id,
  ) async {
    if (!await _confirm(context, 'Cabut akses perangkat ini?') ||
        !context.mounted) {
      return;
    }
    try {
      await api.dio.delete('/devices/$id');
      _refresh(ref);
    } on Exception catch (error) {
      if (context.mounted) _notify(context, apiErrorMessage(error));
    }
  }

  Future<void> _createChannel(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
  ) async {
    final input = await showDialog<_ChannelInput>(
      context: context,
      builder: (context) => const _ChannelDialog(),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/channels',
        body: {
          'name': input.name,
          'code': input.code,
          'commission_percent': input.commission,
        },
      ),
      ref,
    );
  }

  Future<void> _stockMovement(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> ingredients,
  ) async {
    final input = await showDialog<_StockInput>(
      context: context,
      builder: (context) => _StockDialog(ingredients: ingredients),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/stock/movements',
        body: {
          'ingredient_id': input.ingredientId,
          'type': input.type,
          'quantity': input.type == 'WASTE' ? -input.quantity : input.quantity,
          'notes': input.notes,
        },
      ),
      ref,
    );
  }

  Future<void> _createRecipe(
    BuildContext context,
    ApiClient api,
    WidgetRef ref,
    List<Map<String, dynamic>> menus,
    List<Map<String, dynamic>> ingredients,
  ) async {
    final input = await showDialog<_RecipeInput>(
      context: context,
      builder: (context) =>
          _RecipeDialog(menus: menus, ingredients: ingredients),
    );
    if (input == null || !context.mounted) return;
    await _run(
      context,
      api.postData(
        '/recipes',
        body: {
          'menu_id': input.menuId,
          'items': [
            {'ingredient_id': input.ingredientId, 'quantity': input.quantity},
          ],
        },
      ),
      ref,
    );
  }

  Future<void> _showQr(
    BuildContext context,
    String token,
    String tableNumber,
  ) async {
    const configuredBaseUrl = String.fromEnvironment(
      'QR_MENU_BASE_URL',
      defaultValue: 'http://localhost:5173',
    );
    final qrUrl = '${configuredBaseUrl.replaceAll(RegExp(r'/+$'), '')}/$token';
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('QR Menu · $tableNumber'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            QrImageView(data: qrUrl, size: 220),
            SelectableText(qrUrl, textAlign: TextAlign.center),
            if (configuredBaseUrl.contains('localhost'))
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  'Atur QR_MENU_BASE_URL ke alamat web yang dapat dibuka pelanggan sebelum mencetak QR.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12),
                ),
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Tutup'),
          ),
        ],
      ),
    );
  }

  Future<void> _run(
    BuildContext context,
    Future<Map<String, dynamic>> action,
    WidgetRef ref,
  ) async {
    try {
      await action;
      _refresh(ref);
      if (context.mounted) _notify(context, 'Perubahan berhasil disimpan.');
    } on Exception catch (error) {
      if (context.mounted) _notify(context, apiErrorMessage(error));
    }
  }

  void _refresh(WidgetRef ref) => ref.invalidate(managementDataProvider);
}

class _DataSection extends StatelessWidget {
  const _DataSection({
    required this.title,
    required this.count,
    required this.children,
    this.actions = const [],
  });

  final String title;
  final String count;
  final List<Widget> children;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(top: 10),
    child: ExpansionTile(
      initiallyExpanded: true,
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(count),
      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      children: [
        if (actions.isNotEmpty)
          Wrap(spacing: 8, runSpacing: 6, children: actions),
        if (children.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('Belum ada data.'),
          ),
        for (final child in children) child,
      ],
    ),
  );
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) =>
      OutlinedButton(onPressed: onPressed, child: Text(label));
}

class _RecordRow extends StatelessWidget {
  const _RecordRow({
    required this.title,
    required this.subtitle,
    required this.trailing,
    this.warning = false,
  });

  final String title;
  final String subtitle;
  final Widget trailing;
  final bool warning;

  @override
  Widget build(BuildContext context) => ListTile(
    dense: true,
    contentPadding: EdgeInsets.zero,
    title: Text(title),
    subtitle: subtitle.isEmpty ? null : Text(subtitle),
    trailing: trailing,
    leading: warning
        ? Icon(Icons.warning_amber, color: Theme.of(context).colorScheme.error)
        : null,
  );
}

class _MenuInput {
  const _MenuInput(this.name, this.categoryId, this.description, this.price);
  final String name;
  final String categoryId;
  final String description;
  final double price;
}

class _MenuDialog extends StatefulWidget {
  const _MenuDialog({required this.categories});
  final List<Map<String, dynamic>> categories;

  @override
  State<_MenuDialog> createState() => _MenuDialogState();
}

class _MenuDialogState extends State<_MenuDialog> {
  final _name = TextEditingController();
  final _description = TextEditingController();
  final _price = TextEditingController();
  String? _categoryId;

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tambah menu'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Nama menu'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _categoryId,
            decoration: const InputDecoration(labelText: 'Kategori'),
            items: [
              for (final item in widget.categories)
                DropdownMenuItem(
                  value: item['id'] as String,
                  child: Text(item['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _categoryId = value),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _description,
            decoration: const InputDecoration(labelText: 'Deskripsi'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _price,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Harga',
              prefixText: 'Rp ',
            ),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final price = double.tryParse(_price.text.replaceAll('.', '')) ?? 0;
          if (_name.text.trim().isNotEmpty &&
              _categoryId != null &&
              price > 0) {
            Navigator.pop(
              context,
              _MenuInput(
                _name.text.trim(),
                _categoryId!,
                _description.text.trim(),
                price,
              ),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _UserInput {
  const _UserInput(
    this.name,
    this.username,
    this.password,
    this.pin,
    this.role,
  );
  final String name;
  final String username;
  final String password;
  final String pin;
  final String role;
}

class _UserDialog extends StatefulWidget {
  const _UserDialog();

  @override
  State<_UserDialog> createState() => _UserDialogState();
}

class _UserDialogState extends State<_UserDialog> {
  final _name = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _pin = TextEditingController();
  String _role = 'kasir';

  @override
  void dispose() {
    _name.dispose();
    _username.dispose();
    _password.dispose();
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tambah pengguna'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Nama'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _username,
            decoration: const InputDecoration(labelText: 'Username'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _password,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Password'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _pin,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'PIN 6 digit'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _role,
            decoration: const InputDecoration(labelText: 'Role'),
            items: const [
              DropdownMenuItem(value: 'kasir', child: Text('Kasir')),
              DropdownMenuItem(value: 'admin', child: Text('Admin/Owner')),
              DropdownMenuItem(
                value: 'super_admin',
                child: Text('Super Admin'),
              ),
            ],
            onChanged: (value) => setState(() => _role = value ?? 'kasir'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          if (_name.text.trim().isNotEmpty &&
              _username.text.trim().isNotEmpty &&
              _password.text.isNotEmpty &&
              (_pin.text.isEmpty || _pin.text.length == 6)) {
            Navigator.pop(
              context,
              _UserInput(
                _name.text.trim(),
                _username.text.trim(),
                _password.text,
                _pin.text,
                _role,
              ),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _ChannelInput {
  const _ChannelInput(this.name, this.code, this.commission);
  final String name;
  final String code;
  final double commission;
}

class _ChannelDialog extends StatefulWidget {
  const _ChannelDialog();

  @override
  State<_ChannelDialog> createState() => _ChannelDialogState();
}

class _ChannelDialogState extends State<_ChannelDialog> {
  final _name = TextEditingController();
  final _code = TextEditingController();
  final _commission = TextEditingController(text: '0');

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    _commission.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tambah channel'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Nama'),
        ),
        TextField(
          controller: _code,
          decoration: const InputDecoration(labelText: 'Kode'),
        ),
        TextField(
          controller: _commission,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Komisi (%)'),
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final commission = double.tryParse(_commission.text) ?? 0;
          if (_name.text.trim().isNotEmpty && _code.text.trim().isNotEmpty) {
            Navigator.pop(
              context,
              _ChannelInput(_name.text.trim(), _code.text.trim(), commission),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _StockInput {
  const _StockInput(this.ingredientId, this.type, this.quantity, this.notes);
  final String ingredientId;
  final String type;
  final double quantity;
  final String notes;
}

class _StockDialog extends StatefulWidget {
  const _StockDialog({required this.ingredients});
  final List<Map<String, dynamic>> ingredients;

  @override
  State<_StockDialog> createState() => _StockDialogState();
}

class _StockDialogState extends State<_StockDialog> {
  final _quantity = TextEditingController();
  final _notes = TextEditingController();
  String? _ingredientId;
  String _type = 'ADJUSTMENT';

  @override
  void dispose() {
    _quantity.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Penyesuaian stok'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _ingredientId,
            decoration: const InputDecoration(labelText: 'Bahan baku'),
            items: [
              for (final item in widget.ingredients)
                DropdownMenuItem(
                  value: item['id'] as String,
                  child: Text(item['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _ingredientId = value),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _type,
            decoration: const InputDecoration(labelText: 'Jenis'),
            items: const [
              DropdownMenuItem(value: 'ADJUSTMENT', child: Text('Penyesuaian')),
              DropdownMenuItem(value: 'WASTE', child: Text('Waste')),
            ],
            onChanged: (value) => setState(() => _type = value ?? 'ADJUSTMENT'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _quantity,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Jumlah'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _notes,
            decoration: const InputDecoration(labelText: 'Catatan'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final quantity = double.tryParse(_quantity.text) ?? 0;
          if (_ingredientId != null && quantity > 0) {
            Navigator.pop(
              context,
              _StockInput(_ingredientId!, _type, quantity, _notes.text.trim()),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _RecipeInput {
  const _RecipeInput(this.menuId, this.ingredientId, this.quantity);
  final String menuId;
  final String ingredientId;
  final double quantity;
}

class _RecipeDialog extends StatefulWidget {
  const _RecipeDialog({required this.menus, required this.ingredients});
  final List<Map<String, dynamic>> menus;
  final List<Map<String, dynamic>> ingredients;

  @override
  State<_RecipeDialog> createState() => _RecipeDialogState();
}

class _RecipeDialogState extends State<_RecipeDialog> {
  final _quantity = TextEditingController();
  String? _menuId;
  String? _ingredientId;

  @override
  void dispose() {
    _quantity.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tambahkan bahan ke resep'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _menuId,
            decoration: const InputDecoration(labelText: 'Menu'),
            items: [
              for (final item in widget.menus)
                DropdownMenuItem(
                  value: item['id'] as String,
                  child: Text(item['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _menuId = value),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _ingredientId,
            decoration: const InputDecoration(labelText: 'Bahan baku'),
            items: [
              for (final item in widget.ingredients)
                DropdownMenuItem(
                  value: item['id'] as String,
                  child: Text(item['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _ingredientId = value),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _quantity,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Kuantitas bahan'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final quantity = double.tryParse(_quantity.text) ?? 0;
          if (_menuId != null && _ingredientId != null && quantity > 0) {
            Navigator.pop(
              context,
              _RecipeInput(_menuId!, _ingredientId!, quantity),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _IngredientInput {
  const _IngredientInput(
    this.name,
    this.unitId,
    this.minStock,
    this.lastPurchasePrice,
  );

  final String name;
  final String unitId;
  final double minStock;
  final double lastPurchasePrice;
}

class _IngredientDialog extends StatefulWidget {
  const _IngredientDialog({required this.units});

  final List<Map<String, dynamic>> units;

  @override
  State<_IngredientDialog> createState() => _IngredientDialogState();
}

class _IngredientDialogState extends State<_IngredientDialog> {
  final _name = TextEditingController();
  final _minimum = TextEditingController(text: '0');
  final _price = TextEditingController(text: '0');
  String? _unitId;

  @override
  void dispose() {
    _name.dispose();
    _minimum.dispose();
    _price.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tambah bahan baku'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Nama bahan'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _unitId,
            decoration: const InputDecoration(labelText: 'Satuan'),
            items: [
              for (final unit in widget.units)
                DropdownMenuItem(
                  value: unit['id'] as String,
                  child: Text('${unit['name']} (${unit['symbol']})'),
                ),
            ],
            onChanged: (value) => setState(() => _unitId = value),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _minimum,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Stok minimum'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _price,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Harga beli terakhir',
              prefixText: 'Rp ',
            ),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final minimum = double.tryParse(_minimum.text.replaceAll(',', '.'));
          final price = double.tryParse(_price.text.replaceAll(',', '.'));
          if (_name.text.trim().isNotEmpty &&
              _unitId != null &&
              minimum != null &&
              minimum >= 0 &&
              price != null &&
              price >= 0) {
            Navigator.pop(
              context,
              _IngredientInput(_name.text.trim(), _unitId!, minimum, price),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _PurchaseInput {
  const _PurchaseInput({
    required this.ingredientId,
    required this.quantity,
    required this.unitPrice,
    required this.supplier,
    required this.invoiceNumber,
    required this.notes,
  });

  final String ingredientId;
  final double quantity;
  final double unitPrice;
  final String supplier;
  final String invoiceNumber;
  final String notes;
}

class _PurchaseDialog extends StatefulWidget {
  const _PurchaseDialog({required this.ingredients});

  final List<Map<String, dynamic>> ingredients;

  @override
  State<_PurchaseDialog> createState() => _PurchaseDialogState();
}

class _PurchaseDialogState extends State<_PurchaseDialog> {
  final _quantity = TextEditingController();
  final _price = TextEditingController();
  final _supplier = TextEditingController();
  final _invoice = TextEditingController();
  String? _ingredientId;

  @override
  void dispose() {
    _quantity.dispose();
    _price.dispose();
    _supplier.dispose();
    _invoice.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Catat pembelian bahan'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _ingredientId,
            decoration: const InputDecoration(labelText: 'Bahan baku'),
            items: [
              for (final ingredient in widget.ingredients)
                DropdownMenuItem(
                  value: ingredient['id'] as String,
                  child: Text(ingredient['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _ingredientId = value),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _quantity,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Kuantitas'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _price,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Harga per satuan',
              prefixText: 'Rp ',
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _supplier,
            decoration: const InputDecoration(labelText: 'Pemasok (opsional)'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _invoice,
            decoration: const InputDecoration(
              labelText: 'Nomor invoice (opsional)',
            ),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final quantity = double.tryParse(_quantity.text.replaceAll(',', '.'));
          final price = double.tryParse(_price.text.replaceAll(',', '.'));
          if (_ingredientId != null &&
              quantity != null &&
              quantity > 0 &&
              price != null &&
              price >= 0) {
            Navigator.pop(
              context,
              _PurchaseInput(
                ingredientId: _ingredientId!,
                quantity: quantity,
                unitPrice: price,
                supplier: _supplier.text.trim(),
                invoiceNumber: _invoice.text.trim(),
                notes: '',
              ),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _OpnameInput {
  const _OpnameInput(this.ingredientId, this.actualStock, this.notes);

  final String ingredientId;
  final double actualStock;
  final String notes;
}

class _StockOpnameDialog extends StatefulWidget {
  const _StockOpnameDialog({required this.ingredients});

  final List<Map<String, dynamic>> ingredients;

  @override
  State<_StockOpnameDialog> createState() => _StockOpnameDialogState();
}

class _StockOpnameDialogState extends State<_StockOpnameDialog> {
  final _actualStock = TextEditingController();
  final _notes = TextEditingController();
  String? _ingredientId;

  @override
  void dispose() {
    _actualStock.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Stok opname'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _ingredientId,
            decoration: const InputDecoration(labelText: 'Bahan baku'),
            items: [
              for (final ingredient in widget.ingredients)
                DropdownMenuItem(
                  value: ingredient['id'] as String,
                  child: Text(ingredient['name'] as String? ?? ''),
                ),
            ],
            onChanged: (value) => setState(() => _ingredientId = value),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _actualStock,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Stok fisik'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _notes,
            decoration: const InputDecoration(labelText: 'Catatan (opsional)'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Batal'),
      ),
      FilledButton(
        onPressed: () {
          final stock = double.tryParse(_actualStock.text.replaceAll(',', '.'));
          if (_ingredientId != null && stock != null && stock >= 0) {
            Navigator.pop(
              context,
              _OpnameInput(_ingredientId!, stock, _notes.text.trim()),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

Future<String?> _askText(
  BuildContext context,
  String title,
  String label,
) async {
  final controller = TextEditingController();
  final result = await showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: InputDecoration(labelText: label),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Batal'),
        ),
        FilledButton(
          onPressed: () {
            if (controller.text.trim().isNotEmpty) {
              Navigator.pop(context, controller.text.trim());
            }
          },
          child: const Text('Simpan'),
        ),
      ],
    ),
  );
  controller.dispose();
  return result;
}

Future<bool> _confirm(BuildContext context, String message) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Batal'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Lanjutkan'),
          ),
        ],
      ),
    ) ??
    false;

void _notify(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

String _rupiah(num amount) => NumberFormat.currency(
  locale: 'id_ID',
  symbol: 'Rp ',
  decimalDigits: 0,
).format(amount);
