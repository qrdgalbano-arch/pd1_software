class ExerciseSummary {
  const ExerciseSummary({
    required this.id,
    required this.name,
    required this.description,
  });

  final int id;
  final String name;
  final String description;

  factory ExerciseSummary.fromJson(Map<String, dynamic> json) {
    return ExerciseSummary(
      id: json['id'] as int,
      name: json['name'] as String,
      description: json['description'] as String,
    );
  }
}

class Prescription {
  const Prescription({
    required this.id,
    required this.exerciseId,
    required this.exercise,
    required this.repetitionsTarget,
    required this.durationLimitSeconds,
    required this.scheduledDays,
    required this.isActive,
  });

  final int id;
  final int exerciseId;
  final ExerciseSummary exercise;
  final int repetitionsTarget;
  final int durationLimitSeconds;
  final String scheduledDays;
  final bool isActive;

  String get formattedDuration {
    if (durationLimitSeconds < 60) {
      return '$durationLimitSeconds seconds';
    }

    final minutes = durationLimitSeconds ~/ 60;
    final seconds = durationLimitSeconds % 60;

    if (seconds == 0) {
      return '$minutes ${minutes == 1 ? 'minute' : 'minutes'}';
    }

    return '$minutes min $seconds sec';
  }

  factory Prescription.fromJson(Map<String, dynamic> json) {
    final exerciseJson = json['exercise'];

    if (exerciseJson is! Map<String, dynamic>) {
      throw const FormatException(
        'The server returned a prescription without exercise details.',
      );
    }

    return Prescription(
      id: json['id'] as int,
      exerciseId: json['exercise_id'] as int,
      exercise: ExerciseSummary.fromJson(exerciseJson),
      repetitionsTarget: json['repetitions_target'] as int,
      durationLimitSeconds: json['duration_limit_seconds'] as int,
      scheduledDays: json['scheduled_days'] as String,
      isActive: json['is_active'] as bool,
    );
  }
}
