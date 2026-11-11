import secrets
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ROLE_ADMIN, ROLE_SUPER_ADMIN, ALL_ROLES
from app.orders.models import Table

tables_bp = Blueprint("tables", __name__, url_prefix="/api/v1/tables")


def generate_table_qr_token():
    return secrets.token_urlsafe(32)


@tables_bp.route("", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def list_tables():
    tables = Table.query_active().order_by(Table.table_number).all()
    result = [{
        "id": t.id,
        "table_number": t.table_number,
        "name": t.name,
        "qr_token": t.qr_token,
        "qr_url": f"/qr/{t.qr_token}",
        "is_active": t.is_active
    } for t in tables]
    return api_response(result)


@tables_bp.route("", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_table():
    data = request.get_json() or {}
    table_number = str(data.get("table_number", "")).strip()
    name = data.get("name", f"Meja {table_number}").strip()

    if not table_number:
        return error_response("Nomor meja wajib diisi", 400)

    existing = Table.query_active().filter_by(table_number=table_number).first()
    if existing:
        return error_response(f"Meja nomor {table_number} sudah ada", 400)

    table = Table(
        table_number=table_number,
        name=name,
        qr_token=generate_table_qr_token(),
        is_active=True
    )
    db.session.add(table)
    db.session.commit()
    return api_response({
        "id": table.id,
        "table_number": table.table_number,
        "qr_token": table.qr_token,
        "qr_url": f"/qr/{table.qr_token}"
    }, "Meja berhasil dibuat", 201)


@tables_bp.route("/<table_id>/regenerate-token", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def regenerate_qr_token(table_id):
    table = Table.query_active().filter_by(id=table_id).first()
    if not table:
        return error_response("Meja tidak ditemukan", 404)

    table.qr_token = generate_table_qr_token()
    db.session.commit()
    return api_response({
        "id": table.id,
        "table_number": table.table_number,
        "new_qr_token": table.qr_token,
        "qr_url": f"/qr/{table.qr_token}"
    }, "QR Token berhasil diperbarui (token lama tidak berlaku lagi)")
