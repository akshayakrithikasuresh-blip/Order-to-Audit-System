
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, abort, send_file
)
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle
)

invoices = Blueprint("invoices", __name__)


# --------------------------------------------------
# CONFIGURATION
# Replace these placeholders with actual seller details
# --------------------------------------------------

SELLER_NAME = "Your Company Name"
SELLER_ADDRESS = "Your Business Address"
SELLER_GSTIN = "Seller GSTIN"


def money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def format_money(value):
    return f"{money(value):,.2f}"


# --------------------------------------------------
# INVOICE MANAGEMENT
# --------------------------------------------------

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
            GROUP BY so.id, so.order_number,
                     c.customer_name, c.state
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


# --------------------------------------------------
# CREATE GST INVOICE
# --------------------------------------------------

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
            raise ValueError(
                "Only approved orders can be invoiced."
            )

        existing = db.session.execute(
            text("""
                SELECT id FROM invoices
                WHERE sales_order_id = :order_id
            """),
            {"order_id": order_id}
        ).first()

        if existing:
            raise ValueError(
                "An invoice already exists for this order."
            )

        items = db.session.execute(
            text("""
                SELECT soi.product_id, soi.quantity,
                       soi.unit_price, p.gst_rate
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
            total_gst = money(
                taxable * gst_rate / Decimal("100")
            )

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
            taxable_total + cgst_total +
            sgst_total + igst_total
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
                    "intra_state" if intra_state
                    else "inter_state"
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


# --------------------------------------------------
# DOWNLOAD GST INVOICE AS PDF
# --------------------------------------------------

@invoices.route("/invoices/<int:invoice_id>/pdf")
@login_required
def download_invoice_pdf(invoice_id):

    if not (current_user.has_role("Admin") or
            current_user.has_role("Accountant")):
        abort(403)

    invoice = db.session.execute(
        text("""
            SELECT inv.*,
                   so.order_number,
                   c.customer_name,
                   c.contact_person,
                   c.phone,
                   c.address,
                   c.city,
                   c.state AS customer_state,
                   c.gstin AS customer_gstin
            FROM invoices inv
            JOIN sales_orders so
                ON inv.sales_order_id = so.id
            JOIN customers c
                ON so.customer_id = c.id
            WHERE inv.id = :invoice_id
        """),
        {"invoice_id": invoice_id}
    ).mappings().first()

    if not invoice:
        abort(404)

    invoice_items = db.session.execute(
        text("""
            SELECT ii.quantity,
                   ii.unit_price,
                   ii.taxable_amount,
                   ii.gst_rate,
                   ii.cgst_amount,
                   ii.sgst_amount,
                   ii.igst_amount,
                   p.product_name,
                   p.hsn_code
            FROM invoice_items ii
            JOIN products p ON ii.product_id = p.id
            WHERE ii.invoice_id = :invoice_id
        """),
        {"invoice_id": invoice_id}
    ).mappings().all()

    if not invoice_items:
        abort(404)

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        textColor=colors.HexColor("#243447"),
        spaceAfter=12
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#243447")
    )

    normal_style = styles["Normal"]

    story = []

    # Invoice heading
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Spacer(1, 8))

    # Seller details
    seller_data = [
        [
            Paragraph(
                f"<b>{SELLER_NAME}</b><br/>"
                f"{SELLER_ADDRESS}<br/>"
                f"GSTIN: {SELLER_GSTIN}",
                normal_style
            ),
            Paragraph(
                f"<b>Invoice Number:</b> "
                f"{invoice['invoice_number']}<br/>"
                f"<b>Invoice Date:</b> "
                f"{invoice['invoice_date']}<br/>"
                f"<b>Order Number:</b> "
                f"{invoice['order_number']}",
                normal_style
            )
        ]
    ]

    seller_table = Table(
        seller_data,
        colWidths=[85 * mm, 85 * mm]
    )

    seller_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 9)
    ]))

    story.append(seller_table)
    story.append(Spacer(1, 15))

    # Customer details
    story.append(
        Paragraph("BILL TO / CUSTOMER DETAILS", heading_style)
    )

    customer_address = ", ".join(
        str(value) for value in [
            invoice["address"],
            invoice["city"],
            invoice["customer_state"]
        ] if value
    )

    customer_data = [
        [
            Paragraph(
                f"<b>Customer:</b> "
                f"{invoice['customer_name']}",
                normal_style
            ),
            Paragraph(
                f"<b>GSTIN:</b> "
                f"{invoice['customer_gstin'] or 'Not provided'}",
                normal_style
            )
        ],
        [
            Paragraph(
                f"<b>Address:</b> "
                f"{customer_address or 'Not provided'}",
                normal_style
            ),
            Paragraph(
                f"<b>Phone:</b> "
                f"{invoice['phone'] or 'Not provided'}",
                normal_style
            )
        ],
        [
            Paragraph(
                f"<b>Place of Supply:</b> "
                f"{invoice['place_of_supply']}",
                normal_style
            ),
            Paragraph(
                f"<b>Supply Type:</b> "
                f"{invoice['supply_type'].replace('_', ' ').title()}",
                normal_style
            )
        ]
    ]

    customer_table = Table(
        customer_data,
        colWidths=[85 * mm, 85 * mm]
    )

    customer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8)
    ]))

    story.append(customer_table)
    story.append(Spacer(1, 15))

    # Product details
    story.append(
        Paragraph("ITEM DETAILS", heading_style)
    )

    table_data = [[
        "Product",
        "HSN",
        "Qty",
        "Rate",
        "Taxable",
        "GST %",
        "CGST",
        "SGST",
        "IGST"
    ]]

    for item in invoice_items:
        table_data.append([
            Paragraph(str(item["product_name"]), normal_style),
            str(item["hsn_code"] or "-"),
            str(item["quantity"]),
            format_money(item["unit_price"]),
            format_money(item["taxable_amount"]),
            str(item["gst_rate"]),
            format_money(item["cgst_amount"]),
            format_money(item["sgst_amount"]),
            format_money(item["igst_amount"])
        ])

    item_table = Table(
        table_data,
        colWidths=[
            32 * mm, 15 * mm, 10 * mm,
            17 * mm, 21 * mm, 13 * mm,
            19 * mm, 19 * mm, 19 * mm
        ],
        repeatRows=1
    )

    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0),
         colors.HexColor("#243447")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("PADDING", (0, 0), (-1, -1), 5)
    ]))

    story.append(item_table)
    story.append(Spacer(1, 15))

    # Invoice totals
    totals_data = [
        ["Taxable Amount", f"Rs. {format_money(invoice['taxable_amount'])}"],
        ["CGST", f"Rs. {format_money(invoice['cgst_amount'])}"],
        ["SGST", f"Rs. {format_money(invoice['sgst_amount'])}"],
        ["IGST", f"Rs. {format_money(invoice['igst_amount'])}"],
        ["TOTAL INVOICE VALUE",
         f"Rs. {format_money(invoice['total_amount'])}"]
    ]

    totals_table = Table(
        totals_data,
        colWidths=[55 * mm, 35 * mm],
        hAlign="RIGHT"
    )

    totals_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1),
         colors.HexColor("#e8eef4")),
        ("PADDING", (0, 0), (-1, -1), 7)
    ]))

    story.append(totals_table)
    story.append(Spacer(1, 25))

    story.append(
        Paragraph(
            "This is a computer-generated invoice.",
            ParagraphStyle(
                "Footer",
                parent=normal_style,
                alignment=TA_CENTER,
                fontSize=9
            )
        )
    )

    document.build(story)

    buffer.seek(0)

    filename = f"{invoice['invoice_number']}.pdf"

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )
