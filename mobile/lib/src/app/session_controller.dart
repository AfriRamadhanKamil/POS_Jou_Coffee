import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:dio/dio.dart';
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
    required this.deviceId,
    this.isOffline = false,
  });

  final String accessToken;
  final String refreshToken;
  final String userId;
  final String username;
  final String name;
  final String role;
  final String deviceId;
  final bool isOffline;

  factory AppSession.fromJson(Map<String, dynamic> json) => AppSession(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    userId: json['user_id'] as String,
    username: json['username'] as String,
    name: json['name'] as String,
    role: json['role'] as String,
    deviceId: json['device_id'] as String? ?? '',
    isOffline: json['is_offline'] as bool? ?? false,
  );

  Map<String, Object> toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'user_id': userId,
    'username': username,
    'name': name,
    'role': role,
    'device_id': deviceId,
    'is_offline': isOffline,
  };

  AppSession asOffline() => AppSession(
    accessToken: accessToken,
    refreshToken: refreshToken,
    userId: userId,
    username: username,
    name: name,
    role: role,
    deviceId: deviceId,
    isOffline: true,
  );
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
  AuthState build() {
    final api = ref.read(apiClientProvider);
    api.onAccessTokenRefreshed = _persistRefreshedToken;
    api.onSessionExpired = logout;
    return const AuthState(ready: false);
  }

  Future<void> restore() async {
    final storage = ref.read(secureStorageProvider);
    final baseUrl = await storage.read(key: 'jou_api_base_url');
    if (baseUrl != null) {
      ref.read(apiClientProvider).setBaseUrl(baseUrl);
    }
    final sessionJson = await storage.read(key: 'jou_session');
    if (sessionJson == null) {
      state = const AuthState(ready: true);
      return;
    }

    try {
      final offlineAuthJson = await storage.read(key: 'jou_offline_auth');
      if (offlineAuthJson == null) {
        await storage.delete(key: 'jou_session');
        state = const AuthState(
          ready: true,
          error: 'Sesi lokal kedaluwarsa. Silakan masuk kembali.',
        );
        return;
      }
      final offlineAuth = jsonDecode(offlineAuthJson) as Map<String, dynamic>;
      final lastOnlineLogin = DateTime.tryParse(
        offlineAuth['last_online_login'] as String? ?? '',
      );
      if (lastOnlineLogin == null || !isOfflineSessionValid(lastOnlineLogin)) {
        await storage.delete(key: 'jou_session');
        state = const AuthState(
          ready: true,
          error: 'Sesi offline lebih dari 7 hari. Silakan masuk kembali.',
        );
        return;
      }
      final session = AppSession.fromJson(
        jsonDecode(sessionJson) as Map<String, dynamic>,
      );
      if (offlineAuth['username'] != session.username) {
        await storage.delete(key: 'jou_session');
        state = const AuthState(
          ready: true,
          error: 'Sesi lokal tidak cocok. Silakan masuk kembali.',
        );
        return;
      }
      ref
          .read(apiClientProvider)
          .setSession(session.accessToken, session.refreshToken);
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

  Future<void> setServerUrl(String value) async {
    final baseUrl = _normalizeServerUrl(value);
    if (baseUrl == null) {
      throw const FormatException(
        'Alamat server harus berupa URL HTTP/HTTPS yang valid.',
      );
    }
    await ref
        .read(secureStorageProvider)
        .write(key: 'jou_api_base_url', value: baseUrl);
    ref.read(apiClientProvider).setBaseUrl(baseUrl);
  }

  Future<void> login(
    String username,
    String credential, {
    bool isPin = false,
  }) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final storage = ref.read(secureStorageProvider);
      var deviceId = await storage.read(key: 'jou_device_id');
      if (deviceId == null) {
        deviceId = const Uuid().v4();
        await storage.write(key: 'jou_device_id', value: deviceId);
      }

      final result = await ref
          .read(apiClientProvider)
          .postData(
            '/auth/login',
            body: {
              'username': username.trim(),
              if (isPin) 'pin': credential else 'password': credential,
              'device_id': deviceId,
              'device_name': 'Jou Coffee Mobile',
            },
          );
      final user = result['user'];
      if (user is! Map<String, dynamic>) {
        throw const FormatException(
          'Respons login tidak berisi data pengguna.',
        );
      }
      final accessToken = result['access_token'];
      final refreshToken = result['refresh_token'];
      if (accessToken is! String || refreshToken is! String) {
        throw const FormatException(
          'Respons login tidak berisi token yang valid.',
        );
      }

      final session = AppSession(
        accessToken: accessToken,
        refreshToken: refreshToken,
        userId: user['id'] as String? ?? '',
        username: user['username'] as String? ?? username.trim(),
        name: user['name'] as String? ?? username.trim(),
        role: user['role'] as String? ?? 'kasir',
        deviceId: deviceId,
      );
      await storage.write(
        key: 'jou_session',
        value: jsonEncode(session.toJson()),
      );
      final salt = const Uuid().v4();
      await storage.write(
        key: 'jou_offline_auth',
        value: jsonEncode({
          'username': session.username,
          'salt': salt,
          'credential_hash': await deriveOfflineCredentialVerifier(
            username: session.username,
            credential: credential,
            salt: salt,
            isPin: isPin,
          ),
          'is_pin': isPin,
          'last_online_login': DateTime.now().toUtc().toIso8601String(),
        }),
      );
      ref
          .read(apiClientProvider)
          .setSession(session.accessToken, session.refreshToken);
      state = AuthState(ready: true, session: session);
    } on DioException catch (error) {
      if (error.response == null ||
          error.requestOptions.extra['refreshUnavailable'] == true) {
        await _tryOfflineLogin(username, credential, isPin);
        return;
      }
      state = state.copyWith(loading: false, error: apiErrorMessage(error));
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
    await storage.delete(key: 'jou_offline_auth');
    await ref.read(appDatabaseProvider).clearCachedCatalog();
    ref.read(apiClientProvider).setSession(null, null);
    state = const AuthState(ready: true);
  }

  Future<void> _tryOfflineLogin(
    String username,
    String credential,
    bool isPin,
  ) async {
    final storage = ref.read(secureStorageProvider);
    final savedSession = await storage.read(key: 'jou_session');
    final authJson = await storage.read(key: 'jou_offline_auth');
    if (savedSession == null || authJson == null) {
      state = state.copyWith(
        loading: false,
        error:
            'Belum ada sesi offline. Silakan login saat terhubung ke server.',
      );
      return;
    }

    try {
      final saved = jsonDecode(authJson) as Map<String, dynamic>;
      final session = AppSession.fromJson(
        jsonDecode(savedSession) as Map<String, dynamic>,
      );
      final lastLogin = DateTime.tryParse(
        saved['last_online_login'] as String? ?? '',
      );
      final salt = saved['salt'] as String? ?? '';
      final savedHash = saved['credential_hash'] as String? ?? '';
      final matches =
          saved['username'] == username.trim() &&
          saved['is_pin'] == isPin &&
          lastLogin != null &&
          isOfflineSessionValid(lastLogin) &&
          await deriveOfflineCredentialVerifier(
                username: username.trim(),
                credential: credential,
                salt: salt,
                isPin: isPin,
              ) ==
              savedHash;
      if (!matches) {
        state = state.copyWith(
          loading: false,
          error:
              'Kredensial offline tidak cocok atau sesi sudah lebih dari 7 hari.',
        );
        return;
      }

      final offlineSession = session.asOffline();
      ref
          .read(apiClientProvider)
          .setSession(offlineSession.accessToken, offlineSession.refreshToken);
      await storage.write(
        key: 'jou_session',
        value: jsonEncode(offlineSession.toJson()),
      );
      state = AuthState(ready: true, session: offlineSession);
    } on FormatException {
      state = state.copyWith(
        loading: false,
        error: 'Data sesi offline tidak valid. Silakan login saat online.',
      );
    } on TypeError {
      state = state.copyWith(
        loading: false,
        error: 'Data sesi offline tidak valid. Silakan login saat online.',
      );
    }
  }

  Future<void> _persistRefreshedToken(String accessToken) async {
    final storage = ref.read(secureStorageProvider);
    final rawSession = await storage.read(key: 'jou_session');
    if (rawSession == null) return;
    final session = jsonDecode(rawSession) as Map<String, dynamic>;
    session['access_token'] = accessToken;
    session['is_offline'] = false;
    await storage.write(key: 'jou_session', value: jsonEncode(session));
    if (state.session != null) {
      state = state.copyWith(session: AppSession.fromJson(session));
    }
  }
}

