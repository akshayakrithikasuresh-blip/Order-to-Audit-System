# ORDER-TO-AUDIT SYSTEM
## System Design Note

### 1. System Architecture

The Order-to-Audit System is a web-based application developed using Python Flask and MySQL. Flask handles application logic, authentication, role-based access and business operations. MySQL stores transactional and master data. HTML, CSS and Jinja2 are used to render the user interface.

The application follows a modular structure:

- **Authentication:** User login and role-based access.
- **Purchases and Inventory:** Purchase recording and stock tracking.
- **Production:** BOM-based material consumption and finished goods updates.
- **Sales and Invoicing:** Sales order approval and GST invoice generation.
- **Dispatch and Payments:** Dispatch recording and payment allocation.
- **Reports:** Sales, GST, inventory, production costing and receivables reporting.

### 2. Database Design

The application uses a relational MySQL database named `order_to_audit`.

The main entities and their relationships are:

| Entity | Purpose |
|---|---|
| Users and Roles | Authentication and access permissions |
| Customers and Suppliers | Business partner information |
| Products | Manufactured product details |
| Inventory Items | Raw materials, packaging and finished goods |
| BOM Headers and BOM Items | Product-wise material requirements |
| Purchases and Purchase Items | Material procurement records |
| Stock Movements | Inventory inflow and outflow history |
| Production Runs and Consumptions | Production output and material usage |
| Sales Orders and Items | Customer orders |
| Invoices and Invoice Items | GST billing records |
| Dispatches and Items | Finished goods dispatch records |
| Payments and Allocations | Customer payment tracking |
| Audit Logs | Audit-related activity records |

**Important relationships:**

- One role can be assigned to multiple users.
- One product can have BOM definitions containing multiple inventory items.
- One purchase can contain multiple purchase items.
- One production run records its material consumption and finished output.
- One sales order belongs to a customer and contains multiple order items.
- An approved sales order is associated with an invoice.
- An invoice can have dispatch and payment allocation records.

### 3. Stock Management and BOM Consumption

Inventory is maintained through the `stock_movements` table. Every stock transaction records the inventory item, movement type, quantity in, quantity out and source reference.

**Stock calculation:**

Current Stock = Total Quantity In − Total Quantity Out

The main stock movements are:

- Purchase: increases raw material stock.
- Production Issue: decreases raw material stock.
- Production Output: increases finished goods stock.
- Dispatch: decreases finished goods stock.

**BOM calculation:**

A Bill of Materials defines the planned material quantities needed for a production batch.

Planned Material Quantity = BOM Quantity × Batch Size

The production module records both planned and actual material consumption.

Material Variance = Actual Consumption − Planned Consumption

A positive variance indicates excess material consumption. A negative variance indicates lower consumption than planned.

Actual good output is added to finished goods inventory. Damaged or wasted output is recorded separately and is excluded from good finished stock.

### 4. Production Costing Method

The application calculates production material costs using the recorded average purchase cost available for each consumed inventory item.

Material Cost = Actual Material Quantity × Recorded Unit Cost

Total Production Cost = Material Cost + Labour Cost + Utility Cost

Cost per Packet = Total Production Cost ÷ Actual Good Output

The production report compares planned and actual output, material consumption, wastage and production expenses.

This is the production costing approach implemented in the application; it should not be interpreted as a separate, fully implemented inventory valuation system.

### 5. GST and Financial Tracking

The invoice module determines the tax treatment using the customer's state and the configured GST rate.

- Intra-state transactions: CGST and SGST.
- Inter-state transactions: IGST.

For a 5% GST rate, intra-state transactions use 2.5% CGST and 2.5% SGST, while inter-state transactions use 5% IGST.

Customer payments are recorded and allocated against invoices. Outstanding receivables are calculated as:

Outstanding Amount = Invoice Total − Allocated Payments

The receivables report displays invoice-wise outstanding balances and ageing categories.

### 6. Design Summary

The system connects purchasing, inventory, production, sales, invoicing, dispatch and payment operations through a centralized relational database. Stock movement records provide transaction traceability, while production and financial reports support operational monitoring and audit review.

**Technology:** Python, Flask, MySQL, HTML, CSS, Jinja2  
**Database schema:** `schema.sql`  
**Project repository:** https://github.com/akshayakrithikasuresh-blip/Order-to-Audit-System