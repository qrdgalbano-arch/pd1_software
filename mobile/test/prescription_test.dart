import 'package:flutter_test/flutter_test.dart';
import 'package:qmmc_pd1_mobile/features/prescriptions/domain/prescription.dart';

void main() {
  group('Prescription.fromJson', () {
    test('parses an enriched prescription with exercise details', () {
      final prescription = Prescription.fromJson({
        'id': 1,
        'patient_id': 2,
        'staff_id': 3,
        'exercise_id': 4,
        'repetitions_target': 10,
        'duration_limit_seconds': 90,
        'scheduled_days': 'Monday, Wednesday, Friday',
        'is_active': true,
        'created_at': '2026-09-11T00:00:00Z',
        'exercise': {
          'id': 4,
          'name': 'Seated Knee Extension',
          'description':
              'Sit upright. Slowly straighten one knee, then lower it.',
        },
      });

      expect(prescription.id, 1);
      expect(prescription.exerciseId, 4);
      expect(prescription.exercise.id, 4);
      expect(prescription.exercise.name, 'Seated Knee Extension');
      expect(
        prescription.exercise.description,
        'Sit upright. Slowly straighten one knee, then lower it.',
      );
      expect(prescription.repetitionsTarget, 10);
      expect(prescription.durationLimitSeconds, 90);
      expect(prescription.formattedDuration, '1 min 30 sec');
      expect(prescription.scheduledDays, 'Monday, Wednesday, Friday');
      expect(prescription.isActive, isTrue);
    });

    test('formats durations below one minute in seconds', () {
      final prescription = Prescription(
        id: 1,
        exerciseId: 4,
        exercise: const ExerciseSummary(
          id: 4,
          name: 'Example exercise',
          description: 'Example instruction.',
        ),
        repetitionsTarget: 5,
        durationLimitSeconds: 45,
        scheduledDays: 'Monday',
        isActive: true,
      );

      expect(prescription.formattedDuration, '45 seconds');
    });

    test('rejects a prescription without exercise details', () {
      expect(
        () => Prescription.fromJson({
          'id': 1,
          'exercise_id': 4,
          'repetitions_target': 10,
          'duration_limit_seconds': 60,
          'scheduled_days': 'Monday',
          'is_active': true,
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
