class AuthUser {
  const AuthUser({
    required this.id,
    required this.fullName,
    required this.email,
    required this.role,
  });

  final int id;
  final String fullName;
  final String email;
  final String role;

  bool get isPatient => role == 'patient';

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] as int,
      fullName: json['full_name'] as String,
      email: json['email'] as String,
      role: json['role'] as String,
    );
  }
}
