import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum LegSide { left, right }

extension LegSideLabel on LegSide {
  String get label => this == LegSide.left ? 'Left' : 'Right';
}

class ExerciseDef {
  const ExerciseDef({
    required this.key,
    required this.name,
    required this.sets,
    required this.reps,
    required this.targetDeg,
    required this.frequency,
    required this.steps,
  });

  final String key;
  final String name;
  final int sets;
  final int reps;
  final double targetDeg;
  final String frequency;
  final List<String> steps;

  String get prescription => '$sets Sets × $reps Reps';
}

/// Fixed order. The list screen locks everything after the first undone item.
/// Instruction text is placeholder content: replace with clinician-approved wording.
const List<ExerciseDef> designBExercises = [
  ExerciseDef(
    key: 'straight_leg_raise',
    name: 'Straight Leg Raise',
    sets: 3,
    reps: 10,
    targetDeg: 45,
    frequency: 'Daily',
    steps: [
      'Lie down flat on your back with one knee bent and the other leg kept completely straight.',
      'Tighten your thigh muscle on the straight leg and slowly lift it about 12 inches.',
      'Hold for 3 seconds, then slowly lower the straight leg back to the floor.',
    ],
  ),
  ExerciseDef(
    key: 'prone_leg_flexion',
    name: 'Prone Leg Flexion',
    sets: 3,
    reps: 10,
    targetDeg: 90,
    frequency: 'Daily',
    steps: [
      'Lie face down on a firm surface with both legs straight.',
      'Slowly bend one knee, bringing your heel toward your buttock as far as is comfortable.',
      'Hold for 3 seconds, then slowly lower your foot back down.',
    ],
  ),
  ExerciseDef(
    key: 'ankle_pump',
    name: 'Ankle Pump',
    sets: 3,
    reps: 10,
    targetDeg: 30,
    frequency: 'Daily',
    steps: [
      'Lie or sit with your legs straight and relaxed.',
      'Point your toes away from you as far as is comfortable, then pull them back toward your shin.',
      'Move smoothly and repeat without rushing.',
    ],
  ),
];

class SessionRecord {
  const SessionRecord({
    required this.id,
    required this.patientId,
    required this.exerciseKey,
    required this.exerciseName,
    required this.setsCompleted,
    required this.setsTotal,
    required this.totalReps,
    required this.repsTotal,
    required this.durationSeconds,
    required this.recordedAt,
    required this.completed,
    this.synced = false,
  });

  final String id;
  final String patientId;
  final String exerciseKey;
  final String exerciseName;
  final int setsCompleted;
  final int setsTotal;
  final int totalReps;
  final int repsTotal;
  final int durationSeconds;
  final DateTime recordedAt;
  final bool completed;
  final bool synced;

  SessionRecord copyWith({bool? synced}) => SessionRecord(
        id: id,
        patientId: patientId,
        exerciseKey: exerciseKey,
        exerciseName: exerciseName,
        setsCompleted: setsCompleted,
        setsTotal: setsTotal,
        totalReps: totalReps,
        repsTotal: repsTotal,
        durationSeconds: durationSeconds,
        recordedAt: recordedAt,
        completed: completed,
        synced: synced ?? this.synced,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'patientId': patientId,
        'exerciseKey': exerciseKey,
        'exerciseName': exerciseName,
        'setsCompleted': setsCompleted,
        'setsTotal': setsTotal,
        'totalReps': totalReps,
        'repsTotal': repsTotal,
        'durationSeconds': durationSeconds,
        'recordedAt': recordedAt.toIso8601String(),
        'completed': completed,
        'synced': synced,
      };

  factory SessionRecord.fromJson(Map<String, dynamic> j) => SessionRecord(
        id: j['id'] as String,
        patientId: j['patientId'] as String,
        exerciseKey: j['exerciseKey'] as String,
        exerciseName: j['exerciseName'] as String,
        setsCompleted: j['setsCompleted'] as int,
        setsTotal: j['setsTotal'] as int,
        totalReps: j['totalReps'] as int,
        repsTotal: j['repsTotal'] as int,
        durationSeconds: j['durationSeconds'] as int,
        recordedAt: DateTime.parse(j['recordedAt'] as String),
        completed: j['completed'] as bool,
        synced: j['synced'] as bool? ?? false,
      );
}

class DesignBState {
  const DesignBState({
    this.patientId,
    this.sessions = const [],
    this.lastSynced,
    this.lastSession,
    this.syncing = false,
  });

