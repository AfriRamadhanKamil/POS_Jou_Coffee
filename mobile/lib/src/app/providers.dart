import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session_controller.dart';

export 'dependencies.dart';

final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);
