import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/qmmc_theme.dart';
import 'design_b_state.dart';

class PatientIdPage extends ConsumerStatefulWidget {
  const PatientIdPage({super.key});

  @override
  ConsumerState<PatientIdPage> createState() => _PatientIdPageState();
}

class _PatientIdPageState extends ConsumerState<PatientIdPage> {
  final TextEditingController _controller = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final id = _controller.text.trim().toUpperCase();
    // Format check only. Server/cached patient lookup is not wired yet.
    if (!RegExp(r'^[A-Z0-9-]{3,20}$').hasMatch(id)) {
      setState(() => _error =
          'Enter a valid Patient ID (3-20 letters, numbers, or dashes).');
      return;
    }
    ref.read(designBProvider.notifier).setPatient(id);
    context.go('/b/exercises');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 32),
              // Swap this icon for the official QMMC seal once approved by the client.
              const CircleAvatar(
                radius: 44,
                backgroundColor: QmmcColors.deepGreen,
                child: Icon(Icons.local_hospital, size: 44, color: Colors.white),
              ),
              const SizedBox(height: 20),
              const Text(
                'Quirino Memorial Medical Center',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: QmmcColors.deepGreen,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Pang-alaalang Sentrong Medikal Quirino',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontStyle: FontStyle.italic,
                  color: QmmcColors.muted,
                ),
              ),
              const SizedBox(height: 40),
              const Text(
                'Enter Patient ID',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _controller,
                textCapitalization: TextCapitalization.characters,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  hintText: 'e.g. QMMC-0001',
                  errorText: _error,
                ),
                onChanged: (_) {
                  if (_error != null) setState(() => _error = null);
                },
              ),
              const SizedBox(height: 20),
              FilledButton(onPressed: _submit, child: const Text('Continue')),
            ],
          ),
        ),
      ),
    );
  }
}
