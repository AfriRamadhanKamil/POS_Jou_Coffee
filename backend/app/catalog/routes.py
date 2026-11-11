from decimal import Decimal
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ROLE_ADMIN, ROLE_SUPER_ADMIN, ALL_ROLES
from app.catalog.models import (
    Category, Menu, MenuVariant, ModifierGroup, Modifier,
    SalesChannel, MenuChannelPrice
)

catalog_bp = Blueprint("catalog", __name__, url_prefix="/api/v1")


# ==================== POS CATALOG (READ-ONLY) ====================

@catalog_bp.route("/menus/catalog", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def get_pos_catalog():
    """
    Returns full menu catalog for POS screen in one call.
    Includes active categories, menus with active variants, modifier groups, and channels.
    """
    categories = Category.query_active().filter_by(is_active=True).order_by(Category.sort_order).all()
    channels = SalesChannel.query_active().filter_by(is_active=True).all()
    modifier_groups = ModifierGroup.query_active().all()

    catalog_data = {
        "categories": [{
            "id": c.id,
            "name": c.name,
            "sort_order": c.sort_order,
            "menus": [{
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "image_url": m.image_url,
                "base_price": float(m.base_price),
                "is_available": m.is_available,
                "variants": [{
                    "id": v.id,
                    "name": v.name,
                    "price_adjustment": float(v.price_adjustment)
                } for v in m.variants if v.deleted_at is None and v.is_active],
                "channel_prices": {
                    cp.channel_id: float(cp.price) for cp in m.channel_prices if cp.deleted_at is None
                }
            } for m in c.menus if m.deleted_at is None and m.is_active]
        } for c in categories],
        "modifier_groups": [{
            "id": mg.id,
            "name": mg.name,
            "min_selection": mg.min_selection,
            "max_selection": mg.max_selection,
            "is_required": mg.is_required,
            "modifiers": [{
                "id": mod.id,
                "name": mod.name,
                "price": float(mod.price)
            } for mod in mg.modifiers if mod.deleted_at is None and mod.is_active]
        } for mg in modifier_groups],
        "channels": [{
            "id": ch.id,
            "name": ch.name,
            "code": ch.code,
            "commission_percent": float(ch.commission_percent)
        } for ch in channels]
    }

    return api_response(catalog_data)


# ==================== CATEGORIES CRUD ====================

@catalog_bp.route("/categories", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_categories():
    categories = Category.query_active().order_by(Category.sort_order).all()
    return api_response([{
        "id": c.id,
        "name": c.name,
        "sort_order": c.sort_order,
        "is_active": c.is_active
    } for c in categories])


@catalog_bp.route("/categories", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_category():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return error_response("Nama kategori wajib diisi", 400)

    category = Category(
        name=name,
        sort_order=int(data.get("sort_order", 0)),
        is_active=bool(data.get("is_active", True))
    )
    db.session.add(category)
    db.session.commit()
    return api_response({"id": category.id, "name": category.name}, "Kategori dibuat", 201)


@catalog_bp.route("/categories/<category_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_category(category_id):
    category = Category.query_active().filter_by(id=category_id).first()
    if not category:
        return error_response("Kategori tidak ditemukan", 404)

    data = request.get_json() or {}
    if "name" in data:
        category.name = data["name"].strip()
    if "sort_order" in data:
        category.sort_order = int(data["sort_order"])
    if "is_active" in data:
        category.is_active = bool(data["is_active"])

    db.session.commit()
    return api_response({"id": category.id, "name": category.name}, "Kategori diperbarui")


@catalog_bp.route("/categories/<category_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_category(category_id):
    category = Category.query_active().filter_by(id=category_id).first()
    if not category:
        return error_response("Kategori tidak ditemukan", 404)

    category.soft_delete()
    db.session.commit()
    return api_response(None, "Kategori dihapus")


# ==================== MENUS CRUD ====================

@catalog_bp.route("/menus", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_menus():
    menus = Menu.query_active().all()
    result = [{
        "id": m.id,
        "category_id": m.category_id,
        "category_name": m.category.name if m.category else None,
        "name": m.name,
        "description": m.description,
        "base_price": float(m.base_price),
        "is_active": m.is_active,
        "is_available": m.is_available,
        "variants": [{
            "id": v.id,
            "name": v.name,
            "price_adjustment": float(v.price_adjustment),
            "is_active": v.is_active
        } for v in m.variants if v.deleted_at is None]
    } for m in menus]
    return api_response(result)


@catalog_bp.route("/menus", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_menu():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    category_id = data.get("category_id")
    base_price = data.get("base_price", 0)

    if not name or not category_id:
        return error_response("Nama dan kategori wajib diisi", 400)

    menu = Menu(
        name=name,
        category_id=category_id,
        description=data.get("description", ""),
        image_url=data.get("image_url"),
        base_price=Decimal(str(base_price)),
        is_active=bool(data.get("is_active", True)),
        is_available=bool(data.get("is_available", True))
    )
    db.session.add(menu)
    db.session.flush()

    # Add variants if provided
    variants = data.get("variants", [])
    for v in variants:
        variant = MenuVariant(
            menu_id=menu.id,
            name=v.get("name"),
            price_adjustment=Decimal(str(v.get("price_adjustment", 0))),
            is_active=bool(v.get("is_active", True))
        )
        db.session.add(variant)

    db.session.commit()
    return api_response({"id": menu.id, "name": menu.name}, "Menu berhasil dibuat", 201)


@catalog_bp.route("/menus/<menu_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_menu(menu_id):
    menu = Menu.query_active().filter_by(id=menu_id).first()
    if not menu:
        return error_response("Menu tidak ditemukan", 404)

    data = request.get_json() or {}
    if "name" in data:
        menu.name = data["name"].strip()
    if "category_id" in data:
        menu.category_id = data["category_id"]
    if "description" in data:
        menu.description = data["description"]
    if "image_url" in data:
        menu.image_url = data["image_url"]
    if "base_price" in data:
        menu.base_price = Decimal(str(data["base_price"]))
    if "is_active" in data:
        menu.is_active = bool(data["is_active"])
    if "is_available" in data:
        menu.is_available = bool(data["is_available"])

    db.session.commit()
    return api_response({"id": menu.id, "name": menu.name}, "Menu berhasil diperbarui")


@catalog_bp.route("/menus/<menu_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_menu(menu_id):
    menu = Menu.query_active().filter_by(id=menu_id).first()
    if not menu:
        return error_response("Menu tidak ditemukan", 404)

    menu.soft_delete()
    db.session.commit()
    return api_response(None, "Menu berhasil dihapus")


# ==================== SALES CHANNELS ====================

@catalog_bp.route("/channels", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_channels():
    channels = SalesChannel.query_active().all()
    return api_response([{
        "id": ch.id,
        "name": ch.name,
        "code": ch.code,
        "commission_percent": float(ch.commission_percent),
        "is_active": ch.is_active
    } for ch in channels])


@catalog_bp.route("/channels", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_channel():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    code = data.get("code", "").strip()
    commission_percent = data.get("commission_percent", 0.0)

    if not name or not code:
        return error_response("Nama dan kode channel wajib diisi", 400)

    channel = SalesChannel(
        name=name,
        code=code,
        commission_percent=Decimal(str(commission_percent)),
        is_active=bool(data.get("is_active", True))
    )
    db.session.add(channel)
    db.session.commit()
    return api_response({"id": channel.id, "name": channel.name}, "Channel berhasil dibuat", 201)

