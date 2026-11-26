
from flask import Blueprint, render_template, abort, request
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import date

reports = Blueprint("reports", __name__)


# =====================================================
# ROLE-BASED ACCESS
# =====================================================

def reports_access():
    if not (
        current_user.has_role("Admin")
        or current_user.has_role("Accountant")
        or current_user.has_role("Owner")
    ):
        abort(403)


# =====================================================
# STEP 10.1 - BUSINESS REPORTS DASHBOARD
# =====================================================

@reports.route("/reports")
@login_required
def reports_dashboard():

    reports_access()

    # 1. Sales and GST summary
    sales_summary = db.session.execute(text("""
        SELECT
            COUNT(*) AS invoice_count,
            COALESCE(SUM(taxable_amount), 0) AS taxable_amount,
            COALESCE(SUM(cgst_amount), 0) AS cgst_amount,
            COALESCE(SUM(sgst_amount), 0) AS sgst_amount,
            COALESCE(SUM(igst_amount), 0) AS igst_amount,
            COALESCE(SUM(total_amount), 0) AS total_sales
        FROM invoices
        WHERE status = 'posted'
    """)).mappings().first()

    # 2. Inventory summary
    inventory_summary = db.session.execute(text("""
        SELECT
            COUNT(*) AS total_items,
            COALESCE(SUM(
                CASE
                    WHEN current_stock <= reorder_level
                    THEN 1 ELSE 0
                END
            ), 0) AS low_stock_count
        FROM (
            SELECT
                i.id,
                i.reorder_level,
                COALESCE(
                    SUM(sm.quantity_in) - SUM(sm.quantity_out), 0
                ) AS current_stock
            FROM inventory_items i
            LEFT JOIN stock_movements sm
                ON i.id = sm.inventory_item_id
            WHERE i.is_active = 1
            GROUP BY i.id, i.reorder_level
        ) AS stock_data
    """)).mappings().first()

    # 3. Production summary
    production_summary = db.session.execute(text("""
        SELECT
            COUNT(*) AS total_runs,
            COALESCE(SUM(expected_output), 0) AS planned_output,
            COALESCE(SUM(actual_output), 0) AS actual_output,
            COALESCE(SUM(wastage_quantity), 0) AS total_wastage
        FROM production_runs
        WHERE status = 'completed'
    """)).mappings().first()

    # 4. Outstanding receivables
    outstanding_summary = db.session.execute(text("""
        SELECT
            COALESCE(
                SUM(
                    inv.total_amount - COALESCE(pay.total_paid, 0)
                ), 0
            ) AS outstanding_amount
        FROM invoices inv
        LEFT JOIN (
            SELECT
                invoice_id,
                SUM(allocated_amount) AS total_paid
            FROM payment_allocations
            GROUP BY invoice_id
        ) pay ON inv.id = pay.invoice_id
        WHERE inv.status = 'posted'
    """)).mappings().first()

    # 5. Low stock items
    low_stock_items = db.session.execute(text("""
        SELECT
            i.item_name,
            i.item_code,
            i.category,
            i.unit,
            i.reorder_level,
            COALESCE(
                SUM(sm.quantity_in) - SUM(sm.quantity_out), 0
            ) AS current_stock
        FROM inventory_items i
        LEFT JOIN stock_movements sm
            ON i.id = sm.inventory_item_id
        WHERE i.is_active = 1
        GROUP BY
            i.id,
            i.item_name,
            i.item_code,
            i.category,
            i.unit,
            i.reorder_level
        HAVING current_stock <= i.reorder_level
        ORDER BY current_stock ASC
    """)).mappings().all()

    # 6. Recent invoices
    recent_invoices = db.session.execute(text("""
        SELECT
            inv.invoice_number,
            inv.invoice_date,
            c.customer_name,
            inv.total_amount
        FROM invoices inv
        JOIN sales_orders so
            ON inv.sales_order_id = so.id
        JOIN customers c
            ON so.customer_id = c.id
        WHERE inv.status = 'posted'
        ORDER BY inv.invoice_date DESC, inv.id DESC
        LIMIT 5
    """)).mappings().all()

    return render_template(
        "reports.html",
        sales_summary=sales_summary,
        inventory_summary=inventory_summary,
        production_summary=production_summary,
        outstanding_summary=outstanding_summary,
        low_stock_items=low_stock_items,
        recent_invoices=recent_invoices
    )


# =====================================================
# STEP 10.2 - DETAILED SALES REGISTER AND GST REPORT
# =====================================================

