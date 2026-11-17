from flask import current_app

from app.auth.models import Device, User
from app.common.auth import ROLE_ADMIN, ROLE_KASIR, ROLE_SUPER_ADMIN


def send_cashier_notification(payload, title, body, notification_type):
    service_account_file = current_app.config.get("FCM_SERVICE_ACCOUNT_FILE")
    if not service_account_file:
        current_app.logger.warning(
            "FCM is not configured; QR order remains available in the cashier inbox"
        )
        return

    import firebase_admin
    from firebase_admin import credentials, exceptions, messaging

    try:
        try:
            firebase_app = firebase_admin.get_app("jou_coffee")
        except ValueError:
            firebase_app = firebase_admin.initialize_app(
                credentials.Certificate(service_account_file),
                name="jou_coffee"
            )
    except (OSError, ValueError, exceptions.FirebaseError):
        current_app.logger.exception("Unable to initialize Firebase Admin")
        return

    devices = (
        Device.query.join(User)
        .filter(
            Device.fcm_token.isnot(None),
            Device.fcm_token != "",
            Device.is_revoked.is_(False),
            Device.deleted_at.is_(None),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.role.in_((ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN))
        )
        .all()
    )
    for device in devices:
        message = messaging.Message(
            token=device.fcm_token,
            notification=messaging.Notification(title=title, body=body),
            data={
                "order_id": payload["order_id"],
                "order_no": payload["order_no"],
                "type": notification_type
            }
        )
        try:
            messaging.send(message, app=firebase_app)
        except exceptions.FirebaseError:
            current_app.logger.exception(
                "Failed to send FCM notification for QR order %s",
                payload["order_id"]
            )


def send_qr_order_notification(payload):
    send_cashier_notification(
        payload,
        "Pesanan QR baru",
        f"Pesanan {payload['order_no']} menunggu persetujuan kasir",
        "qr_order_pending"
    )
