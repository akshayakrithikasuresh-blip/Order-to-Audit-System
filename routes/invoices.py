
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

invoices = Blueprint("invoices", __name__)


def money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


@invoices.route("/invoices")
@login_required
def invoice_management():

    if not (current_user.has_role("Admin") or
            current_user.has_role("Accountant")):
        abort(403)

    approved_orders = db.session.execute(
        text("""
            SELECT so.id, so.order_number, c.customer_name,
                   c.state, SUM(soi.quantity) AS total_quantity
            FROM sales_orders so
            JOIN customers c ON so.customer_id = c.id
            JOIN sales_order_items soi ON so.id = soi.sales_order_id
            WHERE so.status = 'approved'
              AND NOT EXISTS (
                  SELECT 1 FROM invoices inv
                  WHERE inv.sales_order_id = so.id
              )
            GROUP BY so.id, so.order_number, c.customer_name, c.state
            ORDER BY so.id
        """)
    ).mappings().all()

    invoice_records = db.session.execute(
        text("""
            SELECT inv.id, inv.invoice_number, inv.invoice_date,
                   inv.place_of_supply, inv.taxable_amount,
                   inv.total_amount, inv.status, c.customer_name
            FROM invoices inv
            JOIN sales_orders so ON inv.sales_order_id = so.id
            JOIN customers c ON so.customer_id = c.id
            ORDER BY inv.id DESC
        """)
    ).mappings().all()

    return render_template(
        "invoices.html",
        approved_orders=approved_orders,
        invoice_records=invoice_records
    )


@invoices.route("/invoices/create/<int:order_id>", methods=["POST"])
@login_required
def create_invoice(order_id):

    if not (current_user.has_role("Admin") or
            current_user.has_role("Accountant")):
        abort(403)

    try:
        order = db.session.execute(
            text("""
                SELECT so.id, so.order_number, so.status,
                       c.customer_name, c.state
                FROM sales_orders so
                JOIN customers c ON so.customer_id = c.id
                WHERE so.id = :order_id
                FOR UPDATE
            """),
            {"order_id": order_id}
        ).mappings().first()

        if not order or order["status"] != "approved":
            raise ValueError("Only approved orders can be invoiced.")

        existing = db.session.execute(
            text("""
                SELECT id FROM invoices
                WHERE sales_order_id = :order_id
            """),
            {"order_id": order_id}
        ).first()

        if existing:
            raise ValueError("An invoice already exists for this order.")

        items = db.session.execute(
            text("""
                SELECT soi.product_id, soi.quantity, soi.unit_price,
                       p.gst_rate
                FROM sales_order_items soi
                JOIN products p ON soi.product_id = p.id
                WHERE soi.sales_order_id = :order_id
            """),
            {"order_id": order_id}
        ).mappings().all()

        if not items:
            raise ValueError("The order has no items.")

        intra_state = order["state"].strip().lower() in [
            "tamil nadu", "tamilnadu"
        ]

        taxable_total = Decimal("0.00")
        cgst_total = Decimal("0.00")
        sgst_total = Decimal("0.00")
        igst_total = Decimal("0.00")

        calculated_items = []

        for item in items:
            taxable = money(
                Decimal(item["quantity"]) *
                Decimal(str(item["unit_price"]))
            )

            gst_rate = Decimal(str(item["gst_rate"]))
            total_gst = money(taxable * gst_rate / Decimal("100"))

            if intra_state:
                cgst = money(total_gst / Decimal("2"))
                sgst = total_gst - cgst
                igst = Decimal("0.00")
            else:
                cgst = Decimal("0.00")
                sgst = Decimal("0.00")
                igst = total_gst

            taxable_total += taxable
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst

            calculated_items.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "taxable": taxable,
                "gst_rate": gst_rate,
                "cgst": cgst,
                "sgst": sgst,
                "igst": igst
            })

        taxable_total = money(taxable_total)
        cgst_total = money(cgst_total)
        sgst_total = money(sgst_total)
        igst_total = money(igst_total)

        total_amount = money(
            taxable_total + cgst_total + sgst_total + igst_total
        )

        invoice_number = (
            "INV-" + date.today().strftime("%Y%m%d") +
            "-" + uuid4().hex[:6].upper()
        )

        result = db.session.execute(
            text("""
                INSERT INTO invoices
                (invoice_number, sales_order_id, invoice_date,
                 place_of_supply, supply_type, taxable_amount,
                 cgst_amount, sgst_amount, igst_amount,
                 total_amount, status, created_by)
                VALUES
                (:invoice_number, :order_id, :invoice_date,
                 :place_of_supply, :supply_type, :taxable,
                 :cgst, :sgst, :igst, :total,
                 'posted', :created_by)
            """),
            {
                "invoice_number": invoice_number,
                "order_id": order_id,
                "invoice_date": date.today(),
                "place_of_supply": order["state"],
                "supply_type": (
                    "intra_state" if intra_state else "inter_state"
                ),
                "taxable": taxable_total,
                "cgst": cgst_total,
                "sgst": sgst_total,
                "igst": igst_total,
                "total": total_amount,
                "created_by": current_user.id
            }
        )

        invoice_id = result.lastrowid

        for item in calculated_items:
            db.session.execute(
                text("""
                    INSERT INTO invoice_items
                    (invoice_id, product_id, quantity, unit_price,
                     taxable_amount, gst_rate, cgst_amount,
                     sgst_amount, igst_amount)
                    VALUES
                    (:invoice_id, :product_id, :quantity, :unit_price,
                     :taxable, :gst_rate, :cgst, :sgst, :igst)
                """),
                {
                    "invoice_id": invoice_id,
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "taxable": item["taxable"],
                    "gst_rate": item["gst_rate"],
                    "cgst": item["cgst"],
                    "sgst": item["sgst"],
                    "igst": item["igst"]
                }
            )

        db.session.execute(
            text("""
                UPDATE sales_orders
                SET status = 'invoiced'
                WHERE id = :order_id
            """),
            {"order_id": order_id}
        )

        db.session.commit()

        flash(
            f"Invoice {invoice_number} generated successfully!",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("invoices.invoice_management"))
