from decimal import Decimal
from app import create_app
from app.extensions import db
from app.common.auth import hash_password, ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_KASIR
from app.auth.models import User
from app.catalog.models import Category, Menu, MenuVariant, SalesChannel, ModifierGroup, Modifier
from app.inventory.models import Unit, Ingredient, Recipe, RecipeItem, StockBalance
from app.orders.models import Table
from app.tables.routes import generate_table_qr_token


def seed_database():
    app = create_app("development")
    with app.app_context():
        print("Creating all tables if not exist...")
        db.create_all()

        # Seed Users
        if not User.query.filter_by(username="superadmin").first():
            superadmin = User(
                username="superadmin",
                password_hash=hash_password("superadmin123"),
                pin_hash=hash_password("999999"),
                name="Super Admin Jou Coffee",
                role=ROLE_SUPER_ADMIN,
                is_active=True
            )
            db.session.add(superadmin)
            print("Created superadmin user (superadmin / superadmin123 / PIN: 999999)")

        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=hash_password("admin123"),
                pin_hash=hash_password("123456"),
                name="Owner Jou Coffee",
                role=ROLE_ADMIN,
                is_active=True
            )
            db.session.add(admin)
            print("Created admin user (admin / admin123 / PIN: 123456)")

        if not User.query.filter_by(username="kasir").first():
            kasir = User(
                username="kasir",
                password_hash=hash_password("kasir123"),
                pin_hash=hash_password("654321"),
                name="Kasir Utama",
                role=ROLE_KASIR,
                is_active=True
            )
            db.session.add(kasir)
            print("Created kasir user (kasir / kasir123 / PIN: 654321)")

        # Seed Units
        units_data = [
            ("Gram", "g"),
            ("Milliliter", "ml"),
            ("Pieces", "pcs"),
            ("Shot", "shot")
        ]
        unit_map = {}
        for name, sym in units_data:
            u = Unit.query.filter_by(symbol=sym).first()
            if not u:
                u = Unit(name=name, symbol=sym)
                db.session.add(u)
                db.session.flush()
            unit_map[sym] = u

        # Seed Ingredients
        ing_data = [
            ("Biji Kopi House Blend", "g", Decimal("500"), Decimal("0.25"), Decimal("5000")),
            ("Fresh Milk", "ml", Decimal("1000"), Decimal("0.02"), Decimal("10000")),
            ("Sirup Gula Aren", "ml", Decimal("500"), Decimal("0.03"), Decimal("3000")),
        ]
        ing_map = {}
        for name, unit_sym, min_stk, price, initial_stk in ing_data:
            ing = Ingredient.query.filter_by(name=name).first()
            if not ing:
                ing = Ingredient(
                    name=name,
                    unit_id=unit_map[unit_sym].id,
                    min_stock=min_stk,
                    last_purchase_price=price,
                    is_active=True
                )
                db.session.add(ing)
                db.session.flush()

                balance = StockBalance(ingredient_id=ing.id, current_stock=initial_stk)
                db.session.add(balance)
            ing_map[name] = ing

        # Seed Categories & Menus
        cat_coffee = Category.query.filter_by(name="Coffee").first()
        if not cat_coffee:
            cat_coffee = Category(name="Coffee", sort_order=1)
            db.session.add(cat_coffee)
            db.session.flush()

        cat_non_coffee = Category.query.filter_by(name="Non-Coffee").first()
        if not cat_non_coffee:
            cat_non_coffee = Category(name="Non-Coffee", sort_order=2)
            db.session.add(cat_non_coffee)
            db.session.flush()

        # Menu: Kopi Susu Jou
        menu_kopsus = Menu.query.filter_by(name="Kopi Susu Jou").first()
        if not menu_kopsus:
            menu_kopsus = Menu(
                category_id=cat_coffee.id,
                name="Kopi Susu Jou",
                description="Espresso premium dengan fresh milk dan gula aren asli",
                base_price=Decimal("18000.00"),
                is_active=True,
                is_available=True
            )
            db.session.add(menu_kopsus)
            db.session.flush()

            # Variants: Regular & Large
            v_reg = MenuVariant(menu_id=menu_kopsus.id, name="Regular", price_adjustment=Decimal("0.00"))
            v_large = MenuVariant(menu_id=menu_kopsus.id, name="Large", price_adjustment=Decimal("4000.00"))
            db.session.add_all([v_reg, v_large])
            db.session.flush()

            # Recipe for Kopi Susu Jou Regular
            recipe = Recipe(menu_id=menu_kopsus.id, variant_id=v_reg.id, notes="Standard recipe regular")
            db.session.add(recipe)
            db.session.flush()

            db.session.add(RecipeItem(recipe_id=recipe.id, ingredient_id=ing_map["Biji Kopi House Blend"].id, quantity=Decimal("18.0000")))
            db.session.add(RecipeItem(recipe_id=recipe.id, ingredient_id=ing_map["Fresh Milk"].id, quantity=Decimal("120.0000")))
            db.session.add(RecipeItem(recipe_id=recipe.id, ingredient_id=ing_map["Sirup Gula Aren"].id, quantity=Decimal("20.0000")))

        # Seed Sales Channels
        channels_data = [
            ("POS Kasir", "POS", Decimal("0.00")),
            ("GoFood", "GOFOOD", Decimal("20.00")),
            ("GrabFood", "GRABFOOD", Decimal("20.00")),
            ("ShopeeFood", "SHOPEEFOOD", Decimal("20.00")),
        ]
        for name, code, comm in channels_data:
            ch = SalesChannel.query.filter_by(code=code).first()
            if not ch:
                ch = SalesChannel(name=name, code=code, commission_percent=comm, is_active=True)
                db.session.add(ch)

        # Seed Tables
        for i in range(1, 6):
            t_num = str(i)
            tbl = Table.query.filter_by(table_number=t_num).first()
            if not tbl:
                tbl = Table(
                    table_number=t_num,
                    name=f"Meja {t_num}",
                    qr_token=generate_table_qr_token(),
                    is_active=True
                )
                db.session.add(tbl)

        db.session.commit()
        print("✅ Database seeding completed successfully!")


if __name__ == "__main__":
    seed_database()

