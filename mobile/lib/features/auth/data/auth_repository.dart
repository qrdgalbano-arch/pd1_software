import 'package:dio/dio.dart';

import '../../../core/storage/token_storage.dart';
import '../domain/auth_user.dart';

class AuthRepository {
  AuthRepository({
    required Dio dio,
    required TokenStorage tokenStorage,
  })  : _dio = dio,
        _tokenStorage = tokenStorage;

  final Dio _dio;
  final TokenStorage _tokenStorage;

  Future<AuthUser> signIn({
    required String email,
    required String password,
  }) async {
    final tokenResponse = await _dio.post<Map<String, dynamic>>(
      '/auth/login',
      data: {
        'username': email.trim(),
        'password': password,
      },
      options: Options(
        contentType: Headers.formUrlEncodedContentType,
      ),
    );

    final tokenData = tokenResponse.data;
    if (tokenData == null ||
        tokenData['access_token'] is! String ||
        tokenData['refresh_token'] is! String) {
      throw const FormatException('The server returned an invalid token response.');
    }

    await _tokenStorage.saveTokens(
      accessToken: tokenData['access_token'] as String,
      refreshToken: tokenData['refresh_token'] as String,
    );

    return getCurrentUser();
  }

  Future<AuthUser> getCurrentUser() async {
    final accessToken = await _tokenStorage.readAccessToken();
    if (accessToken == null || accessToken.isEmpty) {
      throw const UnauthorizedException();
    }

    final response = await _dio.get<Map<String, dynamic>>(
      '/auth/me',
      options: Options(
        headers: {'Authorization': 'Bearer $accessToken'},
      ),
    );

    final data = response.data;
    if (data == null) {
      throw const FormatException('The server returned an empty user response.');
    }

    return AuthUser.fromJson(data);
  }

  Future<AuthUser?> restoreSession() async {
    try {
      return await getCurrentUser();
    } on DioException catch (error) {
      if (error.response?.statusCode == 401) {
        await _tokenStorage.clearTokens();
        return null;
      }
      rethrow;
    } on UnauthorizedException {
      return null;
    }
  }

  Future<void> signOut() {
    return _tokenStorage.clearTokens();
  }
}

class UnauthorizedException implements Exception {
  const UnauthorizedException();
}