@reports.route("/reports/sales")
@login_required
def sales_register():

    reports_access()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    conditions = ["inv.status = 'posted'"]
    params = {}

    # Date validation and filtering
    try:
        parsed_start = None
        parsed_end = None

        if start_date:
            parsed_start = date.fromisoformat(start_date)

            conditions.append(
                "inv.invoice_date >= :start_date"
            )

            params["start_date"] = parsed_start

        if end_date:
            parsed_end = date.fromisoformat(end_date)

            conditions.append(
                "inv.invoice_date <= :end_date"
            )

            params["end_date"] = parsed_end

        if (
            parsed_start
            and parsed_end
            and parsed_start > parsed_end
        ):
            abort(
                400,
                description="Start date cannot be after end date."
            )

    except ValueError:
        abort(
            400,
            description="Invalid date format. Please select valid dates."
        )

    where_clause = " AND ".join(conditions)

    # 1. DETAILED SALES REGISTER
    sales_rows = db.session.execute(text(f"""
        SELECT
            inv.invoice_number,
            inv.invoice_date,
            c.customer_name,
            c.gstin,
            c.state AS customer_state,
            inv.place_of_supply,
            inv.supply_type,
            inv.taxable_amount,
            inv.cgst_amount,
            inv.sgst_amount,
            inv.igst_amount,
            inv.total_amount
        FROM invoices inv
        JOIN sales_orders so
            ON inv.sales_order_id = so.id
        JOIN customers c
            ON so.customer_id = c.id
        WHERE {where_clause}
        ORDER BY inv.invoice_date DESC, inv.id DESC
    """), params).mappings().all()

    # 2. SALES AND GST TOTALS
    totals = db.session.execute(text(f"""
        SELECT
            COUNT(*) AS invoice_count,

            COALESCE(
                SUM(inv.taxable_amount), 0
            ) AS taxable_total,

            COALESCE(
                SUM(inv.cgst_amount), 0
            ) AS cgst_total,

            COALESCE(
                SUM(inv.sgst_amount), 0
            ) AS sgst_total,

            COALESCE(
                SUM(inv.igst_amount), 0
            ) AS igst_total,

            COALESCE(
                SUM(inv.total_amount), 0
            ) AS grand_total,

            COALESCE(
                SUM(
                    CASE
                        WHEN inv.supply_type = 'intra_state'
                        THEN inv.total_amount
                        ELSE 0
                    END
                ), 0
            ) AS intra_state_sales,

            COALESCE(
                SUM(
                    CASE
                        WHEN inv.supply_type = 'inter_state'
                        THEN inv.total_amount
                        ELSE 0
                    END
                ), 0
            ) AS inter_state_sales

        FROM invoices inv
        JOIN sales_orders so
            ON inv.sales_order_id = so.id
        JOIN customers c
            ON so.customer_id = c.id
        WHERE {where_clause}
    """), params).mappings().first()

    return render_template(
        "sales_register.html",
        sales_rows=sales_rows,
        totals=totals,
        start_date=start_date,
        end_date=end_date
    )


# =====================================================
# STEP 10.3 - STOCK SUMMARY AND STOCK LEDGER REPORT
# =====================================================

