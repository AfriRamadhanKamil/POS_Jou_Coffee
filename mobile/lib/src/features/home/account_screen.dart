import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/providers.dart';
import '../../data/api/api_client.dart';

final accountDataProvider = FutureProvider<AccountData>((ref) async {
  final api = ref.watch(apiClientProvider);
  final shift = await api.getData('/shifts/current');
  final expenses = await api.getData('/expenses');
  return AccountData(
    shift: shift.isEmpty ? null : shift,
    expenses: (expenses['items'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList(),
  );
});

class AccountData {
  const AccountData({required this.shift, required this.expenses});

  final Map<String, dynamic>? shift;
  final List<Map<String, dynamic>> expenses;
}

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(accountDataProvider);
    return data.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, stackTrace) => _AccountError(
        error: error,
        onRetry: () => ref.invalidate(accountDataProvider),
      ),
      data: (account) => RefreshIndicator(
        onRefresh: () => ref.refresh(accountDataProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Kas dan pengeluaran',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            _ShiftCard(
              shift: account.shift,
              onChanged: () => ref.invalidate(accountDataProvider),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            'Pengeluaran terbaru',
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        IconButton(
                          tooltip: 'Muat ulang',
                          onPressed: () => ref.invalidate(accountDataProvider),
                          icon: const Icon(Icons.refresh),
                        ),
                      ],
                    ),
                    if (account.expenses.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Text('Belum ada pengeluaran.'),
                      )
                    else
                      for (final expense in account.expenses.take(10))
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const CircleAvatar(
                            child: Icon(Icons.receipt_long_outlined),
                          ),
                          title: Text(
                            expense['category_name'] as String? ?? 'Pengeluaran',
                          ),
                          subtitle: Text(
                            expense['notes'] as String? ?? 'Tanpa catatan',
                          ),
                          trailing: Text(
                            _rupiah((expense['amount'] as num?)?.toDouble() ?? 0),
                          ),
                        ),
                    const Divider(),
                    const Text(
                      'Pencatatan pengeluaran memerlukan kategori. Backend saat ini belum menyediakan endpoint daftar kategori pengeluaran.',
                      style: TextStyle(fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ShiftCard extends ConsumerWidget {
  const _ShiftCard({required this.shift, required this.onChanged});

  final Map<String, dynamic>? shift;
  final VoidCallback onChanged;

  Future<void> _openShift(BuildContext context, WidgetRef ref) async {
    final amount = await _askAmount(context, 'Modal awal shift');
    if (amount == null) return;
    try {
      await ref.read(apiClientProvider).postData(
        '/shifts/open',
        body: {'starting_cash': amount},
      );
      onChanged();
    } on Exception catch (error) {
      if (context.mounted) _showError(context, apiErrorMessage(error));
    }
  }

  Future<void> _closeShift(BuildContext context, WidgetRef ref) async {
    final id = shift?['id'];
    if (id is! String) return;
    final amount = await _askAmount(context, 'Uang kas saat tutup shift');
    if (amount == null) return;
    try {
      final result = await ref.read(apiClientProvider).postData(
        '/shifts/$id/close',
        body: {'ending_cash_actual': amount},
      );
      onChanged();
      if (context.mounted) {
        showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Shift ditutup'),
            content: Text(
              'Kas sistem ${_rupiah((result['ending_cash_expected'] as num?)?.toDouble() ?? 0)}\n'
              'Selisih ${_rupiah((result['cash_difference'] as num?)?.toDouble() ?? 0)}',
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
    } on Exception catch (error) {
      if (context.mounted) _showError(context, apiErrorMessage(error));
    }
  }

  Future<double?> _askAmount(BuildContext context, String title) async {
    final controller = TextEditingController();
    final value = await showDialog<double>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Nominal', prefixText: 'Rp '),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Batal'),
          ),
          FilledButton(
            onPressed: () {
              final amount =
                  double.tryParse(controller.text.replaceAll('.', '')) ?? 0;
              if (amount > 0) Navigator.pop(context, amount);
            },
            child: const Text('Simpan'),
          ),
        ],
      ),
    );
    controller.dispose();
    return value;
  }

  Future<void> _recordMovement(BuildContext context, WidgetRef ref) async {
    final currentShiftId = shift?['id'];
    if (currentShiftId is! String) return;
    final movement = await showDialog<_CashMovement>(
      context: context,
      builder: (context) => const _CashMovementDialog(),
    );
    if (movement == null) return;
    try {
      await ref.read(apiClientProvider).postData(
        '/cash-movements',
        body: {
          'shift_id': currentShiftId,
          'type': movement.type,
          'amount': movement.amount,
          'notes': movement.notes,
        },
      );
      onChanged();
    } on Exception catch (error) {
      if (context.mounted) _showError(context, apiErrorMessage(error));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final opened = shift != null;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.point_of_sale_outlined),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    opened ? 'Shift sedang berjalan' : 'Belum ada shift aktif',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Chip(
                  label: Text(opened ? 'OPEN' : 'CLOSED'),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            if (opened) ...[
              const SizedBox(height: 8),
              _ValueRow(
                label: 'Kas yang diharapkan',
                value: _rupiah(
                  (shift!['expected_cash_drawer'] as num?)?.toDouble() ?? 0,
                ),
              ),
              _ValueRow(
                label: 'Modal awal',
                value: _rupiah(
                  (shift!['starting_cash'] as num?)?.toDouble() ?? 0,
                ),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!opened)
                  FilledButton.icon(
                    onPressed: () => _openShift(context, ref),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Buka shift'),
                  ),
                if (opened) ...[
                  OutlinedButton.icon(
                    onPressed: () => _recordMovement(context, ref),
                    icon: const Icon(Icons.swap_vert),
                    label: const Text('Kas masuk/keluar'),
                  ),
                  FilledButton.icon(
                    onPressed: () => _closeShift(context, ref),
                    icon: const Icon(Icons.stop),
                    label: const Text('Tutup shift'),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CashMovement {
  const _CashMovement(this.type, this.amount, this.notes);

  final String type;
  final double amount;
  final String notes;
}

class _CashMovementDialog extends StatefulWidget {
  const _CashMovementDialog();

  @override
  State<_CashMovementDialog> createState() => _CashMovementDialogState();
}

class _CashMovementDialogState extends State<_CashMovementDialog> {
  final _amount = TextEditingController();
  final _notes = TextEditingController();
  String _type = 'CASH_IN';

  @override
  void dispose() {
    _amount.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Kas masuk / keluar'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _type,
          items: const [
            DropdownMenuItem(value: 'CASH_IN', child: Text('Kas masuk')),
            DropdownMenuItem(value: 'CASH_OUT', child: Text('Kas keluar')),
          ],
          onChanged: (value) => setState(() => _type = value ?? 'CASH_IN'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _amount,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Nominal', prefixText: 'Rp '),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          decoration: const InputDecoration(labelText: 'Catatan'),
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
          final amount = double.tryParse(_amount.text.replaceAll('.', '')) ?? 0;
          if (amount > 0) {
            Navigator.pop(
              context,
              _CashMovement(_type, amount, _notes.text.trim()),
            );
          }
        },
        child: const Text('Simpan'),
      ),
    ],
  );
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    ),
  );
}

class _AccountError extends StatelessWidget {
  const _AccountError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Data kas belum dapat dimuat.'),
          const SizedBox(height: 8),
          Text(apiErrorMessage(error), textAlign: TextAlign.center),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('Coba lagi')),
        ],
      ),
    ),
  );
}

void _showError(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(message)),
  );
}

String _rupiah(num amount) =>
    NumberFormat.currency(locale: 'id_ID', symbol: 'Rp ', decimalDigits: 0)
        .format(amount);
