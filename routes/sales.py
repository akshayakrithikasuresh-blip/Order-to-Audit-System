
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

sales = Blueprint("sales", __name__)


# 1. Sales Order Entry
@sales.route("/sales", methods=["GET", "POST"])
@login_required
def sales_entry():

    if request.method == "POST":

        if not current_user.has_role("Salesman"):
            abort(403)

        try:
            customer_id = int(request.form.get("customer_id"))
            product_id = int(request.form.get("product_id"))
            quantity = int(request.form.get("quantity"))

            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")

            customer = db.session.execute(
                text("""
                    SELECT id
                    FROM customers
                    WHERE id = :customer_id
                """),
                {"customer_id": customer_id}
            ).first()

            product = db.session.execute(
                text("""
                    SELECT id, selling_price
                    FROM products
                    WHERE id = :product_id
                """),
                {"product_id": product_id}
            ).mappings().first()

            if not customer or not product:
                raise ValueError("Invalid customer or product.")

            order_number = "SO-" + datetime.now().strftime("%Y%m%d") + "-" + uuid4().hex[:6].upper()

            result = db.session.execute(
                text("""
                    INSERT INTO sales_orders
                    (order_number, customer_id, salesman_id,
                     order_date, status, notes)
                    VALUES
                    (:order_number, :customer_id, :salesman_id,
                     NOW(), 'submitted', :notes)
                """),
                {
                    "order_number": order_number,
                    "customer_id": customer_id,
                    "salesman_id": current_user.id,
                    "notes": request.form.get("notes", "")
                }
            )

            order_id = result.lastrowid

            db.session.execute(
                text("""
                    INSERT INTO sales_order_items
                    (sales_order_id, product_id, quantity, unit_price)
                    VALUES
                    (:order_id, :product_id, :quantity, :unit_price)
                """),
                {
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": product["selling_price"]
                }
            )

            db.session.commit()

            flash(f"Sales order {order_number} submitted successfully!", "success")

        except (ValueError, InvalidOperation) as e:
            db.session.rollback()
            flash(str(e), "danger")

        except Exception:
            db.session.rollback()
            flash("Unable to create sales order. Please check the details.", "danger")

        return redirect(url_for("sales.sales_entry"))

    customers = db.session.execute(
        text("""
            SELECT id, customer_name, city, state
            FROM customers
            ORDER BY customer_name
        """)
    ).mappings().all()

    products = db.session.execute(
        text("""
            SELECT id, product_name, selling_price
            FROM products
            ORDER BY product_name
        """)
    ).mappings().all()

    orders = db.session.execute(
        text("""
            SELECT so.id, so.order_number, c.customer_name,
                   so.order_date, so.status,
                   soi.quantity, p.product_name
            FROM sales_orders so
            JOIN customers c ON so.customer_id = c.id
            JOIN sales_order_items soi ON so.id = soi.sales_order_id
            JOIN products p ON soi.product_id = p.id
            WHERE so.salesman_id = :user_id
            ORDER BY so.id DESC
        """),
        {"user_id": current_user.id}
    ).mappings().all()

    return render_template(
        "sales.html",
        customers=customers,
        products=products,
        orders=orders
    )


# 2. Admin Order Review
@sales.route("/sales/admin")
@login_required
def admin_sales():

    if not current_user.has_role("Admin"):
        abort(403)

    orders = db.session.execute(
        text("""
            SELECT so.id, so.order_number, c.customer_name,
                   c.city, c.state, u.full_name,
                   so.order_date, so.status,
                   p.product_name, soi.quantity, soi.unit_price
            FROM sales_orders so
            JOIN customers c ON so.customer_id = c.id
            JOIN users u ON so.salesman_id = u.id
            JOIN sales_order_items soi ON so.id = soi.sales_order_id
            JOIN products p ON soi.product_id = p.id
            ORDER BY so.id DESC
        """)
    ).mappings().all()

    return render_template("admin_sales.html", orders=orders)


# 3. Approve or Reject Order
@sales.route("/sales/review/<int:order_id>/<action>", methods=["POST"])
@login_required
def review_sales(order_id, action):

    if not current_user.has_role("Admin"):
        abort(403)

    if action not in ["approve", "reject"]:
        abort(400)

    try:
        order = db.session.execute(
            text("""
                SELECT id, status
                FROM sales_orders
                WHERE id = :order_id
                FOR UPDATE
            """),
            {"order_id": order_id}
        ).mappings().first()

        if not order or order["status"] != "submitted":
            raise ValueError("This order cannot be reviewed.")

        new_status = "approved" if action == "approve" else "rejected"

        db.session.execute(
            text("""
                UPDATE sales_orders
                SET status = :status,
                    approved_by = :admin_id,
                    approved_at = NOW()
                WHERE id = :order_id
            """),
            {
                "status": new_status,
                "admin_id": current_user.id,
                "order_id": order_id
            }
        )

        db.session.commit()
        flash(f"Order {new_status} successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("sales.admin_sales"))
