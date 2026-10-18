import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_providers.dart';
import '../data/prescriptions_repository.dart';
import 'prescription.dart';

final prescriptionsRepositoryProvider =
    Provider<PrescriptionsRepository>((ref) {
  return PrescriptionsRepository(
    dio: ref.watch(dioProvider),
    tokenStorage: ref.watch(tokenStorageProvider),
  );
});

final prescriptionsProvider =
    FutureProvider.autoDispose<List<Prescription>>((ref) async {
  return ref.watch(prescriptionsRepositoryProvider).listMyPrescriptions();
});