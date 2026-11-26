
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from uuid import uuid4

purchases = Blueprint("purchases", __name__)


def check_purchase_access():
    if not current_user.has_role("Admin"):
        abort(403)


@purchases.route("/purchases", methods=["GET", "POST"])
@login_required
def purchase_entry():

    check_purchase_access()

    if request.method == "POST":
        try:
            supplier_id = int(request.form["supplier_id"])
            inventory_item_id = int(request.form["inventory_item_id"])
            quantity = Decimal(request.form["quantity"])
            unit_price = Decimal(request.form["unit_price"])

            if not quantity.is_finite() or not unit_price.is_finite():
                raise ValueError("Enter valid numeric values.")

            if quantity <= 0 or unit_price < 0:
                raise ValueError(
                    "Quantity must be positive and price cannot be negative."
                )

            supplier = db.session.execute(
                text("SELECT id FROM suppliers WHERE id = :id"),
                {"id": supplier_id}
            ).first()

            item = db.session.execute(
                text("""
                    SELECT id, unit
                    FROM inventory_items
                    WHERE id = :id AND category = 'raw_material'
                """),
                {"id": inventory_item_id}
            ).first()

            if not supplier:
                raise ValueError("Invalid supplier.")

            if not item:
                raise ValueError("Invalid raw material.")

            total_amount = (quantity * unit_price).quantize(
                Decimal("0.01")
            )

            purchase_number = (
                f"PUR-{datetime.now():%Y%m%d}-"
                f"{uuid4().hex[:6].upper()}"
            )

            purchase_result = db.session.execute(
                text("""
                    INSERT INTO purchases
                    (
                        purchase_number,
                        supplier_id,
                        purchase_date,
                        total_amount,
                        status,
                        created_by
                    )
                    VALUES
                    (
                        :purchase_number,
                        :supplier_id,
                        :purchase_date,
                        :total_amount,
                        'received',
                        :created_by
                    )
                """),
                {
                    "purchase_number": purchase_number,
                    "supplier_id": supplier_id,
                    "purchase_date": date.today(),
                    "total_amount": total_amount,
                    "created_by": current_user.id
                }
            )

            purchase_id = purchase_result.lastrowid

            db.session.execute(
                text("""
                    INSERT INTO purchase_items
                    (
                        purchase_id,
                        inventory_item_id,
                        quantity,
                        unit,
                        unit_price,
                        line_total
                    )
                    VALUES
                    (
                        :purchase_id,
                        :item_id,
                        :quantity,
                        :unit,
                        :unit_price,
                        :line_total
                    )
                """),
                {
                    "purchase_id": purchase_id,
                    "item_id": inventory_item_id,
                    "quantity": quantity,
                    "unit": item.unit,
                    "unit_price": unit_price,
                    "line_total": total_amount
                }
            )

            db.session.execute(
                text("""
                    INSERT INTO stock_movements
                    (
                        inventory_item_id,
                        movement_type,
                        quantity_in,
                        quantity_out,
                        unit,
                        source_type,
                        source_id,
                        notes,
                        created_by
                    )
                    VALUES
                    (
                        :item_id,
                        'purchase',
                        :quantity,
                        0,
                        :unit,
                        'purchase',
                        :purchase_id,
                        'Purchase received',
                        :created_by
                    )
                """),
                {
                    "item_id": inventory_item_id,
                    "quantity": quantity,
                    "unit": item.unit,
                    "purchase_id": purchase_id,
                    "created_by": current_user.id
                }
            )

            db.session.commit()

            flash(
                f"Purchase {purchase_number} recorded successfully!",
                "success"
            )

            return redirect(url_for("purchases.purchase_entry"))

        except (ValueError, InvalidOperation, KeyError) as error:
            db.session.rollback()
            flash(f"Purchase failed: {error}", "error")

        except Exception as error:
            db.session.rollback()
            flash(f"Database error: {error}", "error")

    suppliers = db.session.execute(
        text("""
            SELECT id, supplier_name
            FROM suppliers
            ORDER BY supplier_name
        """)
    ).mappings().all()

    items = db.session.execute(
        text("""
            SELECT id, item_name, unit
            FROM inventory_items
            WHERE category = 'raw_material'
            ORDER BY item_name
        """)
    ).mappings().all()

    return render_template(
        "purchases.html",
        suppliers=suppliers,
        items=items
    )
