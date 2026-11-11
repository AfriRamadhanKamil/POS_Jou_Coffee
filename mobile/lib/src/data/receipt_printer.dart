import 'package:esc_pos_utils_plus/esc_pos_utils_plus.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:print_bluetooth_thermal/print_bluetooth_thermal.dart';

import 'pos_repository.dart';

class ReceiptPrinter {
  Future<void> printOrder(
    BuildContext context, {
    required String orderNumber,
    required List<CartLine> items,
    required double total,
  }) async {
    if (!await PrintBluetoothThermal.isPermissionBluetoothGranted) {
      throw Exception('Izin Bluetooth belum diberikan pada perangkat.');
    }
    final printers = await PrintBluetoothThermal.pairedBluetooths;
    if (printers.isEmpty) {
      throw Exception('Tidak ada printer Bluetooth yang terhubung ke perangkat.');
    }
    if (!context.mounted) return;
    final selected = await showDialog<BluetoothInfo>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Pilih printer'),
        children: [
          for (final printer in printers)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, printer),
              child: Text(printer.name),
            ),
          SimpleDialogOption(
            onPressed: () => Navigator.pop(context),
            child: const Text('Batal'),
          ),
        ],
      ),
    );
    if (selected == null) return;

    final connected = await PrintBluetoothThermal.connect(
      macPrinterAddress: selected.macAdress,
    );
    if (!connected) {
      throw Exception('Tidak dapat terhubung ke printer ${selected.name}.');
    }
    try {
      final profile = await CapabilityProfile.load();
      final generator = Generator(PaperSize.mm58, profile);
      final bytes = <int>[
        ...generator.text(
          'JOU COFFEE',
          styles: const PosStyles(
            align: PosAlign.center,
            bold: true,
            height: PosTextSize.size2,
            width: PosTextSize.size2,
          ),
        ),
        ...generator.text(
          'Bukti Pesanan',
          styles: const PosStyles(align: PosAlign.center),
        ),
        ...generator.hr(),
        ...generator.text('No: $orderNumber'),
        ...generator.text(
          DateFormat('dd/MM/yyyy HH:mm').format(
            DateTime.now().toUtc().add(const Duration(hours: 7)),
          ),
        ),
        ...generator.hr(),
        for (final item in items) ...[
          ...generator.text(
            '${item.quantity}x ${item.menu.name}'
            '${item.variant == null ? '' : ' (${item.variant!.name})'}',
          ),
          for (final modifier in item.modifiers)
            ...generator.text('   + ${modifier.name}'),
          ...generator.text(_rupiah(item.unitPrice * item.quantity)),
        ],
        ...generator.hr(),
        ...generator.text(
          'TOTAL  ${_rupiah(total)}',
          styles: const PosStyles(bold: true, height: PosTextSize.size2),
        ),
        ...generator.feed(3),
        ...generator.cut(),
      ];
      final printed = await PrintBluetoothThermal.writeBytes(bytes);
      if (!printed) throw Exception('Printer gagal mencetak struk.');
    } finally {
      await PrintBluetoothThermal.disconnect;
    }
  }
}

String _rupiah(num amount) => 'Rp ${amount.toStringAsFixed(0)}';
