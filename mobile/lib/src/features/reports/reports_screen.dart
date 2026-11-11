import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/providers.dart';
import '../../data/api/api_client.dart';

final reportDataProvider = FutureProvider<ReportData>((ref) async {
  final api = ref.watch(apiClientProvider);
  final now = DateTime.now().toUtc().add(const Duration(hours: 7));
  final start = now.subtract(const Duration(days: 6));
  final dateFormat = DateFormat('yyyy-MM-dd');
  final query = {
    'start_date': dateFormat.format(start),
    'end_date': dateFormat.format(now),
  };
  final sales = await api.getData('/reports/sales', query: query);
  final cash = await api.getData('/reports/cash-summary');
  final charts = await api.getData('/reports/charts');
  final session = ref.watch(authControllerProvider).session;
  final profit = session?.role == 'admin' || session?.role == 'super_admin'
      ? await api.getData('/reports/profit')
      : null;
  return ReportData.fromJson(sales, cash, charts, profit);
});

class ReportData {
  const ReportData({
    required this.summary,
    required this.cash,
    required this.topMenus,
    required this.salesByType,
    required this.profit,
  });

  final Map<String, dynamic> summary;
  final Map<String, dynamic> cash;
  final List<Map<String, dynamic>> topMenus;
  final List<Map<String, dynamic>> salesByType;
  final Map<String, dynamic>? profit;

  factory ReportData.fromJson(
    Map<String, dynamic> sales,
    Map<String, dynamic> cash,
    Map<String, dynamic> charts,
    Map<String, dynamic>? profit,
  ) => ReportData(
    summary: sales['summary'] as Map<String, dynamic>? ?? const {},
    cash: cash,
    topMenus: (charts['top_selling_menus'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList(),
    salesByType: (charts['sales_by_order_type'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList(),
    profit: profit,
  );
}

class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(reportDataProvider);
    return report.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, stackTrace) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.bar_chart_outlined, size: 44),
              const SizedBox(height: 12),
              const Text('Laporan belum dapat dimuat.'),
              const SizedBox(height: 8),
              Text(apiErrorMessage(error), textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => ref.invalidate(reportDataProvider),
                child: const Text('Coba lagi'),
              ),
            ],
          ),
        ),
      ),
      data: (data) {
        final gross = _number(data.summary['total_gross']);
        final net = _number(data.summary['total_net']);
        final orderCount = _number(data.summary['order_count']);
        return RefreshIndicator(
          onRefresh: () => ref.refresh(reportDataProvider.future),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Ringkasan 7 hari terakhir',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Muat ulang',
                    onPressed: () => ref.invalidate(reportDataProvider),
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  _MetricCard(
                    label: 'Penjualan bersih',
                    value: _rupiah(net),
                    icon: Icons.payments_outlined,
                  ),
                  _MetricCard(
                    label: 'Jumlah pesanan',
                    value: orderCount.toStringAsFixed(0),
                    icon: Icons.receipt_long_outlined,
                  ),
                  _MetricCard(
                    label: 'Penjualan kotor',
                    value: _rupiah(gross),
                    icon: Icons.point_of_sale_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              _ChartCard(title: 'Menu terlaris', items: data.topMenus),
              const SizedBox(height: 12),
              _OrderTypeCard(items: data.salesByType),
              const SizedBox(height: 12),
              _CashCard(data: data.cash),
              if (data.profit != null) ...[
                const SizedBox(height: 12),
                _ProfitCard(data: data.profit!),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 220,
    child: Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 12),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 4),
            Text(
              value,
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    ),
  );
}

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.title, required this.items});

  final String title;
  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) {
    final maxValue = items.fold<double>(
      0,
      (value, item) => value > _number(item['quantity'])
          ? value
          : _number(item['quantity']),
    );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 18),
            if (items.isEmpty)
              const Text('Belum ada data penjualan.')
            else
              SizedBox(
                height: 190,
                child: BarChart(
                  BarChartData(
                    maxY: maxValue <= 0 ? 1 : maxValue * 1.2,
                    barGroups: [
                      for (var index = 0; index < items.length; index++)
                        BarChartGroupData(
                          x: index,
                          barRods: [
                            BarChartRodData(
                              toY: _number(items[index]['quantity']),
                              color: Theme.of(context).colorScheme.primary,
                              width: 24,
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ],
                        ),
                    ],
                    titlesData: const FlTitlesData(show: false),
                    borderData: FlBorderData(show: false),
                    gridData: const FlGridData(show: false),
                  ),
                ),
              ),
            for (final item in items)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(item['name'] as String? ?? 'Menu'),
                trailing: Text(
                  '${_number(item['quantity']).toStringAsFixed(0)} terjual',
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _OrderTypeCard extends StatelessWidget {
  const _OrderTypeCard({required this.items});

  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Tipe pesanan', style: Theme.of(context).textTheme.titleMedium),
          for (final item in items)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_orderTypeLabel(item['order_type'] as String? ?? '')),
              subtitle: Text('${item['count'] ?? 0} transaksi'),
              trailing: Text(_rupiah(_number(item['total']))),
            ),
          if (items.isEmpty) const Text('Belum ada data pesanan.'),
        ],
      ),
    ),
  );
}

class _CashCard extends StatelessWidget {
  const _CashCard({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Ringkasan pembayaran', style: Theme.of(context).textTheme.titleMedium),
          _DataRow(label: 'Tunai', value: _rupiah(_number(data['cash_drawer_total']))),
          _DataRow(label: 'QRIS', value: _rupiah(_number(data['qris_total']))),
          _DataRow(label: 'Platform', value: _rupiah(_number(data['platform_total']))),
          const Divider(),
          _DataRow(
            label: 'Total',
            value: _rupiah(_number(data['grand_total'])),
            strong: true,
          ),
        ],
      ),
    ),
  );
}

class _ProfitCard extends StatelessWidget {
  const _ProfitCard({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Laba kotor', style: Theme.of(context).textTheme.titleMedium),
          _DataRow(label: 'Pendapatan', value: _rupiah(_number(data['total_revenue']))),
          _DataRow(label: 'HPP', value: _rupiah(_number(data['total_cogs']))),
          const Divider(),
          _DataRow(
            label: 'Laba',
            value: _rupiah(_number(data['gross_profit'])),
            strong: true,
          ),
          Text(
            'Margin ${_number(data['margin_percentage']).toStringAsFixed(1)}%',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    ),
  );
}

class _DataRow extends StatelessWidget {
  const _DataRow({
    required this.label,
    required this.value,
    this.strong = false,
  });

  final String label;
  final String value;
  final bool strong;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: TextStyle(fontWeight: strong ? FontWeight.w700 : null),
          ),
        ),
        Text(value, style: TextStyle(fontWeight: strong ? FontWeight.w700 : null)),
      ],
    ),
  );
}

String _orderTypeLabel(String value) => switch (value) {
  'DINE_IN' => 'Dine In',
  'TAKE_AWAY' => 'Take Away',
  'DELIVERY' => 'Delivery / Platform',
  _ => value,
};

double _number(Object? value) => value is num ? value.toDouble() : 0;

String _rupiah(num amount) =>
    NumberFormat.currency(locale: 'id_ID', symbol: 'Rp ', decimalDigits: 0)
        .format(amount);
