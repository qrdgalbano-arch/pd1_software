import 'package:dio/dio.dart';

import '../../../core/storage/token_storage.dart';
import '../domain/prescription.dart';

class PrescriptionsRepository {
  PrescriptionsRepository({
    required Dio dio,
    required TokenStorage tokenStorage,
  })  : _dio = dio,
        _tokenStorage = tokenStorage;

  final Dio _dio;
  final TokenStorage _tokenStorage;

  Future<List<Prescription>> listMyPrescriptions() async {
    final accessToken = await _tokenStorage.readAccessToken();

    if (accessToken == null || accessToken.isEmpty) {
      throw const UnauthorizedException();
    }

    final response = await _dio.get<List<dynamic>>(
      '/patients/me/prescriptions',
      options: Options(
        headers: {'Authorization': 'Bearer $accessToken'},
      ),
    );

    final data = response.data;
    if (data == null) {
      return const [];
    }

    return data
        .whereType<Map<String, dynamic>>()
        .map(Prescription.fromJson)
        .toList();
  }
}

class UnauthorizedException implements Exception {
  const UnauthorizedException();
}