@reports.route("/reports/stock")
@login_required
def stock_report():

    reports_access()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    item_id = request.args.get("item_id", "").strip()
    movement_type = request.args.get("movement_type", "").strip()

    conditions = []
    params = {}

    # Validate inventory item
    if item_id:
        try:
            item_id = int(item_id)

            if item_id <= 0:
                raise ValueError

            params["item_id"] = item_id
            conditions.append("sm.inventory_item_id = :item_id")

        except ValueError:
            abort(400, description="Invalid inventory item.")

    # Validate movement type
    allowed_movement_types = [
        "opening",
        "purchase",
        "production_issue",
        "production_output",
        "dispatch",
        "return",
        "adjustment"
    ]

    if movement_type:
        if movement_type not in allowed_movement_types:
            abort(400, description="Invalid movement type.")

        conditions.append("sm.movement_type = :movement_type")
        params["movement_type"] = movement_type

    # Validate date filters
    try:
        parsed_start = None
        parsed_end = None

        if start_date:
            parsed_start = date.fromisoformat(start_date)
            conditions.append("sm.movement_date >= :start_date")
            params["start_date"] = parsed_start

        if end_date:
            parsed_end = date.fromisoformat(end_date)
            conditions.append(
                "sm.movement_date < DATE_ADD(:end_date, INTERVAL 1 DAY)"
            )
            params["end_date"] = parsed_end

        if (
            parsed_start
            and parsed_end
            and parsed_start > parsed_end
        ):
            abort(400, description="Start date cannot be after end date.")

    except ValueError:
        abort(400, description="Invalid date format.")

    # Current stock item filter
    item_condition = ""

    if item_id:
        item_condition = "AND i.id = :item_id"

    # 1. CURRENT STOCK SUMMARY
    stock_summary = db.session.execute(text("""
        SELECT
            i.id,
            i.item_name,
            i.item_code,
            i.category,
            i.unit,
            i.reorder_level,
            COALESCE(SUM(sm.quantity_in), 0) AS total_received,
            COALESCE(SUM(sm.quantity_out), 0) AS total_issued,
            COALESCE(
                SUM(sm.quantity_in) - SUM(sm.quantity_out), 0
            ) AS current_stock
        FROM inventory_items i
        LEFT JOIN stock_movements sm
            ON i.id = sm.inventory_item_id
        WHERE i.is_active = 1
        """ + item_condition + """
        GROUP BY
            i.id,
            i.item_name,
            i.item_code,
            i.category,
            i.unit,
            i.reorder_level
        ORDER BY i.category, i.item_name
    """), params).mappings().all()

    # 2. STOCK MOVEMENT LEDGER
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    ledger_rows = db.session.execute(text(f"""
        SELECT
            sm.id,
            sm.movement_date,
            i.item_name,
            i.item_code,
            i.category,
            sm.movement_type,
            sm.quantity_in,
            sm.quantity_out,
            sm.unit,
            sm.source_type,
            sm.source_id,
            sm.notes
        FROM stock_movements sm
        JOIN inventory_items i
            ON sm.inventory_item_id = i.id
        WHERE {where_clause}
        ORDER BY sm.movement_date DESC, sm.id DESC
        LIMIT 1000
    """), params).mappings().all()

    # 3. MOVEMENT TOTALS
    movement_totals = db.session.execute(text(f"""
        SELECT
            COUNT(*) AS movement_count,
            COALESCE(SUM(sm.quantity_in), 0) AS total_in,
            COALESCE(SUM(sm.quantity_out), 0) AS total_out
        FROM stock_movements sm
        JOIN inventory_items i
            ON sm.inventory_item_id = i.id
        WHERE {where_clause}
    """), params).mappings().first()

    # 4. INVENTORY ITEMS FOR DROPDOWN
    inventory_items = db.session.execute(text("""
        SELECT id, item_name, item_code
        FROM inventory_items
        WHERE is_active = 1
        ORDER BY item_name
    """)).mappings().all()

    return render_template(
        "stock_report.html",
        stock_summary=stock_summary,
        ledger_rows=ledger_rows,
        movement_totals=movement_totals,
        inventory_items=inventory_items,
        selected_item=str(item_id) if item_id else "",
        selected_movement=movement_type,
        start_date=start_date,
        end_date=end_date
    )


# =====================================================
# STEP 10.4 - PRODUCTION VARIANCE AND COSTING REPORT
# =====================================================

