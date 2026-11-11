import 'package:dio/dio.dart';

class ApiClient {
  ApiClient()
    : dio = Dio(
        BaseOptions(
          baseUrl: const String.fromEnvironment(
            'API_BASE_URL',
            defaultValue: 'http://10.0.2.2:5000/api/v1',
          ),
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 15),
          headers: const {'Content-Type': 'application/json'},
        ),
      ),
      _refreshDio = Dio(
        BaseOptions(
          baseUrl: const String.fromEnvironment(
            'API_BASE_URL',
            defaultValue: 'http://10.0.2.2:5000/api/v1',
          ),
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 15),
          headers: const {'Content-Type': 'application/json'},
        ),
      ) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onError: (error, handler) async {
          if (error.response?.statusCode != 401 ||
              error.requestOptions.extra['retried'] == true ||
              _refreshToken == null ||
              error.requestOptions.path.endsWith('/auth/refresh')) {
            handler.next(error);
            return;
          }
          try {
            final response = await _refreshDio.post<Map<String, dynamic>>(
              '/auth/refresh',
              options: Options(
                headers: {'Authorization': 'Bearer $_refreshToken'},
              ),
            );
            final payload = response.data?['data'];
            final accessToken = payload is Map
                ? payload['access_token']
                : null;
            if (accessToken is! String || accessToken.isEmpty) {
              handler.next(error);
              return;
            }
            setSession(accessToken, _refreshToken);
            final request = error.requestOptions
              ..headers['Authorization'] = 'Bearer $accessToken'
              ..extra['retried'] = true;
            handler.resolve(await dio.fetch<Object?>(request));
          } on DioException catch (refreshError) {
            if (refreshError.response == null) {
              error.requestOptions.extra['refreshUnavailable'] = true;
            }
            handler.next(error);
          }
        },
      ),
    );
  }

  final Dio dio;
  final Dio _refreshDio;
  String? _refreshToken;
  Future<void> Function(String accessToken)? onAccessTokenRefreshed;

  void setSession(String? accessToken, String? refreshToken) {
    _refreshToken = refreshToken;
    dio.options.headers.remove('Authorization');
    if (accessToken != null && accessToken.isNotEmpty) {
      dio.options.headers['Authorization'] = 'Bearer $accessToken';
    }
  }

  Future<String> refreshAccessToken(String refreshToken) async {
    final response = await _refreshDio.post<Object?>(
      '/auth/refresh',
      options: Options(
        headers: {'Authorization': 'Bearer $refreshToken'},
      ),
    );
    final body = response.data;
    if (body is! Map<String, dynamic> || body['success'] != true) {
      final message = body is Map && body['message'] is String
          ? body['message'] as String
          : 'Sesi tidak dapat diperbarui.';
      throw ApiException(message, response.statusCode);
    }
    final data = body['data'];
    final accessToken = data is Map ? data['access_token'] : null;
    if (accessToken is! String || accessToken.isEmpty) {
      throw const FormatException('Respons refresh tidak berisi access token.');
    }
    setSession(accessToken, refreshToken);
    return accessToken;
  }

  Map<String, dynamic> unwrap(Response<dynamic> response) {
    final body = response.data;
    if (body is! Map<String, dynamic>) {
      throw const FormatException('Respons API tidak sesuai format.');
    }
    if (body['success'] == false) {
      throw ApiException(
        body['message'] is String ? body['message'] as String : 'Permintaan gagal.',
        response.statusCode,
      );
    }
    final data = body['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data};
    return <String, dynamic>{};
  }

  Future<Map<String, dynamic>> getData(String path, {Map<String, Object?>? query}) async {
    return unwrap(await dio.get<Object?>(path, queryParameters: query));
  }

  Future<Map<String, dynamic>> postData(
    String path, {
    Map<String, Object?>? body,
  }) async {
    return unwrap(await dio.post<Object?>(path, data: body));
  }
}

class ApiException implements Exception {
  const ApiException(this.message, this.statusCode);

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

String apiErrorMessage(Object error) {
  if (error is ApiException) return error.message;
  if (error is DioException) {
    final response = error.response?.data;
    if (response is Map && response['message'] is String) {
      return response['message'] as String;
    }
    if (error.response == null) {
      return 'Tidak dapat terhubung ke server. Periksa jaringan lalu coba lagi.';
    }
  }
  return 'Terjadi kesalahan. Silakan coba kembali.';
}
