
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from decimal import Decimal, InvalidOperation
from datetime import date

payments = Blueprint("payments", __name__)


@payments.route("/payments", methods=["GET", "POST"])
@login_required
def payment_management():

    # Role-based access
    if not (
        current_user.has_role("Admin")
        or current_user.has_role("Accountant")
    ):
        abort(403)

    # -------------------------------------------------
    # POST: RECORD CUSTOMER PAYMENT
    # -------------------------------------------------

    if request.method == "POST":
        try:
            customer_id = int(request.form.get("customer_id"))
            invoice_id = int(request.form.get("invoice_id"))

            amount = Decimal(request.form.get("amount", "0"))
            payment_method = request.form.get("payment_method")

            payment_date = date.fromisoformat(
                request.form.get("payment_date")
            )

            reference_number = request.form.get(
                "reference_number", ""
            ).strip()

            notes = request.form.get("notes", "").strip()

            # Validate payment amount
            if not amount.is_finite() or amount <= 0:
                raise ValueError(
                    "Payment amount must be greater than zero."
                )

            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError(
                    "Payment amount can have at most two decimal places."
                )

            # Validate payment method
            if payment_method not in [
                "cash", "upi", "bank_transfer", "cheque", "other"
            ]:
                raise ValueError("Invalid payment method.")

            # Fetch invoice and lock its row
            invoice = db.session.execute(text("""
                SELECT
                    inv.id,
                    inv.total_amount,
                    inv.status,
                    so.customer_id,
                    inv.invoice_number
                FROM invoices inv
                JOIN sales_orders so
                    ON inv.sales_order_id = so.id
                WHERE inv.id = :invoice_id
                FOR UPDATE
            """), {
                "invoice_id": invoice_id
            }).mappings().first()

            if not invoice:
                raise ValueError("Invoice not found.")

            if invoice["status"] != "posted":
                raise ValueError(
                    "Only posted invoices can receive payments."
                )

            if invoice["customer_id"] != customer_id:
                raise ValueError(
                    "Selected invoice does not belong to this customer."
                )

            # Calculate existing allocations
            allocated = db.session.execute(text("""
                SELECT COALESCE(SUM(allocated_amount), 0)
                FROM payment_allocations
                WHERE invoice_id = :invoice_id
            """), {
                "invoice_id": invoice_id
            }).scalar()

            outstanding = (
                Decimal(str(invoice["total_amount"]))
                - Decimal(str(allocated))
            )

            if outstanding <= 0:
                raise ValueError(
                    "This invoice is already fully paid."
                )

            if amount > outstanding:
                raise ValueError(
                    f"Payment exceeds outstanding balance of "
                    f"₹{outstanding:.2f}."
                )

            # Insert payment record
            result = db.session.execute(text("""
                INSERT INTO payments (
                    customer_id,
                    payment_date,
                    amount,
                    payment_method,
                    reference_number,
                    notes,
                    recorded_by
                )
                VALUES (
                    :customer_id,
                    :payment_date,
                    :amount,
                    :payment_method,
                    :reference_number,
                    :notes,
                    :recorded_by
                )
            """), {
                "customer_id": customer_id,
                "payment_date": payment_date,
                "amount": amount,
                "payment_method": payment_method,
                "reference_number": reference_number or None,
                "notes": notes or None,
                "recorded_by": current_user.id
            })

            payment_id = result.lastrowid

            # Allocate payment to invoice
            db.session.execute(text("""
                INSERT INTO payment_allocations (
                    payment_id,
                    invoice_id,
                    allocated_amount
                )
                VALUES (
                    :payment_id,
                    :invoice_id,
                    :allocated_amount
                )
            """), {
                "payment_id": payment_id,
                "invoice_id": invoice_id,
                "allocated_amount": amount
            })

            db.session.commit()

            remaining = outstanding - amount

            flash(
                f"Payment of ₹{amount:.2f} recorded successfully! "
                f"Remaining invoice balance: ₹{remaining:.2f}.",
                "success"
            )

        except (ValueError, InvalidOperation, TypeError) as e:
            db.session.rollback()
            flash(str(e), "danger")

        except Exception as e:
            db.session.rollback()
            flash(
                f"Payment could not be recorded: {str(e)}",
                "danger"
            )

        return redirect(
            url_for("payments.payment_management")
        )

    # -------------------------------------------------
    # GET: FETCH CUSTOMER DETAILS
    # -------------------------------------------------

    customers = db.session.execute(text("""
        SELECT
            id,
            customer_name
        FROM customers
        ORDER BY customer_name
    """)).mappings().all()

    # -------------------------------------------------
    # FETCH OUTSTANDING INVOICES
    # -------------------------------------------------

    pending_invoices = db.session.execute(text("""
        SELECT
            inv.id AS invoice_id,
            inv.invoice_number,
            inv.invoice_date,
            inv.total_amount,
            c.id AS customer_id,
            c.customer_name,
            inv.total_amount - COALESCE(pa.paid_amount, 0)
                AS outstanding
        FROM invoices inv
        JOIN sales_orders so
            ON inv.sales_order_id = so.id
        JOIN customers c
            ON so.customer_id = c.id
        LEFT JOIN (
            SELECT
                invoice_id,
                SUM(allocated_amount) AS paid_amount
            FROM payment_allocations
            GROUP BY invoice_id
        ) pa ON inv.id = pa.invoice_id
        WHERE inv.status = 'posted'
          AND inv.total_amount > COALESCE(pa.paid_amount, 0)
        ORDER BY inv.invoice_date, inv.id
    """)).mappings().all()

    # -------------------------------------------------
    # PAYMENT HISTORY
    # -------------------------------------------------

    payment_history = db.session.execute(text("""
        SELECT
            p.id,
            p.payment_date,
            p.amount,
            p.payment_method,
            p.reference_number,
            c.customer_name,
            COALESCE(SUM(pa.allocated_amount), 0)
                AS allocated_amount
        FROM payments p
        JOIN customers c
            ON p.customer_id = c.id
        LEFT JOIN payment_allocations pa
            ON p.id = pa.payment_id
        GROUP BY
            p.id,
            p.payment_date,
            p.amount,
            p.payment_method,
            p.reference_number,
            c.customer_name
        ORDER BY p.payment_date DESC, p.id DESC
    """)).mappings().all()

    # -------------------------------------------------
    # CUSTOMER-WISE OUTSTANDING SUMMARY
    # -------------------------------------------------

    customer_outstanding = db.session.execute(text("""
        SELECT
            c.id AS customer_id,
            c.customer_name,
            COUNT(inv.id) AS pending_invoices,
            SUM(
                inv.total_amount - COALESCE(pa.paid_amount, 0)
            ) AS total_outstanding
        FROM customers c
        JOIN sales_orders so
            ON c.id = so.customer_id
        JOIN invoices inv
            ON so.id = inv.sales_order_id
        LEFT JOIN (
            SELECT
                invoice_id,
                SUM(allocated_amount) AS paid_amount
            FROM payment_allocations
            GROUP BY invoice_id
        ) pa ON inv.id = pa.invoice_id
        WHERE inv.status = 'posted'
          AND inv.total_amount > COALESCE(pa.paid_amount, 0)
        GROUP BY c.id, c.customer_name
        ORDER BY total_outstanding DESC
    """)).mappings().all()

    # -------------------------------------------------
    # INVOICE-WISE AGEING DETAILS
    # -------------------------------------------------

    ageing_invoices = db.session.execute(text("""
        SELECT
            inv.invoice_number,
            c.customer_name,
            inv.invoice_date,

            DATEDIFF(CURDATE(), inv.invoice_date)
                AS age_days,

            inv.total_amount - COALESCE(pa.paid_amount, 0)
                AS outstanding,

            CASE
                WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                    BETWEEN 0 AND 30
                    THEN '0-30 days'

                WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                    BETWEEN 31 AND 60
                    THEN '31-60 days'

                WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                    BETWEEN 61 AND 90
                    THEN '61-90 days'

                ELSE 'Above 90 days'
            END AS ageing_category

        FROM invoices inv

        JOIN sales_orders so
            ON inv.sales_order_id = so.id

        JOIN customers c
            ON so.customer_id = c.id

        LEFT JOIN (
            SELECT
                invoice_id,
                SUM(allocated_amount) AS paid_amount
            FROM payment_allocations
            GROUP BY invoice_id
        ) pa ON inv.id = pa.invoice_id

        WHERE inv.status = 'posted'
          AND inv.total_amount > COALESCE(pa.paid_amount, 0)

        ORDER BY age_days DESC
    """)).mappings().all()

    # -------------------------------------------------
    # OVERALL AGEING SUMMARY
    # -------------------------------------------------

    ageing_summary = db.session.execute(text("""
        SELECT

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                        BETWEEN 0 AND 30
                    THEN inv.total_amount - COALESCE(pa.paid_amount, 0)
                    ELSE 0
                END
            ), 0) AS days_0_30,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                        BETWEEN 31 AND 60
                    THEN inv.total_amount - COALESCE(pa.paid_amount, 0)
                    ELSE 0
                END
            ), 0) AS days_31_60,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURDATE(), inv.invoice_date)
                        BETWEEN 61 AND 90
                    THEN inv.total_amount - COALESCE(pa.paid_amount, 0)
                    ELSE 0
                END
            ), 0) AS days_61_90,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURDATE(), inv.invoice_date) > 90
                    THEN inv.total_amount - COALESCE(pa.paid_amount, 0)
                    ELSE 0
                END
            ), 0) AS above_90_days

        FROM invoices inv

        LEFT JOIN (
            SELECT
                invoice_id,
                SUM(allocated_amount) AS paid_amount
            FROM payment_allocations
            GROUP BY invoice_id
        ) pa ON inv.id = pa.invoice_id

        WHERE inv.status = 'posted'
          AND inv.total_amount > COALESCE(pa.paid_amount, 0)

    """)).mappings().first()

    # -------------------------------------------------
    # RENDER PAYMENT MANAGEMENT PAGE
    # -------------------------------------------------

    return render_template(
        "payments.html",
        customers=customers,
        pending_invoices=pending_invoices,
        payment_history=payment_history,
        customer_outstanding=customer_outstanding,
        ageing_invoices=ageing_invoices,
        ageing_summary=ageing_summary,
        today=date.today().isoformat()
    )
