
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

production = Blueprint("production", __name__)


def check_production_access():
    if not (
        current_user.has_role("Admin")
        or current_user.has_role("Production Supervisor")
    ):
        abort(403)


# 1. Production Management Page
@production.route("/production")
@login_required
def production_entry():

    check_production_access()

    products = db.session.execute(
        text("""
            SELECT
                p.id,
                p.product_name,
                p.sku,
                p.pack_size_grams,
                b.id AS bom_id,
                b.batch_name,
                b.expected_yield_packets
            FROM products p
            JOIN bom_headers b ON p.id = b.product_id
            WHERE b.is_active = 1
            ORDER BY p.product_name
        """)
    ).mappings().all()

    components = db.session.execute(
        text("""
            SELECT
                bi.id AS bom_item_id,
                bi.bom_id,
                i.item_name,
                bi.inventory_item_id,
                bi.quantity_required,
                bi.unit
            FROM bom_items bi
            JOIN inventory_items i
                ON bi.inventory_item_id = i.id
            JOIN bom_headers b
                ON bi.bom_id = b.id
            WHERE b.is_active = 1
            ORDER BY bi.bom_id, i.item_name
        """)
    ).mappings().all()

    return render_template(
        "production.html",
        products=products,
        components=components,
        today=date.today().isoformat()
    )


