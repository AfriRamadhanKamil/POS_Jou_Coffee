import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../data/api/api_client.dart';
import 'dependencies.dart';

class AppSession {
  const AppSession({
    required this.accessToken,
    required this.refreshToken,
    required this.userId,
    required this.username,
    required this.name,
    required this.role,
  });

  final String accessToken;
  final String refreshToken;
  final String userId;
  final String username;
  final String name;
  final String role;

  factory AppSession.fromJson(Map<String, dynamic> json) => AppSession(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    userId: json['user_id'] as String,
    username: json['username'] as String,
    name: json['name'] as String,
    role: json['role'] as String,
  );

  Map<String, String> toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'user_id': userId,
    'username': username,
    'name': name,
    'role': role,
  };
}

class AuthState {
  const AuthState({
    required this.ready,
    this.session,
    this.loading = false,
    this.error,
  });

  final bool ready;
  final AppSession? session;
  final bool loading;
  final String? error;

  AuthState copyWith({
    bool? ready,
    AppSession? session,
    bool? loading,
    String? error,
    bool clearSession = false,
    bool clearError = false,
  }) => AuthState(
    ready: ready ?? this.ready,
    session: clearSession ? null : session ?? this.session,
    loading: loading ?? this.loading,
    error: clearError ? null : error ?? this.error,
  );
}

class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthState(ready: false);

  Future<void> restore() async {
    final storage = ref.read(secureStorageProvider);
    final sessionJson = await storage.read(key: 'jou_session');
    if (sessionJson == null) {
      state = const AuthState(ready: true);
      return;
    }

    try {
      final session = AppSession.fromJson(
        jsonDecode(sessionJson) as Map<String, dynamic>,
      );
      ref.read(apiClientProvider).setSession(
        session.accessToken,
        session.refreshToken,
      );
      state = AuthState(ready: true, session: session);
    } on FormatException {
      await storage.delete(key: 'jou_session');
      state = const AuthState(
        ready: true,
        error: 'Sesi lokal tidak valid. Silakan masuk kembali.',
      );
    } on TypeError {
      await storage.delete(key: 'jou_session');
      state = const AuthState(
        ready: true,
        error: 'Sesi lokal tidak valid. Silakan masuk kembali.',
      );
    } on Exception catch (error) {
      state = AuthState(
        ready: true,
        error: 'Sesi tidak dapat dipulihkan: ${apiErrorMessage(error)}',
      );
    }
  }

  Future<void> login(String username, String password) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final storage = ref.read(secureStorageProvider);
      var deviceId = await storage.read(key: 'jou_device_id');
      if (deviceId == null) {
        deviceId = const Uuid().v4();
        await storage.write(key: 'jou_device_id', value: deviceId);
      }

      final result = await ref.read(apiClientProvider).postData(
        '/auth/login',
        body: {
          'username': username.trim(),
          'password': password,
          'device_id': deviceId,
          'device_name': 'Jou Coffee Mobile',
        },
      );
      final user = result['user'];
      if (user is! Map<String, dynamic>) {
        throw const FormatException('Respons login tidak berisi data pengguna.');
      }
      final accessToken = result['access_token'];
      final refreshToken = result['refresh_token'];
      if (accessToken is! String || refreshToken is! String) {
        throw const FormatException('Respons login tidak berisi token yang valid.');
      }

      final session = AppSession(
        accessToken: accessToken,
        refreshToken: refreshToken,
        userId: user['id'] as String? ?? '',
        username: user['username'] as String? ?? username.trim(),
        name: user['name'] as String? ?? username.trim(),
        role: user['role'] as String? ?? 'kasir',
      );
      await storage.write(key: 'jou_session', value: jsonEncode(session.toJson()));
      ref.read(apiClientProvider).setSession(
        session.accessToken,
        session.refreshToken,
      );
      state = AuthState(ready: true, session: session);
    } on ApiException catch (error) {
      state = state.copyWith(loading: false, error: error.message);
    } on FormatException catch (error) {
      state = state.copyWith(loading: false, error: error.message);
    } on TypeError {
      state = state.copyWith(
        loading: false,
        error: 'Respons login tidak sesuai format. Periksa versi backend.',
      );
    } on Exception catch (error) {
      state = state.copyWith(loading: false, error: apiErrorMessage(error));
    }
  }

  Future<void> logout() async {
    final storage = ref.read(secureStorageProvider);
    await storage.delete(key: 'jou_session');
    ref.read(apiClientProvider).setSession(null, null);
    state = const AuthState(ready: true);
  }
}