@reports.route("/reports/production")
@login_required
def production_variance_report():

    reports_access()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    conditions = ["pr.status = 'completed'"]
    params = {}

    # Date validation
    try:
        parsed_start = None
        parsed_end = None

        if start_date:
            parsed_start = date.fromisoformat(start_date)
            conditions.append("pr.production_date >= :start_date")
            params["start_date"] = parsed_start

        if end_date:
            parsed_end = date.fromisoformat(end_date)
            conditions.append("pr.production_date <= :end_date")
            params["end_date"] = parsed_end

        if parsed_start and parsed_end and parsed_start > parsed_end:
            abort(400, description="Start date cannot be after end date.")

    except ValueError:
        abort(400, description="Invalid date format.")

    where_clause = " AND ".join(conditions)

    # Material cost calculated separately for each production run
    material_cost_query = """
        SELECT
            production_run_id,
            SUM(actual_quantity * unit_cost) AS material_cost
        FROM production_consumptions
        GROUP BY production_run_id
    """

    # 1. PRODUCTION SUMMARY
    production_summary = db.session.execute(text(f"""
        SELECT
            COUNT(*) AS total_runs,
            COALESCE(SUM(pr.expected_output), 0) AS planned_output,
            COALESCE(SUM(pr.actual_output), 0) AS actual_output,
            COALESCE(SUM(pr.wastage_quantity), 0) AS total_wastage,
            COALESCE(SUM(mc.material_cost), 0) AS material_cost,
            COALESCE(SUM(pr.labour_cost), 0) AS labour_cost,
            COALESCE(SUM(pr.utility_cost), 0) AS utility_cost,
            COALESCE(
                SUM(mc.material_cost)
                + SUM(pr.labour_cost)
                + SUM(pr.utility_cost), 0
            ) AS total_production_cost
        FROM production_runs pr
        LEFT JOIN ({material_cost_query}) mc
            ON pr.id = mc.production_run_id
        WHERE {where_clause}
    """), params).mappings().first()

    # 2. INDIVIDUAL PRODUCTION RUNS AND COST PER PACKET
    production_rows = db.session.execute(text(f"""
        SELECT
            pr.id,
            pr.run_number,
            pr.production_date,
            p.product_name,
            pr.batch_size,
            pr.expected_output,
            pr.actual_output,
            pr.wastage_quantity,

            COALESCE(mc.material_cost, 0) AS material_cost,
            COALESCE(pr.labour_cost, 0) AS labour_cost,
            COALESCE(pr.utility_cost, 0) AS utility_cost,

            (
                COALESCE(mc.material_cost, 0)
                + COALESCE(pr.labour_cost, 0)
                + COALESCE(pr.utility_cost, 0)
            ) AS total_cost,

            CASE
                WHEN pr.actual_output > 0 THEN
                    (
                        COALESCE(mc.material_cost, 0)
                        + COALESCE(pr.labour_cost, 0)
                        + COALESCE(pr.utility_cost, 0)
                    ) / pr.actual_output
                ELSE 0
            END AS cost_per_packet,

            CASE
                WHEN pr.expected_output > 0 THEN
                    (pr.actual_output / pr.expected_output) * 100
                ELSE 0
            END AS yield_percentage,

            (pr.actual_output - pr.expected_output)
                AS output_variance

        FROM production_runs pr
        JOIN products p ON pr.product_id = p.id

        LEFT JOIN ({material_cost_query}) mc
            ON pr.id = mc.production_run_id

        WHERE {where_clause}
        ORDER BY pr.production_date DESC, pr.id DESC
    """), params).mappings().all()

    # 3. RAW MATERIAL CONSUMPTION VARIANCE
    consumption_rows = db.session.execute(text(f"""
        SELECT
            pr.run_number,
            pr.production_date,
            p.product_name,
            i.item_name,
            pc.planned_quantity,
            pc.actual_quantity,

            (pc.actual_quantity - pc.planned_quantity)
                AS quantity_variance,

            pc.unit,
            pc.unit_cost,

            (pc.actual_quantity * pc.unit_cost)
                AS actual_material_cost

        FROM production_consumptions pc

        JOIN production_runs pr
            ON pc.production_run_id = pr.id

        JOIN products p
            ON pr.product_id = p.id

        JOIN inventory_items i
            ON pc.inventory_item_id = i.id

        WHERE {where_clause}
        ORDER BY pr.production_date DESC, pr.id DESC, i.item_name
    """), params).mappings().all()

    # 4. OVERALL OUTPUT VARIANCE
    output_variance = db.session.execute(text(f"""
        SELECT
            COALESCE(SUM(pr.expected_output), 0) AS planned_output,
            COALESCE(SUM(pr.actual_output), 0) AS actual_output,

            COALESCE(
                SUM(pr.actual_output - pr.expected_output), 0
            ) AS output_variance,

            COALESCE(SUM(pr.wastage_quantity), 0) AS total_wastage

        FROM production_runs pr
        WHERE {where_clause}
    """), params).mappings().first()

    return render_template(
        "production_variance.html",
        production_summary=production_summary,
        production_rows=production_rows,
        consumption_rows=consumption_rows,
        output_variance=output_variance,
        start_date=start_date,
        end_date=end_date
    )


# =====================================================
# STEP 10.5 - OUTSTANDING AND RECEIVABLES REPORT
# =====================================================

