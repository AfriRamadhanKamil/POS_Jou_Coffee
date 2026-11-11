import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/providers.dart';
import '../../data/api/api_client.dart';

final pendingQrOrdersProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) async {
    final response = await ref
        .watch(apiClientProvider)
        .getData('/orders/pending-approval');
    return (response['items'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
  },
);

class OrdersScreen extends ConsumerWidget {
  const OrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orders = ref.watch(pendingQrOrdersProvider);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(pendingQrOrdersProvider.future),
      child: orders.when(
        loading: () => ListView(
          children: [
            SizedBox(height: 220),
            Center(child: CircularProgressIndicator()),
          ],
        ),
        error: (error, stackTrace) => ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 90),
            const Icon(Icons.cloud_off_outlined, size: 44),
            const SizedBox(height: 12),
            const Center(child: Text('Inbox pesanan QR belum dapat dimuat.')),
            const SizedBox(height: 8),
            Center(
              child: Text(
                apiErrorMessage(error),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: OutlinedButton(
                onPressed: () => ref.invalidate(pendingQrOrdersProvider),
                child: const Text('Coba lagi'),
              ),
            ),
          ],
        ),
        data: (items) => items.isEmpty
            ? ListView(
                padding: const EdgeInsets.all(24),
                children: const [
                  SizedBox(height: 90),
                  Icon(Icons.inbox_outlined, size: 48),
                  SizedBox(height: 12),
                  Center(child: Text('Belum ada pesanan QR menunggu persetujuan.')),
                  SizedBox(height: 6),
                  Center(child: Text('Tarik layar ke bawah untuk memuat ulang.')),
                ],
              )
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: items.length,
                separatorBuilder: (context, index) =>
                    const SizedBox(height: 10),
                itemBuilder: (context, index) => _PendingOrderCard(
                  order: items[index],
                  onChanged: () => ref.invalidate(pendingQrOrdersProvider),
                ),
              ),
      ),
    );
  }
}

class _PendingOrderCard extends ConsumerStatefulWidget {
  const _PendingOrderCard({required this.order, required this.onChanged});

  final Map<String, dynamic> order;
  final VoidCallback onChanged;

  @override
  ConsumerState<_PendingOrderCard> createState() => _PendingOrderCardState();
}

class _PendingOrderCardState extends ConsumerState<_PendingOrderCard> {
  bool _busy = false;

  Future<void> _approve() async {
    await _runAction(
      () => ref
          .read(apiClientProvider)
          .postData('/orders/${widget.order['id']}/approve'),
      success: 'Pesanan disetujui.',
    );
  }

  Future<void> _reject() async {
    final reasonController = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Tolak pesanan'),
        content: TextField(
          controller: reasonController,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'Alasan penolakan',
            hintText: 'Contoh: menu sedang habis',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Batal'),
          ),
          FilledButton(
            onPressed: () {
              final value = reasonController.text.trim();
              if (value.isNotEmpty) Navigator.pop(context, value);
            },
            child: const Text('Tolak pesanan'),
          ),
        ],
      ),
    );
    reasonController.dispose();
    if (reason == null || !mounted) return;
    await _runAction(
      () => ref.read(apiClientProvider).postData(
        '/orders/${widget.order['id']}/reject',
        body: {'reason': reason},
      ),
      success: 'Pesanan ditolak.',
    );
  }

  Future<void> _runAction(
    Future<Map<String, dynamic>> Function() action, {
    required String success,
  }) async {
    setState(() => _busy = true);
    try {
      await action();
      widget.onChanged();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(success)),
        );
      }
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Aksi gagal: ${apiErrorMessage(error)}')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final order = widget.order;
    final items = order['items'] as List<dynamic>? ?? const [];
    final total = (order['total'] as num?)?.toDouble() ?? 0;
    final createdAt = DateTime.tryParse(order['created_at'] as String? ?? '');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    order['order_no'] as String? ?? 'Pesanan QR',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Chip(
                  label: Text(
                    order['table_number'] == null
                        ? 'Take Away'
                        : 'Meja ${order['table_number']}',
                  ),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            Text(
              '${order['customer_name'] ?? 'Pelanggan'}${createdAt == null ? '' : ' · ${DateFormat('HH:mm').format(createdAt.toUtc().add(const Duration(hours: 7)))}'}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const Divider(height: 24),
            for (final item in items.whereType<Map<String, dynamic>>())
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Row(
                  children: [
                    Expanded(child: Text(item['item_name'] as String? ?? 'Menu')),
                    Text('× ${item['quantity'] ?? 1}'),
                    const SizedBox(width: 14),
                    Text(_rupiah((item['subtotal'] as num?)?.toDouble() ?? 0)),
                  ],
                ),
              ),
            const Divider(height: 20),
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Total pesanan',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                Text(
                  _rupiah(total),
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: _busy ? null : _reject,
                  icon: const Icon(Icons.close),
                  label: const Text('Tolak'),
                ),
                FilledButton.icon(
                  onPressed: _busy ? null : _approve,
                  icon: _busy
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check),
                  label: const Text('Terima pesanan'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

String _rupiah(num amount) =>
    NumberFormat.currency(locale: 'id_ID', symbol: 'Rp ', decimalDigits: 0)
        .format(amount);