String? _normalizeServerUrl(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null ||
      !{'http', 'https'}.contains(uri.scheme) ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment) {
    return null;
  }
  var path = uri.path.replaceFirst(RegExp(r'/+$'), '');
  if (!path.endsWith('/api/v1')) path = '$path/api/v1';
  return uri.replace(path: path).toString().replaceFirst(RegExp(r'/+$'), '');
}

Future<String> deriveOfflineCredentialVerifier({
  required String username,
  required String credential,
  required String salt,
  required bool isPin,
}) async {
  final algorithm = Pbkdf2(
    macAlgorithm: Hmac.sha256(),
    iterations: 100000,
    bits: 256,
  );
  final key = await algorithm.deriveKey(
    secretKey: SecretKey(
      utf8.encode(
        '${username.toLowerCase()}:${isPin ? 'pin' : 'password'}:$credential',
      ),
    ),
    nonce: utf8.encode(salt),
  );
  return base64Encode(await key.extractBytes());
}

bool isOfflineSessionValid(DateTime lastOnlineLogin, {DateTime? now}) {
  final currentTime = (now ?? DateTime.now()).toUtc();
  final loginTime = lastOnlineLogin.toUtc();
  final age = currentTime.difference(loginTime);
  return !age.isNegative && age <= const Duration(days: 7);
}
