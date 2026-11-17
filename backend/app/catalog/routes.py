from decimal import Decimal, InvalidOperation
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


def _non_negative_decimal(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


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
                    cp.channel_id: float(cp.price)
                    for cp in m.channel_prices
                    if cp.deleted_at is None
                    and cp.channel
                    and cp.channel.deleted_at is None
                    and cp.channel.is_active
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
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return error_response("Nama kategori wajib diisi", 400)
    try:
        sort_order = int(data.get("sort_order", 0))
    except (TypeError, ValueError):
        return error_response("Urutan kategori tidak valid", 400)

    category = Category(
        name=name.strip(),
        sort_order=sort_order,
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
    name = data.get("name")
    category_id = data.get("category_id")
    base_price = _non_negative_decimal(data.get("base_price", 0))
    variants = data.get("variants", [])

    if not isinstance(name, str) or not name.strip() or not category_id:
        return error_response("Nama dan kategori wajib diisi", 400)
    if not Category.query_active().filter_by(id=category_id, is_active=True).first():
        return error_response("Kategori tidak ditemukan", 404)
    if base_price is None:
        return error_response("Harga menu tidak valid", 400)
    if not isinstance(variants, list):
        return error_response("Daftar varian tidak valid", 400)

    parsed_variants = []
    for variant_data in variants:
        if not isinstance(variant_data, dict):
            return error_response("Data varian tidak valid", 400)
        variant_name = variant_data.get("name")
        adjustment = _non_negative_decimal(variant_data.get("price_adjustment", 0))
        if not isinstance(variant_name, str) or not variant_name.strip() or adjustment is None:
            return error_response("Nama atau harga varian tidak valid", 400)
        parsed_variants.append((variant_name.strip(), adjustment, variant_data))

    menu = Menu(
        name=name.strip(),
        category_id=category_id,
        description=data.get("description", ""),
        image_url=data.get("image_url"),
        base_price=base_price,
        is_active=bool(data.get("is_active", True)),
        is_available=bool(data.get("is_available", True))
    )
    db.session.add(menu)
    db.session.flush()

    # Add variants if provided
    for variant_name, adjustment, variant_data in parsed_variants:
        variant = MenuVariant(
            menu_id=menu.id,
            name=variant_name,
            price_adjustment=adjustment,
            is_active=bool(variant_data.get("is_active", True))
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
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("Nama menu tidak valid", 400)
        menu.name = data["name"].strip()
    if "category_id" in data:
        if not Category.query_active().filter_by(
            id=data["category_id"], is_active=True
        ).first():
            return error_response("Kategori tidak ditemukan", 404)
        menu.category_id = data["category_id"]
    if "description" in data:
        menu.description = data["description"]
    if "image_url" in data:
        menu.image_url = data["image_url"]
    if "base_price" in data:
        base_price = _non_negative_decimal(data["base_price"])
        if base_price is None:
            return error_response("Harga menu tidak valid", 400)
        menu.base_price = base_price
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
    name = data.get("name")
    code = data.get("code")
    commission_percent = _non_negative_decimal(data.get("commission_percent", 0))

    if not isinstance(name, str) or not name.strip() or not isinstance(code, str) or not code.strip():
        return error_response("Nama dan kode channel wajib diisi", 400)
    if commission_percent is None or commission_percent > 100:
        return error_response("Persentase komisi harus antara 0 dan 100", 400)
    code = code.strip()
    if SalesChannel.query.filter_by(code=code).first():
        return error_response("Kode channel sudah terdaftar", 409)

    channel = SalesChannel(
        name=name.strip(),
        code=code,
        commission_percent=commission_percent,
        is_active=bool(data.get("is_active", True))
    )
    db.session.add(channel)
    db.session.commit()
    return api_response({"id": channel.id, "name": channel.name}, "Channel berhasil dibuat", 201)


@catalog_bp.route("/menus/<menu_id>/variants", methods=["GET", "POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_menu_variants(menu_id):
    menu = Menu.query_active().filter_by(id=menu_id).first()
    if not menu:
        return error_response("Menu tidak ditemukan", 404)

    if request.method == "GET":
        return api_response([{
            "id": variant.id,
            "name": variant.name,
            "price_adjustment": float(variant.price_adjustment),
            "is_active": variant.is_active
        } for variant in menu.variants if variant.deleted_at is None])

    data = request.get_json() or {}
    name = data.get("name")
    adjustment = _non_negative_decimal(data.get("price_adjustment", 0))
    if not isinstance(name, str) or not name.strip() or adjustment is None:
        return error_response("Nama atau harga varian tidak valid", 400)

    variant = MenuVariant(
        menu_id=menu.id,
        name=name.strip(),
        price_adjustment=adjustment,
        is_active=bool(data.get("is_active", True))
    )
    db.session.add(variant)
    db.session.commit()
    return api_response({"id": variant.id, "name": variant.name}, "Varian dibuat", 201)


@catalog_bp.route("/variants/<variant_id>", methods=["PATCH", "DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_variant(variant_id):
    variant = MenuVariant.query_active().filter_by(id=variant_id).first()
    if not variant:
        return error_response("Varian tidak ditemukan", 404)

    if request.method == "DELETE":
        variant.soft_delete()
        db.session.commit()
        return api_response(None, "Varian dihapus")

    data = request.get_json() or {}
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("Nama varian tidak valid", 400)
        variant.name = data["name"].strip()
    if "price_adjustment" in data:
        adjustment = _non_negative_decimal(data["price_adjustment"])
        if adjustment is None:
            return error_response("Harga varian tidak valid", 400)
        variant.price_adjustment = adjustment
    if "is_active" in data:
        variant.is_active = bool(data["is_active"])

    db.session.commit()
    return api_response({"id": variant.id, "name": variant.name}, "Varian diperbarui")


@catalog_bp.route("/modifier-groups", methods=["GET", "POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_modifier_groups():
    if request.method == "GET":
        groups = ModifierGroup.query_active().all()
        return api_response([{
            "id": group.id,
            "name": group.name,
            "min_selection": group.min_selection,
            "max_selection": group.max_selection,
            "is_required": group.is_required
        } for group in groups])

    data = request.get_json() or {}
    name = data.get("name")
    try:
        min_selection = int(data.get("min_selection", 0))
        max_selection = int(data.get("max_selection", 1))
    except (TypeError, ValueError):
        return error_response("Batas pilihan modifier tidak valid", 400)
    if not isinstance(name, str) or not name.strip():
        return error_response("Nama grup modifier wajib diisi", 400)
    if min_selection < 0 or max_selection < min_selection:
        return error_response("Batas pilihan modifier tidak valid", 400)

    group = ModifierGroup(
        name=name.strip(),
        min_selection=min_selection,
        max_selection=max_selection,
        is_required=bool(data.get("is_required", False))
    )
    db.session.add(group)
    db.session.commit()
    return api_response({"id": group.id, "name": group.name}, "Grup modifier dibuat", 201)


@catalog_bp.route("/modifier-groups/<group_id>", methods=["PATCH", "DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_modifier_group(group_id):
    group = ModifierGroup.query_active().filter_by(id=group_id).first()
    if not group:
        return error_response("Grup modifier tidak ditemukan", 404)

    if request.method == "DELETE":
        group.soft_delete()
        db.session.commit()
        return api_response(None, "Grup modifier dihapus")

    data = request.get_json() or {}
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("Nama grup modifier tidak valid", 400)
        group.name = data["name"].strip()
    try:
        min_selection = int(data.get("min_selection", group.min_selection))
        max_selection = int(data.get("max_selection", group.max_selection))
    except (TypeError, ValueError):
        return error_response("Batas pilihan modifier tidak valid", 400)
    if min_selection < 0 or max_selection < min_selection:
        return error_response("Batas pilihan modifier tidak valid", 400)
    group.min_selection = min_selection
    group.max_selection = max_selection
    if "is_required" in data:
        group.is_required = bool(data["is_required"])
    db.session.commit()
    return api_response({"id": group.id, "name": group.name}, "Grup modifier diperbarui")


@catalog_bp.route("/modifier-groups/<group_id>/modifiers", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_modifier(group_id):
    group = ModifierGroup.query_active().filter_by(id=group_id).first()
    if not group:
        return error_response("Grup modifier tidak ditemukan", 404)

    data = request.get_json() or {}
    name = data.get("name")
    price = _non_negative_decimal(data.get("price", 0))
    if not isinstance(name, str) or not name.strip() or price is None:
        return error_response("Nama atau harga modifier tidak valid", 400)

    modifier = Modifier(
        group_id=group.id,
        name=name.strip(),
        price=price,
        is_active=bool(data.get("is_active", True))
    )
    db.session.add(modifier)
    db.session.commit()
    return api_response({"id": modifier.id, "name": modifier.name}, "Modifier dibuat", 201)


@catalog_bp.route("/modifiers/<modifier_id>", methods=["PATCH", "DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_modifier(modifier_id):
    modifier = Modifier.query_active().filter_by(id=modifier_id).first()
    if not modifier:
        return error_response("Modifier tidak ditemukan", 404)

    if request.method == "DELETE":
        modifier.soft_delete()
        db.session.commit()
        return api_response(None, "Modifier dihapus")

    data = request.get_json() or {}
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("Nama modifier tidak valid", 400)
        modifier.name = data["name"].strip()
    if "price" in data:
        price = _non_negative_decimal(data["price"])
        if price is None:
            return error_response("Harga modifier tidak valid", 400)
        modifier.price = price
    if "is_active" in data:
        modifier.is_active = bool(data["is_active"])
    db.session.commit()
    return api_response({"id": modifier.id, "name": modifier.name}, "Modifier diperbarui")


@catalog_bp.route("/channels/<channel_id>", methods=["PATCH", "DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_channel(channel_id):
    channel = SalesChannel.query_active().filter_by(id=channel_id).first()
    if not channel:
        return error_response("Channel tidak ditemukan", 404)

    if request.method == "DELETE":
        channel.soft_delete()
        db.session.commit()
        return api_response(None, "Channel dihapus")

    data = request.get_json() or {}
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("Nama channel tidak valid", 400)
        channel.name = data["name"].strip()
    if "code" in data:
        if not isinstance(data["code"], str) or not data["code"].strip():
            return error_response("Kode channel tidak valid", 400)
        code = data["code"].strip()
        duplicate = SalesChannel.query.filter(
            SalesChannel.code == code,
            SalesChannel.id != channel.id
        ).first()
        if duplicate:
            return error_response("Kode channel sudah terdaftar", 409)
        channel.code = code
    if "commission_percent" in data:
        commission_percent = _non_negative_decimal(data["commission_percent"])
        if commission_percent is None or commission_percent > 100:
            return error_response("Persentase komisi harus antara 0 dan 100", 400)
        channel.commission_percent = commission_percent
    if "is_active" in data:
        channel.is_active = bool(data["is_active"])
    db.session.commit()
    return api_response({"id": channel.id, "name": channel.name}, "Channel diperbarui")


@catalog_bp.route("/channels/<channel_id>/menu-prices", methods=["GET", "POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def manage_channel_prices(channel_id):
    channel = SalesChannel.query_active().filter_by(id=channel_id).first()
    if not channel:
        return error_response("Channel tidak ditemukan", 404)

    if request.method == "GET":
        return api_response([{
            "menu_id": price.menu_id,
            "price": float(price.price)
        } for price in channel.channel_prices if price.deleted_at is None])

    data = request.get_json() or {}
    menu_id = data.get("menu_id")
    price = _non_negative_decimal(data.get("price"))
    menu = Menu.query_active().filter_by(id=menu_id).first() if menu_id else None
    if not menu:
        return error_response("Menu tidak ditemukan", 404)
    if price is None:
        return error_response("Harga channel tidak valid", 400)

    channel_price = MenuChannelPrice.query_active().filter_by(
        channel_id=channel.id,
        menu_id=menu.id
    ).first()
    status_code = 200
    if channel_price:
        channel_price.price = price
    else:
        channel_price = MenuChannelPrice(
            channel_id=channel.id,
            menu_id=menu.id,
            price=price
        )
        db.session.add(channel_price)
        status_code = 201
    db.session.commit()
    return api_response({
        "menu_id": menu.id,
        "price": float(channel_price.price)
    }, "Harga channel disimpan", status_code)


@catalog_bp.route(
    "/channels/<channel_id>/menu-prices/<menu_id>",
    methods=["DELETE"]
)
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_channel_price(channel_id, menu_id):
    channel_price = MenuChannelPrice.query_active().filter_by(
        channel_id=channel_id,
        menu_id=menu_id
    ).first()
    if not channel_price:
        return error_response("Harga channel tidak ditemukan", 404)
    channel_price.soft_delete()
    db.session.commit()
    return api_response(None, "Harga channel dihapus")