# 2. Record Production
@production.route("/production/record", methods=["POST"])
@login_required
def record_production():

    check_production_access()

    try:
        product_id = int(request.form["product_id"])

        batch_size = Decimal(request.form["batch_size"])
        actual_output = int(request.form["actual_output"])
        wastage_quantity = int(request.form["wastage_quantity"])

        labour_cost = Decimal(request.form["labour_cost"])
        utility_cost = Decimal(request.form["utility_cost"])

        production_date = datetime.strptime(
            request.form["production_date"], "%Y-%m-%d"
        ).date()

        # Validate input values
        if not batch_size.is_finite() or batch_size <= 0:
            raise ValueError("Batch size must be positive.")

        if batch_size != batch_size.to_integral_value():
            raise ValueError("Batch size must be a whole number.")

        if actual_output <= 0 or wastage_quantity < 0:
            raise ValueError("Enter valid production and wastage quantities.")

        if (
            not labour_cost.is_finite()
            or not utility_cost.is_finite()
            or labour_cost < 0
            or utility_cost < 0
        ):
            raise ValueError("Enter valid production costs.")

        run_number = (
            f"PROD-{datetime.now():%Y%m%d}-"
            f"{uuid4().hex[:6].upper()}"
        )

        # Fetch product and active BOM
        product = db.session.execute(
            text("""
                SELECT
                    p.id,
                    p.product_name,
                    p.finished_inventory_item_id,
                    b.id AS bom_id,
                    b.expected_yield_packets
                FROM products p
                JOIN bom_headers b ON p.id = b.product_id
                WHERE p.id = :product_id
                  AND b.is_active = 1
            """),
            {"product_id": product_id}
        ).mappings().first()

        if not product:
            raise ValueError("Product or active BOM not found.")

        if not product.finished_inventory_item_id:
            raise ValueError("Finished goods inventory item is not configured.")

        expected_output = int(
            Decimal(str(product.expected_yield_packets)) * batch_size
        )

        if actual_output > expected_output:
            raise ValueError("Actual output cannot exceed planned output.")

        if actual_output + wastage_quantity > expected_output:
            raise ValueError(
                "Good output plus damaged pouches cannot exceed planned output."
            )

        # Fetch BOM ingredients
        bom_items = db.session.execute(
            text("""
                SELECT
                    bi.id AS bom_item_id,
                    bi.inventory_item_id,
                    bi.quantity_required,
                    bi.unit,
                    i.item_name
                FROM bom_items bi
                JOIN inventory_items i
                    ON bi.inventory_item_id = i.id
                WHERE bi.bom_id = :bom_id
            """),
            {"bom_id": product.bom_id}
        ).mappings().all()

        if not bom_items:
            raise ValueError("No ingredients found in this BOM.")

        consumption_data = []

        # Validate material consumption and stock
        for item in bom_items:

            actual_quantity = Decimal(
                request.form[f"actual_qty_{item.bom_item_id}"]
            )

            planned_quantity = (
                Decimal(str(item.quantity_required)) * batch_size
            )

            if not actual_quantity.is_finite() or actual_quantity < 0:
                raise ValueError(
                    f"Invalid consumption for {item.item_name}."
                )

            if actual_quantity > 0:

                # Lock inventory item during this transaction
                db.session.execute(
                    text("""
                        SELECT id
                        FROM inventory_items
                        WHERE id = :item_id
                        FOR UPDATE
                    """),
                    {"item_id": item.inventory_item_id}
                ).first()

                stock = db.session.execute(
                    text("""
                        SELECT
                            COALESCE(SUM(quantity_in), 0)
                            - COALESCE(SUM(quantity_out), 0)
                            AS current_stock
                        FROM stock_movements
                        WHERE inventory_item_id = :item_id
                    """),
                    {"item_id": item.inventory_item_id}
                ).scalar_one()

                if Decimal(str(stock)) < actual_quantity:
                    raise ValueError(
                        f"Insufficient stock for {item.item_name}. "
                        f"Available: {stock} {item.unit}, "
                        f"Required: {actual_quantity} {item.unit}."
                    )

            # Calculate average recorded purchase cost
            unit_cost = db.session.execute(
                text("""
                    SELECT
                        COALESCE(
                            SUM(pi.quantity * pi.unit_price)
                            / NULLIF(SUM(pi.quantity), 0),
                            0
                        )
                    FROM purchase_items pi
                    JOIN purchases p ON p.id = pi.purchase_id
                    WHERE pi.inventory_item_id = :item_id
                      AND p.status = 'received'
                """),
                {"item_id": item.inventory_item_id}
            ).scalar_one()

            consumption_data.append({
                "item": item,
                "planned": planned_quantity,
                "actual": actual_quantity,
                "unit_cost": Decimal(str(unit_cost))
            })

        # Create production run
        run_result = db.session.execute(
            text("""
                INSERT INTO production_runs
                (
                    run_number,
                    product_id,
                    bom_id,
                    batch_size,
                    expected_output,
                    actual_output,
                    wastage_quantity,
                    labour_cost,
                    utility_cost,
                    production_date,
                    status,
                    notes,
                    created_by
                )
                VALUES
                (
                    :run_number,
                    :product_id,
                    :bom_id,
                    :batch_size,
                    :expected_output,
                    :actual_output,
                    :wastage_quantity,
                    :labour_cost,
                    :utility_cost,
                    :production_date,
                    'completed',
                    :notes,
                    :created_by
                )
            """),
            {
                "run_number": run_number,
                "product_id": product_id,
                "bom_id": product.bom_id,
                "batch_size": batch_size,
                "expected_output": expected_output,
                "actual_output": actual_output,
                "wastage_quantity": wastage_quantity,
                "labour_cost": labour_cost,
                "utility_cost": utility_cost,
                "production_date": production_date,
                "notes": request.form.get("notes", ""),
                "created_by": current_user.id
            }
        )

        run_id = run_result.lastrowid

        # Record material consumption and deduct stock
        for data in consumption_data:

            item = data["item"]

            db.session.execute(
                text("""
                    INSERT INTO production_consumptions
                    (
                        production_run_id,
                        inventory_item_id,
                        planned_quantity,
                        actual_quantity,
                        unit,
                        unit_cost
                    )
                    VALUES
                    (
                        :run_id,
                        :item_id,
                        :planned,
                        :actual,
                        :unit,
                        :unit_cost
                    )
                """),
                {
                    "run_id": run_id,
                    "item_id": item.inventory_item_id,
                    "planned": data["planned"],
                    "actual": data["actual"],
                    "unit": item.unit,
                    "unit_cost": data["unit_cost"]
                }
            )

            if data["actual"] > 0:
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
                            'production_issue',
                            0,
                            :quantity,
                            :unit,
                            'production',
                            :run_id,
                            'Material consumed in production',
                            :user_id
                        )
                    """),
                    {
                        "item_id": item.inventory_item_id,
                        "quantity": data["actual"],
                        "unit": item.unit,
                        "run_id": run_id,
                        "user_id": current_user.id
                    }
                )

        # Add finished goods to inventory
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
                    'production_output',
                    :quantity,
                    0,
                    'packets',
                    'production',
                    :run_id,
                    'Finished goods produced',
                    :user_id
                )
            """),
            {
                "item_id": product.finished_inventory_item_id,
                "quantity": actual_output,
                "run_id": run_id,
                "user_id": current_user.id
            }
        )

        # Commit all production and inventory changes together
        db.session.commit()

        flash(
            f"Production run {run_number} recorded successfully!",
            "success"
        )

    except (ValueError, InvalidOperation, KeyError) as error:
        db.session.rollback()
        flash(f"Production failed: {error}", "error")

    except Exception as error:
        db.session.rollback()
        flash(f"Database error: {error}", "error")

    return redirect(url_for("production.production_entry"))
