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
  final _serverController = TextEditingController();
  bool _usePin = false;
  bool _obscurePassword = true;

  @override
  void initState() {
    super.initState();
    _serverController.text = ref.read(apiClientProvider).dio.options.baseUrl;
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _serverController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    try {
      await ref
          .read(authControllerProvider.notifier)
          .setServerUrl(_serverController.text);
    } on FormatException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
      return;
    }
    await ref
        .read(authControllerProvider.notifier)
        .login(
          _usePin ? 'kasir' : _usernameController.text,
          _passwordController.text,
          isPin: _usePin,
        );
  }

  void _enterPin(String digit) {
    final current = _passwordController.text;
    if (digit == 'hapus') {
      if (current.isNotEmpty) {
        _passwordController.text = current.substring(0, current.length - 1);
      }
    } else if (digit == 'bersihkan') {
      _passwordController.clear();
    } else if (current.length < 6) {
      _passwordController.text = '$current$digit';
    }
    _passwordController.selection = TextSelection.collapsed(
      offset: _passwordController.text.length,
    );
    setState(() {});
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
                        const SizedBox(height: 28),
                        TextFormField(
                          controller: _serverController,
                          keyboardType: TextInputType.url,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Alamat server',
                            hintText: 'https://server.example.com/api/v1',
                            prefixIcon: Icon(Icons.dns_outlined),
                          ),
                          validator: (value) =>
                              value == null || value.trim().isEmpty
                              ? 'Alamat server wajib diisi.'
                              : null,
                        ),
                        const SizedBox(height: 14),
                        SegmentedButton<bool>(
                          segments: const [
                            ButtonSegment(
                              value: false,
                              label: Text('Password'),
                              icon: Icon(Icons.lock_outline),
                            ),
                            ButtonSegment(
                              value: true,
                              label: Text('PIN Kasir'),
                              icon: Icon(Icons.dialpad_outlined),
                            ),
                          ],
                          selected: {_usePin},
                          onSelectionChanged: (selection) {
                            setState(() {
                              _usePin = selection.first;
                              if (_usePin) {
                                _usernameController.text = 'kasir';
                              }
                              _passwordController.clear();
                            });
                          },
                        ),
                        const SizedBox(height: 14),
                        if (!_usePin)
                          TextFormField(
                            controller: _usernameController,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.username],
                            decoration: const InputDecoration(
                              labelText: 'Username',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                value == null || value.trim().isEmpty
                                ? 'Username wajib diisi.'
                                : null,
                          )
                        else
                          TextFormField(
                            initialValue: 'kasir',
                            readOnly: true,
                            decoration: const InputDecoration(
                              labelText: 'Username kasir',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                          ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _usePin || _obscurePassword,
                          maxLength: _usePin ? 6 : null,
                          readOnly: _usePin,
                          keyboardType: _usePin
                              ? TextInputType.number
                              : TextInputType.text,
                          autofillHints: _usePin
                              ? null
                              : const [AutofillHints.password],
                          textInputAction: TextInputAction.done,
                          onFieldSubmitted: (_) => _submit(),
                          decoration: InputDecoration(
                            labelText: _usePin ? 'PIN 6 digit' : 'Password',
                            prefixIcon: Icon(
                              _usePin
                                  ? Icons.dialpad_outlined
                                  : Icons.lock_outline,
                            ),
                            counterText: _usePin ? '' : null,
                            suffixIcon: _usePin
                                ? null
                                : IconButton(
                                    onPressed: () => setState(
                                      () =>
                                          _obscurePassword = !_obscurePassword,
                                    ),
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_outlined
                                          : Icons.visibility_off_outlined,
                                    ),
                                  ),
                          ),
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return _usePin
                                  ? 'PIN wajib diisi.'
                                  : 'Password wajib diisi.';
                            }
                            if (_usePin &&
                                (value.length != 6 ||
                                    !RegExp(r'^\d{6}$').hasMatch(value))) {
                              return 'PIN harus terdiri dari 6 digit.';
                            }
                            return null;
                          },
                        ),
                        if (_usePin) ...[
                          const SizedBox(height: 8),
                          SizedBox(
                            height: 190,
                            child: GridView.count(
                              physics: const NeverScrollableScrollPhysics(),
                              crossAxisCount: 3,
                              mainAxisSpacing: 6,
                              crossAxisSpacing: 6,
                              childAspectRatio: 2.6,
                              children: [
                                for (final digit in const [
                                  '1',
                                  '2',
                                  '3',
                                  '4',
                                  '5',
                                  '6',
                                  '7',
                                  '8',
                                  '9',
                                  'bersihkan',
                                  '0',
                                  'hapus',
                                ])
                                  OutlinedButton(
                                    onPressed: () => _enterPin(digit),
                                    child: digit == 'hapus'
                                        ? const Icon(Icons.backspace_outlined)
                                        : digit == 'bersihkan'
                                        ? const Text('Hapus semua')
                                        : Text(digit),
                                  ),
                              ],
                            ),
                          ),
                        ],
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
                          'Jika pernah login online di perangkat ini, login offline tersedia hingga 7 hari.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(color: colors.onSurfaceVariant),
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
