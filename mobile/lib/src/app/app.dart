import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/login_screen.dart';
import '../features/home/account_screen.dart';
import '../features/management/management_screen.dart';
import '../features/orders/orders_screen.dart';
import '../features/pos/pos_screen.dart';
import '../features/reports/reports_screen.dart';
import '../data/api/api_client.dart';
import '../data/realtime_service.dart';
import 'providers.dart';
import 'state_providers.dart';

final backgroundSyncSetupErrorProvider = Provider<String?>((ref) => null);

final appRouterProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(
    authControllerProvider.select(
      (state) => (ready: state.ready, session: state.session),
    ),
  );
  final router = GoRouter(
    initialLocation: auth.session == null ? '/login' : '/pos',
    redirect: (context, state) {
      final session = auth.session;
      final location = state.matchedLocation;
      if (session == null && location != '/login') return '/login';
      if (session != null && location == '/login') return '/pos';
      if (location == '/management' &&
          session != null &&
          session.role != 'admin' &&
          session.role != 'super_admin') {
        return '/pos';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(path: '/pos', builder: (context, state) => const PosScreen()),
          GoRoute(
            path: '/orders',
            builder: (context, state) => const OrdersScreen(),
          ),
          GoRoute(
            path: '/reports',
            builder: (context, state) => const ReportsScreen(),
          ),
          GoRoute(
            path: '/management',
            builder: (context, state) => const ManagementScreen(),
          ),
          GoRoute(
            path: '/account',
            builder: (context, state) => const AccountScreen(),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

class JouCoffeeApp extends ConsumerStatefulWidget {
  const JouCoffeeApp({super.key});

  @override
  ConsumerState<JouCoffeeApp> createState() => _JouCoffeeAppState();
}

class _JouCoffeeAppState extends ConsumerState<JouCoffeeApp> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(authControllerProvider.notifier).restore());
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xff31513e),
      surface: const Color(0xfff7f7f4),
    );
    if (!auth.ready) {
      return MaterialApp(
        theme: ThemeData(colorScheme: scheme, useMaterial3: true),
        home: const Scaffold(body: Center(child: CircularProgressIndicator())),
      );
    }
    return MaterialApp.router(
      title: 'Jou Coffee POS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: scheme,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xfff7f7f4),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xfff7f7f4),
          surfaceTintColor: Colors.transparent,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
        ),
      ),
      routerConfig: ref.watch(appRouterProvider),
    );
  }
}