@reports.route("/reports/receivables")
@login_required
def receivables_report():

    reports_access()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    conditions = ["inv.status = 'posted'"]
    params = {}

    # Date validation
    try:
        parsed_start = None
        parsed_end = None

        if start_date:
            parsed_start = date.fromisoformat(start_date)
            conditions.append("inv.invoice_date >= :start_date")
            params["start_date"] = parsed_start

        if end_date:
            parsed_end = date.fromisoformat(end_date)
            conditions.append("inv.invoice_date <= :end_date")
            params["end_date"] = parsed_end

        if parsed_start and parsed_end and parsed_start > parsed_end:
            abort(400, description="Start date cannot be after end date.")

    except ValueError:
        abort(400, description="Invalid date format.")

    where_clause = " AND ".join(conditions)

    # Payment totals per invoice
    payment_query = """
        SELECT
            invoice_id,
            SUM(allocated_amount) AS total_paid
        FROM payment_allocations
        GROUP BY invoice_id
    """

    # 1. OVERALL RECEIVABLES SUMMARY
    receivables_summary = db.session.execute(text(f"""
        SELECT
            COUNT(*) AS total_invoices,

            COALESCE(SUM(inv.total_amount), 0)
                AS total_invoiced,

            COALESCE(SUM(pay.total_paid), 0)
                AS total_collected,

            COALESCE(
                SUM(
                    inv.total_amount - COALESCE(pay.total_paid, 0)
                ), 0
            ) AS total_outstanding

        FROM invoices inv

        LEFT JOIN ({payment_query}) pay
            ON inv.id = pay.invoice_id

        WHERE {where_clause}
    """), params).mappings().first()

    # 2. INVOICE-WISE OUTSTANDING AND AGEING
    invoice_rows = db.session.execute(text(f"""
        SELECT
            inv.id,
            inv.invoice_number,
            inv.invoice_date,
            c.customer_name,
            c.phone,
            c.state,

            inv.total_amount,

            COALESCE(pay.total_paid, 0) AS total_paid,

            (
                inv.total_amount - COALESCE(pay.total_paid, 0)
            ) AS outstanding_amount,

            DATEDIFF(CURRENT_DATE, inv.invoice_date) AS age_days,

            CASE
                WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date) <= 30
                    THEN '0-30 days'
                WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date) <= 60
                    THEN '31-60 days'
                WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date) <= 90
                    THEN '61-90 days'
                ELSE 'Over 90 days'
            END AS ageing_bucket

        FROM invoices inv

        JOIN sales_orders so
            ON inv.sales_order_id = so.id

        JOIN customers c
            ON so.customer_id = c.id

        LEFT JOIN ({payment_query}) pay
            ON inv.id = pay.invoice_id

        WHERE {where_clause}

        HAVING outstanding_amount > 0.005

        ORDER BY inv.invoice_date ASC, inv.id ASC
    """), params).mappings().all()

    # 3. CUSTOMER-WISE OUTSTANDING
    customer_rows = db.session.execute(text(f"""
        SELECT
            c.id AS customer_id,
            c.customer_name,
            c.customer_type,
            c.phone,

            COUNT(inv.id) AS invoice_count,

            COALESCE(SUM(inv.total_amount), 0)
                AS total_invoiced,

            COALESCE(SUM(pay.total_paid), 0)
                AS total_paid,

            COALESCE(
                SUM(
                    inv.total_amount - COALESCE(pay.total_paid, 0)
                ), 0
            ) AS outstanding_amount

        FROM invoices inv

        JOIN sales_orders so
            ON inv.sales_order_id = so.id

        JOIN customers c
            ON so.customer_id = c.id

        LEFT JOIN ({payment_query}) pay
            ON inv.id = pay.invoice_id

        WHERE {where_clause}

        GROUP BY
            c.id,
            c.customer_name,
            c.customer_type,
            c.phone

        HAVING outstanding_amount > 0.005

        ORDER BY outstanding_amount DESC
    """), params).mappings().all()

    # 4. AGEING SUMMARY
    ageing_summary = db.session.execute(text(f"""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date) <= 30
                    THEN inv.total_amount - COALESCE(pay.total_paid, 0)
                    ELSE 0
                END
            ), 0) AS days_0_30,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date)
                        BETWEEN 31 AND 60
                    THEN inv.total_amount - COALESCE(pay.total_paid, 0)
                    ELSE 0
                END
            ), 0) AS days_31_60,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date)
                        BETWEEN 61 AND 90
                    THEN inv.total_amount - COALESCE(pay.total_paid, 0)
                    ELSE 0
                END
            ), 0) AS days_61_90,

            COALESCE(SUM(
                CASE
                    WHEN DATEDIFF(CURRENT_DATE, inv.invoice_date) > 90
                    THEN inv.total_amount - COALESCE(pay.total_paid, 0)
                    ELSE 0
                END
            ), 0) AS over_90_days

        FROM invoices inv

        LEFT JOIN ({payment_query}) pay
            ON inv.id = pay.invoice_id

        WHERE {where_clause}
    """), params).mappings().first()

    return render_template(
        "receivables_report.html",
        receivables_summary=receivables_summary,
        invoice_rows=invoice_rows,
        customer_rows=customer_rows,
        ageing_summary=ageing_summary,
        start_date=start_date,
        end_date=end_date
    )
