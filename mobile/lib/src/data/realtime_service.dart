import 'dart:async';

import 'package:socket_io_client/socket_io_client.dart' as io;

class RealtimeEvent {
  const RealtimeEvent({
    required this.name,
    this.payload,
    this.connected,
  });

  final String name;
  final Object? payload;
  final bool? connected;
}

class RealtimeService {
  RealtimeService(String serverOrigin) {
    _socket = io.io(
      '$serverOrigin/ws',
      io.OptionBuilder()
          .setTransports(['websocket'])
          .disableAutoConnect()
          .build(),
    );
    _socket.onConnect((_) {
      _events.add(const RealtimeEvent(name: 'connection', connected: true));
    });
    _socket.onDisconnect((_) {
      _events.add(const RealtimeEvent(name: 'connection', connected: false));
    });
    _socket.onConnectError((error) {
      _events.add(
        RealtimeEvent(
          name: 'connection_error',
          payload: error,
          connected: false,
        ),
      );
    });
    for (final event in const [
      'qr_order_pending',
      'qris_payment_received',
      'order_approved',
      'order_status_updated',
      'order_rejected',
    ]) {
      _socket.on(event, (payload) {
        _events.add(RealtimeEvent(name: event, payload: payload));
      });
    }
    _socket.connect();
  }

  final StreamController<RealtimeEvent> _events =
      StreamController<RealtimeEvent>.broadcast();
  late final io.Socket _socket;

  Stream<RealtimeEvent> get events => _events.stream;

  Future<void> dispose() async {
    _socket.dispose();
    await _events.close();
  }
}