  final String? patientId;
  final List<SessionRecord> sessions;
  final DateTime? lastSynced;
  final SessionRecord? lastSession;
  final bool syncing;

  DesignBState copyWith({
    String? patientId,
    List<SessionRecord>? sessions,
    DateTime? lastSynced,
    SessionRecord? lastSession,
    bool? syncing,
  }) =>
      DesignBState(
        patientId: patientId ?? this.patientId,
        sessions: sessions ?? this.sessions,
        lastSynced: lastSynced ?? this.lastSynced,
        lastSession: lastSession ?? this.lastSession,
        syncing: syncing ?? this.syncing,
      );

  /// Exercises fully recorded today by the current patient.
  Map<String, DateTime> get completedToday {
    final now = DateTime.now();
    final map = <String, DateTime>{};
    for (final s in sessions) {
      if (!s.completed || s.patientId != patientId) continue;
      final d = s.recordedAt;
      if (d.year == now.year && d.month == now.month && d.day == now.day) {
        final existing = map[s.exerciseKey];
        if (existing == null || d.isAfter(existing)) map[s.exerciseKey] = d;
      }
    }
    return map;
  }

  /// Index of the only unlocked exercise (strict order).
  int get nextIndex {
    final done = completedToday;
    for (var i = 0; i < designBExercises.length; i++) {
      if (!done.containsKey(designBExercises[i].key)) return i;
    }
    return designBExercises.length;
  }

  List<SessionRecord> get pending =>
      sessions.where((s) => !s.synced).toList();
}

class DesignBNotifier extends StateNotifier<DesignBState> {
  DesignBNotifier() : super(const DesignBState()) {
    _load();
  }

  static const String _sessionsKey = 'design_b_sessions_v1';
  static const String _syncedKey = 'design_b_last_synced_v1';

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_sessionsKey);
    final synced = prefs.getString(_syncedKey);
    if (!mounted) return;
    final sessions = raw == null
        ? <SessionRecord>[]
        : (jsonDecode(raw) as List<dynamic>)
            .map((e) => SessionRecord.fromJson(e as Map<String, dynamic>))
            .toList();
    state = state.copyWith(
      sessions: sessions,
      lastSynced: synced == null ? null : DateTime.tryParse(synced),
    );
  }

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _sessionsKey,
      jsonEncode(state.sessions.map((s) => s.toJson()).toList()),
    );
    final synced = state.lastSynced;
    if (synced != null) {
      await prefs.setString(_syncedKey, synced.toIso8601String());
    }
  }

  void setPatient(String id) {
    state = state.copyWith(patientId: id);
  }

  /// Saved locally first; marked pending until synced.
  void completeSession(SessionRecord record) {
    state = state.copyWith(
      sessions: [record, ...state.sessions],
      lastSession: record,
    );
    _save();
  }

  /// Upload is simulated in this build: no server call is made.
  Future<void> syncAll() async {
    if (state.syncing) return;
    state = state.copyWith(syncing: true);
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    if (!mounted) return;
    state = state.copyWith(
      sessions: [for (final s in state.sessions) s.copyWith(synced: true)],
      lastSynced: DateTime.now(),
      syncing: false,
    );
    await _save();
  }

  Future<void> syncOne(String id) async {
    if (state.syncing) return;
    state = state.copyWith(syncing: true);
    await Future<void>.delayed(const Duration(milliseconds: 800));
    if (!mounted) return;
    state = state.copyWith(
      sessions: [
        for (final s in state.sessions)
          s.id == id ? s.copyWith(synced: true) : s,
      ],
      lastSynced: DateTime.now(),
      syncing: false,
    );
    await _save();
  }
}

final designBProvider =
    StateNotifierProvider<DesignBNotifier, DesignBState>((ref) {
  return DesignBNotifier();
});

String formatClock(DateTime d) {
  final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
  final m = d.minute.toString().padLeft(2, '0');
  return '$h:$m ${d.hour >= 12 ? 'PM' : 'AM'}';
}

String formatMmSs(int seconds) {
  final m = (seconds ~/ 60).toString().padLeft(2, '0');
  final s = (seconds % 60).toString().padLeft(2, '0');
  return '$m:$s';
}

String formatShortDate(DateTime d) {
  const days = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];
  return '${days[d.weekday - 1]}, ${d.month}/${d.day}/${d.year % 100}';
}
