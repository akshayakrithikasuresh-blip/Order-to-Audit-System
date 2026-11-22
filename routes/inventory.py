
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import text
from extensions import db

inventory = Blueprint("inventory", __name__)


@inventory.route("/inventory")
@login_required
def inventory_summary():

    stock_items = db.session.execute(
        text("""
            SELECT
                i.id,
                i.item_code,
                i.item_name,
                i.category,
                i.unit,
                i.reorder_level,
                COALESCE(SUM(sm.quantity_in), 0)
                - COALESCE(SUM(sm.quantity_out), 0) AS current_stock
            FROM inventory_items i
            LEFT JOIN stock_movements sm
                ON i.id = sm.inventory_item_id
            GROUP BY
                i.id,
                i.item_code,
                i.item_name,
                i.category,
                i.unit,
                i.reorder_level
            ORDER BY i.id
        """)
    ).mappings().all()

    movements = db.session.execute(
        text("""
            SELECT
                sm.id,
                i.item_name,
                sm.movement_date,
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
            ORDER BY sm.movement_date DESC, sm.id DESC
        """)
    ).mappings().all()

    return render_template(
        "inventory.html",
        stock_items=stock_items,
        movements=movements
    )
