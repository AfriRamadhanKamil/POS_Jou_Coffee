import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/app/app.dart';
import 'src/app/background_sync.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final backgroundSyncError = await initializeBackgroundSync();
  runApp(
    ProviderScope(
      overrides: [
        backgroundSyncSetupErrorProvider.overrideWithValue(backgroundSyncError),
      ],
      child: const JouCoffeeApp(),
    ),
  );
}
