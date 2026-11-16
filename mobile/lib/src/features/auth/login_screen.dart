import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/providers.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _pinController = TextEditingController();
  bool _isPinMode = false;
  bool _obscurePassword = true;
  bool _obscurePin = true;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_isPinMode) {
      final username = _usernameController.text.trim().isEmpty
          ? 'kasir'
          : _usernameController.text.trim();
      await ref.read(authControllerProvider.notifier).login(
            username,
            pin: _pinController.text.trim(),
          );
    } else {
      await ref.read(authControllerProvider.notifier).login(
            _usernameController.text.trim(),
            password: _passwordController.text,
          );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Card(
                elevation: 0,
                color: Colors.white,
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        CircleAvatar(
                          radius: 32,
                          backgroundColor: colors.primaryContainer,
                          child: Icon(
                            Icons.coffee,
                            color: colors.primary,
                            size: 32,
                          ),
                        ),
                        const SizedBox(height: 18),
                        Text(
                          'Selamat datang',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Masuk untuk mulai menggunakan POS Jou Coffee.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(color: colors.onSurfaceVariant),
                        ),
                        const SizedBox(height: 20),
                        SegmentedButton<bool>(
                          segments: const [
                            ButtonSegment<bool>(
                              value: false,
                              label: Text('Password'),
                              icon: Icon(Icons.password_outlined),
                            ),
                            ButtonSegment<bool>(
                              value: true,
                              label: Text('PIN Kasir'),
                              icon: Icon(Icons.pin_outlined),
                            ),
                          ],
                          selected: {_isPinMode},
                          onSelectionChanged: (newSelection) {
                            setState(() {
                              _isPinMode = newSelection.first;
                              if (_isPinMode &&
                                  _usernameController.text.trim().isEmpty) {
                                _usernameController.text = 'kasir';
                              }
                            });
                          },
                        ),
                        const SizedBox(height: 18),
                        TextFormField(
                          controller: _usernameController,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.username],
                          decoration: const InputDecoration(
                            labelText: 'Username',
                            prefixIcon: Icon(Icons.person_outline),
                          ),
                          validator: (value) => value == null || value.trim().isEmpty
                              ? 'Username wajib diisi.'
                              : null,
                        ),
                        const SizedBox(height: 14),
                        if (_isPinMode)
                          TextFormField(
                            controller: _pinController,
                            obscureText: _obscurePin,
                            keyboardType: TextInputType.number,
                            maxLength: 6,
                            textInputAction: TextInputAction.done,
                            onFieldSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'PIN 6 Digit',
                              prefixIcon: const Icon(Icons.pin_outlined),
                              counterText: '',
                              suffixIcon: IconButton(
                                onPressed: () => setState(
                                  () => _obscurePin = !_obscurePin,
                                ),
                                icon: Icon(
                                  _obscurePin
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ),
                            validator: (value) =>
                                value == null || value.trim().length != 6
                                    ? 'PIN harus 6 digit angka.'
                                    : null,
                          )
                        else
                          TextFormField(
                            controller: _passwordController,
                            obscureText: _obscurePassword,
                            textInputAction: TextInputAction.done,
                            autofillHints: const [AutofillHints.password],
                            onFieldSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                onPressed: () => setState(
                                  () => _obscurePassword = !_obscurePassword,
                                ),
                                icon: Icon(
                                  _obscurePassword
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Password wajib diisi.'
                                : null,
                          ),
                        if (auth.error != null) ...[
                          const SizedBox(height: 14),
                          Text(
                            auth.error!,
                            style: TextStyle(color: colors.error),
                            textAlign: TextAlign.center,
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton(
                          onPressed: auth.loading ? null : _submit,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 13),
                            child: auth.loading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Text('Masuk'),
                          ),
                        ),
                        const SizedBox(height: 14),
                        Text(
                          'Pastikan perangkat terhubung ke server untuk masuk.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
