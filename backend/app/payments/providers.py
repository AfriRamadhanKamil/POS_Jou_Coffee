import hashlib
import hmac
import json
from base64 import b64encode
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app


class PaymentGatewayError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class PaymentGatewayProvider:
    name = None

    def notification_order_reference(self, data):
        raise NotImplementedError

    def verify_signature(self, data):
        raise NotImplementedError

    def request(self, method, path, payload=None):
        raise NotImplementedError

    def qr_image_data(self, action_url):
        raise NotImplementedError

    def create_qris_charge(self, order, request_fn):
        raise NotImplementedError

    def get_status(self, order_reference, request_fn):
        raise NotImplementedError

    def normalize_status(self, data, order):
        raise NotImplementedError

    def verify_notification(self, data, order, request_fn):
        raise NotImplementedError


class MidtransProvider(PaymentGatewayProvider):
    name = "midtrans"

    def request(self, method, path, payload=None):
        server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
        if not server_key:
            raise PaymentGatewayError("Payment gateway belum dikonfigurasi")

        base_url = current_app.config.get(
            "PAYMENT_GATEWAY_BASE_URL",
            "https://api.sandbox.midtrans.com"
        ).rstrip("/")
        authorization = b64encode(f"{server_key}:".encode("utf-8")).decode("ascii")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        gateway_request = Request(
            f"{base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        try:
            with urlopen(gateway_request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise PaymentGatewayError(
                f"Payment gateway menolak permintaan (HTTP {error.code})",
                status_code=error.code
            ) from error
        except (URLError, TimeoutError) as error:
            raise PaymentGatewayError("Payment gateway tidak dapat dihubungi") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PaymentGatewayError("Respons payment gateway tidak valid") from error

    def qr_image_data(self, action_url):
        base_url = current_app.config.get(
            "PAYMENT_GATEWAY_BASE_URL",
            "https://api.sandbox.midtrans.com"
        ).rstrip("/")
        configured = urlsplit(base_url)
        target = urlsplit(action_url or "")
        if (
            target.scheme != "https"
            or target.netloc != configured.netloc
            or not target.path.startswith("/v2/")
        ):
            raise PaymentGatewayError("Alamat QR dari payment gateway tidak valid")

        server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
        authorization = b64encode(f"{server_key}:".encode("utf-8")).decode("ascii")
        image_request = Request(
            action_url,
            headers={"Authorization": f"Basic {authorization}", "Accept": "image/png"}
        )
        try:
            with urlopen(image_request, timeout=10) as response:
                content_type = response.headers.get_content_type()
                image = response.read(1_000_001)
        except HTTPError as error:
            raise PaymentGatewayError(
                f"QR pembayaran tidak dapat diambil (HTTP {error.code})"
            ) from error
        except (URLError, TimeoutError) as error:
            raise PaymentGatewayError("QR pembayaran tidak dapat diambil") from error
        if content_type not in {"image/png", "image/jpeg"} or len(image) > 1_000_000:
            raise PaymentGatewayError("Format gambar QR dari payment gateway tidak valid")
        return f"data:{content_type};base64,{b64encode(image).decode('ascii')}"

    def create_qris_charge(self, order, request_fn):
        return request_fn("POST", "/v2/charge", {
            "payment_type": "qris",
            "transaction_details": {
                "order_id": order.order_no,
                "gross_amount": float(order.total)
            },
            "qris": {"acquirer": "gopay"},
            "customer_details": {"first_name": order.customer_name or "Pelanggan"}
        })

    def get_status(self, order_reference, request_fn):
        return request_fn(
            "GET",
            f"/v2/{quote(order_reference, safe='')}/status"
        )

    def normalize_status(self, data, order):
        if not isinstance(data, dict):
            raise PaymentGatewayError("Respons dari payment gateway tidak valid", 502)
        try:
            amount = Decimal(str(data.get("gross_amount", "0")))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise PaymentGatewayError(
                "Nominal dari payment gateway tidak valid",
                502
            ) from error
        transaction_status = data.get("transaction_status")
        transaction_id = data.get("transaction_id")
        if (
            data.get("order_id") != order.order_no
            or not amount.is_finite()
            or amount != order.total
            or not isinstance(transaction_status, str)
            or not isinstance(transaction_id, str)
        ):
            raise PaymentGatewayError("Status pembayaran tidak cocok dengan data gateway", 403)
        return {
            "amount": amount,
            "transaction_status": transaction_status,
            "transaction_id": transaction_id,
            "fraud_status": data.get("fraud_status")
        }

    def notification_order_reference(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("order_id"), str):
            raise PaymentGatewayError("Data notifikasi pembayaran tidak valid", 400)
        return data["order_id"]

    def verify_signature(self, data):
        if not isinstance(data, dict):
            raise PaymentGatewayError("Data notifikasi pembayaran tidak valid", 400)
        order_reference = data.get("order_id")
        status_code = data.get("status_code")
        gross_amount = data.get("gross_amount")
        signature_key = data.get("signature_key")
        if not all(
            isinstance(value, str)
            for value in (order_reference, status_code, gross_amount, signature_key)
        ):
            raise PaymentGatewayError("Data notifikasi pembayaran tidak valid", 400)
        server_key = current_app.config.get("PAYMENT_GATEWAY_SERVER_KEY", "")
        expected_signature = hashlib.sha512(
            f"{order_reference}{status_code}{gross_amount}{server_key}".encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature_key):
            raise PaymentGatewayError("Invalid signature", 403)

    def verify_notification(self, data, order, request_fn):
        order_reference = data.get("order_id")
        status_code = data.get("status_code")
        gross_amount = data.get("gross_amount")
        signature_key = data.get("signature_key")
        transaction_status = data.get("transaction_status")
        transaction_id = data.get("transaction_id")
        if not all(
            isinstance(value, str)
            for value in (
                order_reference,
                status_code,
                gross_amount,
                signature_key,
                transaction_status,
                transaction_id
            )
        ):
            raise PaymentGatewayError("Data notifikasi pembayaran tidak valid", 400)

        self.verify_signature(data)

        try:
            callback_amount = Decimal(gross_amount)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise PaymentGatewayError("Nominal pembayaran tidak valid", 400) from error
        if not callback_amount.is_finite() or callback_amount != order.total:
            raise PaymentGatewayError("Nominal pembayaran tidak sesuai dengan pesanan", 400)

        verified_status = self.normalize_status(
            self.get_status(order_reference, request_fn),
            order
        )
        if (
            verified_status["transaction_status"] != transaction_status
            or verified_status["transaction_id"] != transaction_id
        ):
            raise PaymentGatewayError("Status pembayaran tidak cocok dengan data gateway", 403)

        verified_status["amount"] = callback_amount
        verified_status["fraud_status"] = data.get("fraud_status")
        return verified_status


_PROVIDERS = {MidtransProvider.name: MidtransProvider}


def get_payment_gateway_provider(name):
    provider_class = _PROVIDERS.get(name)
    if provider_class is None:
        raise PaymentGatewayError("Payment gateway yang dipilih belum didukung")
    return provider_class()