class AppShell extends ConsumerStatefulWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell>
    with WidgetsBindingObserver {
  final Connectivity _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  StreamSubscription<RealtimeEvent>? _realtimeSubscription;
  RealtimeService? _realtimeService;
  bool _realtimeConnected = false;

  static const _allDestinations = [
    _Destination('POS', '/pos', Icons.point_of_sale_outlined),
    _Destination('Pesanan', '/orders', Icons.receipt_long_outlined),
    _Destination('Laporan', '/reports', Icons.bar_chart_outlined),
    _Destination('Kelola', '/management', Icons.inventory_2_outlined),
    _Destination('Akun', '/account', Icons.account_circle_outlined),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen((
      results,
    ) {
      if (results.any((result) => result != ConnectivityResult.none)) {
        unawaited(_syncPendingOrders(showResult: false));
      }
    });
    Future.microtask(_connectRealtime);
    Future.microtask(() => _syncPendingOrders(showResult: false));
  }

  void _connectRealtime() {
    final baseUrl = ref.read(apiClientProvider).dio.options.baseUrl;
    final uri = Uri.parse(baseUrl);
    final service = RealtimeService('${uri.scheme}://${uri.authority}');
    _realtimeService = service;
    _realtimeSubscription = service.events.listen((event) {
      if (!mounted) return;
      if (event.name == 'connection' || event.name == 'connection_error') {
        setState(() => _realtimeConnected = event.connected ?? false);
      }
      if (event.name == 'qr_order_pending') {
        ref.invalidate(pendingQrOrdersProvider);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Ada pesanan QR baru menunggu persetujuan.'),
          ),
        );
      }
      if (event.name == 'qris_payment_received') {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Pembayaran QRIS berhasil dikonfirmasi.'),
          ),
        );
      }
      if (event.name == 'order_status_updated' ||
          event.name == 'order_approved' ||
          event.name == 'order_rejected') {
        ref.invalidate(pendingQrOrdersProvider);
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivitySubscription?.cancel();
    _realtimeSubscription?.cancel();
    _realtimeService?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_syncPendingOrders(showResult: false));
    }
  }

  Future<void> _syncPendingOrders({required bool showResult}) async {
    try {
      final count = await ref.read(posRepositoryProvider).syncPendingOrders();
      ref.invalidate(pendingOrdersProvider);
      if (showResult && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              count == 0
                  ? 'Tidak ada pesanan yang menunggu sinkronisasi.'
                  : '$count pesanan berhasil disinkronkan.',
            ),
          ),
        );
      }
    } on Exception catch (error) {
      ref.invalidate(pendingOrdersProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Sinkronisasi gagal: ${apiErrorMessage(error)}'),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final isAdmin =
        auth.session?.role == 'admin' || auth.session?.role == 'super_admin';
    final destinations = _allDestinations
        .where((item) => item.path != '/management' || isAdmin)
        .toList();
    final currentPath = GoRouterState.of(context).uri.path;
    var selectedIndex = destinations.indexWhere(
      (item) => item.path == currentPath,
    );
    if (selectedIndex < 0) selectedIndex = 0;
    final pending = ref.watch(pendingOrdersProvider).asData?.value ?? const [];
    final hasNetwork = ref.watch(connectivityStatusProvider).asData?.value;
    final backgroundSyncError = ref.watch(backgroundSyncSetupErrorProvider);

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Row(
          children: [
            const Icon(Icons.coffee, color: Color(0xff31513e)),
            const SizedBox(width: 9),
            const Text(
              'Jou Coffee',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
            ),
            const SizedBox(width: 12),
            if (pending.isNotEmpty)
              Chip(
                avatar: const Icon(Icons.sync, size: 16),
                label: Text('${pending.length} menunggu'),
                visualDensity: VisualDensity.compact,
                side: BorderSide.none,
              ),
            const SizedBox(width: 8),
            if (backgroundSyncError != null)
              Tooltip(
                message: backgroundSyncError,
                child: const Icon(Icons.warning_amber, color: Colors.orange),
              ),
            Tooltip(
              message: hasNetwork == false
                  ? 'Perangkat tidak terhubung ke jaringan'
                  : hasNetwork == true
                  ? 'Perangkat terhubung ke jaringan'
                  : 'Memeriksa koneksi jaringan',
              child: Icon(
                hasNetwork == false ? Icons.wifi_off : Icons.wifi,
                size: 17,
                color: hasNetwork == true ? Colors.green : Colors.grey,
              ),
            ),
            const SizedBox(width: 8),
            Tooltip(
              message: _realtimeConnected
                  ? 'Pembaruan realtime aktif'
                  : 'Pembaruan realtime tidak aktif',
              child: Icon(
                Icons.sync,
                size: 17,
                color: _realtimeConnected ? Colors.green : Colors.grey,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Sinkronkan pesanan tertunda',
            onPressed: () => _syncPendingOrders(showResult: true),
            icon: const Icon(Icons.sync),
          ),
          if (auth.session != null)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(
                child: Text(
                  auth.session!.name,
                  style: const TextStyle(fontSize: 13),
                ),
              ),
            ),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 820) {
            return Row(
              children: [
                NavigationRail(
                  selectedIndex: selectedIndex,
                  onDestinationSelected: (index) =>
                      context.go(destinations[index].path),
                  labelType: NavigationRailLabelType.all,
                  destinations: [
                    for (final item in destinations)
                      NavigationRailDestination(
                        icon: Icon(item.icon),
                        label: Text(item.label),
                      ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: widget.child),
              ],
            );
          }
          return widget.child;
        },
      ),
      bottomNavigationBar: MediaQuery.sizeOf(context).width < 820
          ? NavigationBar(
              selectedIndex: selectedIndex,
              onDestinationSelected: (index) =>
                  context.go(destinations[index].path),
              destinations: [
                for (final item in destinations)
                  NavigationDestination(
                    icon: Icon(item.icon),
                    label: item.label,
                  ),
              ],
            )
          : null,
    );
  }
}

class _Destination {
  const _Destination(this.label, this.path, this.icon);

  final String label;
  final String path;
  final IconData icon;
}
