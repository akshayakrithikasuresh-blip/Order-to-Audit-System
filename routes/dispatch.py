
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import date
from uuid import uuid4
from decimal import Decimal

dispatch = Blueprint("dispatch", __name__)


# 1. Dispatch Management Page
@dispatch.route("/dispatch")
@login_required
def dispatch_management():

    if not current_user.has_role("Admin"):
        abort(403)

    pending_dispatches = db.session.execute(
        text("""
            SELECT
                inv.id AS invoice_id,
                inv.invoice_number,
                inv.total_amount,
                c.customer_name,
                so.order_number,
                SUM(ii.quantity) AS total_quantity
            FROM invoices inv
            JOIN sales_orders so ON inv.sales_order_id = so.id
            JOIN customers c ON so.customer_id = c.id
            JOIN invoice_items ii ON inv.id = ii.invoice_id
            WHERE inv.status = 'posted'
              AND so.status = 'invoiced'
              AND NOT EXISTS (
                  SELECT 1
                  FROM dispatches d
                  WHERE d.invoice_id = inv.id
              )
            GROUP BY
                inv.id, inv.invoice_number, inv.total_amount,
                c.customer_name, so.order_number
            ORDER BY inv.id
        """)
    ).mappings().all()

    dispatch_records = db.session.execute(
        text("""
            SELECT
                d.dispatch_number,
                d.dispatch_date,
                inv.invoice_number,
                c.customer_name,
                SUM(di.quantity) AS total_quantity
            FROM dispatches d
            JOIN invoices inv ON d.invoice_id = inv.id
            JOIN sales_orders so ON inv.sales_order_id = so.id
            JOIN customers c ON so.customer_id = c.id
            JOIN dispatch_items di ON d.id = di.dispatch_id
            GROUP BY
                d.id, d.dispatch_number, d.dispatch_date,
                inv.invoice_number, c.customer_name
            ORDER BY d.id DESC
        """)
    ).mappings().all()

    return render_template(
        "dispatch.html",
        pending_dispatches=pending_dispatches,
        dispatch_records=dispatch_records
    )


# 2. Record Dispatch and Deduct Finished Goods Stock
@dispatch.route("/dispatch/create/<int:invoice_id>", methods=["POST"])
@login_required
def create_dispatch(invoice_id):

    if not current_user.has_role("Admin"):
        abort(403)

    try:
        invoice = db.session.execute(
            text("""
                SELECT inv.id, inv.invoice_number, inv.status,
                       so.id AS order_id, so.status AS order_status
                FROM invoices inv
                JOIN sales_orders so
                    ON inv.sales_order_id = so.id
                WHERE inv.id = :invoice_id
                FOR UPDATE
            """),
            {"invoice_id": invoice_id}
        ).mappings().first()

        if not invoice or invoice["status"] != "posted":
            raise ValueError("A valid posted invoice is required.")

        if invoice["order_status"] != "invoiced":
            raise ValueError("This order is not ready for dispatch.")

        existing = db.session.execute(
            text("""
                SELECT id FROM dispatches
                WHERE invoice_id = :invoice_id
            """),
            {"invoice_id": invoice_id}
        ).first()

        if existing:
            raise ValueError("This invoice has already been dispatched.")

        items = db.session.execute(
            text("""
                SELECT
                    ii.product_id,
                    ii.quantity,
                    p.product_name,
                    p.finished_inventory_item_id,
                    inv_item.unit
                FROM invoice_items ii
                JOIN products p ON ii.product_id = p.id
                JOIN inventory_items inv_item
                    ON p.finished_inventory_item_id = inv_item.id
                WHERE ii.invoice_id = :invoice_id
            """),
            {"invoice_id": invoice_id}
        ).mappings().all()

        if not items:
            raise ValueError("No invoice items found.")

        # Check stock availability for every item first.
        for item in items:

            stock_item = db.session.execute(
                text("""
                    SELECT id
                    FROM inventory_items
                    WHERE id = :item_id
                    FOR UPDATE
                """),
                {"item_id": item["finished_inventory_item_id"]}
            ).first()

            if not stock_item:
                raise ValueError(
                    f"Finished goods inventory is missing for {item['product_name']}."
                )

            stock = db.session.execute(
                text("""
                    SELECT
                        COALESCE(SUM(quantity_in), 0)
                        - COALESCE(SUM(quantity_out), 0) AS current_stock
                    FROM stock_movements
                    WHERE inventory_item_id = :item_id
                """),
                {"item_id": item["finished_inventory_item_id"]}
            ).scalar()

            if Decimal(str(stock or 0)) < Decimal(str(item["quantity"])):
                raise ValueError(
                    f"Insufficient stock for {item['product_name']}. "
                    f"Available: {stock}, Required: {item['quantity']}"
                )

        dispatch_number = (
            "DSP-" + date.today().strftime("%Y%m%d")
            + "-" + uuid4().hex[:6].upper()
        )

        result = db.session.execute(
            text("""
                INSERT INTO dispatches
                (dispatch_number, invoice_id, dispatch_date,
                 dispatched_by, notes)
                VALUES
                (:dispatch_number, :invoice_id, :dispatch_date,
                 :dispatched_by, :notes)
            """),
            {
                "dispatch_number": dispatch_number,
                "invoice_id": invoice_id,
                "dispatch_date": date.today(),
                "dispatched_by": current_user.id,
                "notes": "Dispatch completed against GST invoice."
            }
        )

        dispatch_id = result.lastrowid

        for item in items:

            quantity = item["quantity"]
            inventory_item_id = item["finished_inventory_item_id"]

            db.session.execute(
                text("""
                    INSERT INTO dispatch_items
                    (dispatch_id, product_id, quantity)
                    VALUES
                    (:dispatch_id, :product_id, :quantity)
                """),
                {
                    "dispatch_id": dispatch_id,
                    "product_id": item["product_id"],
                    "quantity": quantity
                }
            )

            db.session.execute(
                text("""
                    INSERT INTO stock_movements
                    (inventory_item_id, movement_date, movement_type,
                     quantity_in, quantity_out, unit, source_type,
                     source_id, notes, created_by)
                    VALUES
                    (:item_id, NOW(), 'dispatch',
                     0, :quantity, :unit, 'dispatch',
                     :source_id, :notes, :created_by)
                """),
                {
                    "item_id": inventory_item_id,
                    "quantity": quantity,
                    "unit": item["unit"],
                    "source_id": dispatch_id,
                    "notes": f"Dispatch {dispatch_number}",
                    "created_by": current_user.id
                }
            )

        db.session.execute(
            text("""
                UPDATE sales_orders
                SET status = 'dispatched'
                WHERE id = :order_id
            """),
            {"order_id": invoice["order_id"]}
        )

        db.session.commit()

        flash(
            f"Dispatch {dispatch_number} recorded successfully!",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("dispatch.dispatch_management"))
