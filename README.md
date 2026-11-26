# Order-to-Audit System

A web-based Order-to-Audit Management System developed using Flask and MySQL for a small food manufacturing business. The application manages the business workflow from raw material purchases and production to sales orders, GST invoicing, dispatch, payments and management reporting.

## 1. Project Overview

Small food manufacturing businesses need to coordinate inventory, production, sales and financial records. Managing these activities separately can lead to stock discrepancies, inaccurate costing and difficulties tracking outstanding payments.

The Order-to-Audit System provides a centralized application to manage and monitor these operations with role-based access control and reporting.

## 2. Objectives

- Digitize the purchase and sales order process.
- Maintain raw material and finished goods stock.
- Calculate production consumption using Bills of Materials (BOM).
- Track planned versus actual production.
- Generate GST invoices.
- Record dispatches and customer payments.
- Monitor outstanding receivables.
- Provide business reports for management and auditing.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.13.9 | Backend programming |
| Flask 3.1.3 | Web application framework |
| MySQL | Relational database |
| Flask-SQLAlchemy | Database integration |
| Flask-Login | User authentication and session management |
| HTML and CSS | Frontend |
| Jinja2 | Dynamic HTML rendering |
| PyMySQL | MySQL connectivity |
| ReportLab | GST invoice PDF generation |
| Pandas and OpenPyXL | Data processing and spreadsheet support |
| Python-dotenv | Environment variable management |

### Why these technologies?

- **Flask:** Lightweight framework suitable for developing modular web applications.
- **MySQL:** Provides structured storage and relationships between business records.
- **SQLAlchemy:** Simplifies database interaction and transaction management.
- **Flask-Login:** Supports authenticated user sessions.
- **ReportLab:** Generates downloadable GST invoice PDFs.
- **HTML and CSS:** Provide browser-based interfaces.

## 4. Features and Requirement Mapping

### Must-have features

- User authentication and role-based access.
- Product, customer, supplier and inventory management.
- Purchase recording.
- Sales order creation by salesmen.
- Admin approval and rejection of sales orders.
- BOM-based production management.
- Raw material consumption and finished goods stock updates.
- GST invoice generation.
- Dispatch management.
- Stock summary and stock movement ledger.

### Should-have features

- Payment recording and invoice allocation.
- Customer-wise outstanding tracking.
- Receivables ageing reports.
- Production variance reporting.
- Production costing and cost per packet.
- Sales register and GST summary.
- Inventory and production reports.
- Management reporting dashboard.

### Nice-to-have features

Features beyond the implemented scope have not been claimed as completed. They can be added if required by the original project specification.

## 5. User Roles

The system uses a common login page with role-specific dashboards and permissions.

| Role | Responsibilities |
|---|---|
| Admin | Manage purchases, review sales orders, invoices, dispatches, payments and reports |
| Salesman | Create and track sales orders |
| Production Supervisor | Record production and monitor inventory |
| Accountant | Manage invoices, payments and financial reports |
| Owner | View management reports |

## 6. Business Workflow

1. The Admin records purchases of raw materials from suppliers.
2. Purchased quantities are added to inventory through stock movements.
3. The Salesman creates a customer sales order.
4. The Admin reviews and approves or rejects the order.
5. An approved order is converted into a GST invoice.
6. The Admin records dispatch, and finished goods stock is reduced.
7. Customer payments are recorded and allocated against invoices.
8. The Production Supervisor records production using the applicable BOM.
9. Raw materials are issued and finished goods are added to inventory.
10. Reports display sales, GST, stock, production variance, costing and outstanding receivables.

## 7. Database Overview

The application uses a MySQL database named `order_to_audit`.

Major database tables include:

- `users` and `roles` – User accounts and role assignments.
- `customers` and `suppliers` – Customer and supplier details.
- `products` – Product information.
- `inventory_items` – Raw materials, packaging and finished goods.
- `bom_headers` and `bom_items` – Bill of Materials definitions.
- `purchases` and `purchase_items` – Purchase transactions.
- `stock_movements` – Inventory movement records.
- `production_runs` and `production_consumptions` – Production and consumption records.
- `sales_orders` and `sales_order_items` – Sales transactions.
- `invoices` and `invoice_items` – GST invoice records.
- `dispatches` and `dispatch_items` – Dispatch records.
- `payments` and `payment_allocations` – Customer payment records.
- `audit_logs` – Audit-related activity records.

The database structure is provided in the `schema.sql` file in the repository.

## 8. Stock and BOM Calculation Method

### Stock calculation

Inventory is maintained using stock movements.

**Current Stock = Total Quantity In − Total Quantity Out**

Examples:

- Purchase: increases raw material stock.
- Production issue: decreases raw material stock.
- Production output: increases finished goods stock.
- Dispatch: decreases finished goods stock.

### BOM consumption

A Bill of Materials specifies the expected material quantities required to manufacture a defined production batch.

For a production run:

**Planned Material Quantity = BOM Quantity × Batch Size**

The system records actual consumption separately from planned consumption.

**Material Variance = Actual Consumption − Planned Consumption**

A positive variance indicates excess consumption, while a negative variance indicates lower consumption than planned.

### Finished goods output

The actual good production output is added to finished goods inventory.

Damaged or wasted output is recorded separately and is not counted as good finished stock.

## 9. Production Costing Method

Material costs are calculated using the recorded purchase costs available for the consumed inventory items.

The application uses the recorded average purchase cost for production consumption.

**Material Cost = Actual Material Quantity × Recorded Unit Cost**

**Total Production Cost = Material Cost + Labour Cost + Utility Cost**

**Cost per Packet = Total Production Cost ÷ Actual Good Output**

The costing report compares planned and actual production output, material consumption and production expenses.

## 10. GST Calculation

The application calculates GST according to the customer's state and the configured GST rate.

- Intra-state supply: CGST + SGST.
- Inter-state supply: IGST.

For the tested 5% GST rate:

- CGST = 2.5%.
- SGST = 2.5%.
- IGST = 5%.

The system generates a downloadable GST invoice PDF containing invoice, customer, product, tax and total details.

## 11. Benchmark and Testing Results

The following figures are from the application's recorded test data.

### Production benchmark

| Metric | Result |
|---|---:|
| Number of production runs | 2 |
| Planned output | 400 packets |
| Actual output | 376 packets |
| Output variance | -24 packets |
| Total recorded wastage | 12 |

The actual output was 24 packets below the planned output.

**Output variance = 376 − 400 = -24 packets**

### Invoice and receivables benchmark

| Metric | Result |
|---|---:|
| Taxable invoice value | ₹7,500 |
| CGST | ₹187.50 |
| SGST | ₹187.50 |
| Invoice total | ₹7,875 |
| Payment received | ₹4,000 |
| Outstanding amount | ₹3,875 |

**Outstanding = Invoice Total − Payment Received**

₹7,875 − ₹4,000 = ₹3,875.

### Stock benchmark

Stock balances are calculated from the opening quantities and subsequent purchase, production and dispatch movements. The stock report provides the recorded movement history for verification.

Differences between expected and recorded material balances should be interpreted using the stock ledger and actual production entries. The recorded test data is retained rather than artificially adjusted to match expected values.

## 12. Assumptions

- The application is designed for a small food manufacturing business.
- Each production run is associated with a product and its applicable BOM.
- BOM quantities represent planned consumption for the defined batch.
- Actual material consumption is recorded during production.
- Damaged output is not added to finished goods stock.
- GST rates are stored with product information.
- Customer state determines intra-state or inter-state tax treatment.
- Customer payments are allocated against invoices.
- Inventory balances are derived from stock movement records.
- User accounts are created and managed locally.

## 13. Known Gaps and Limitations

- The application is currently configured for local development and requires a production deployment setup before public hosting.
- Seller information in the invoice PDF must be replaced with the actual business name, address and GSTIN.
- Actual login passwords are configured locally and are not published in this repository.
- The application should be tested with the target business's actual data and business rules before operational use.
- The benchmark figures represent the recorded test dataset, not independently audited production results.

## 14. Installation and Setup

### Prerequisites

- Python 3.13.9
- MySQL Server
- MySQL Workbench (optional, for database management)
- Git

### Step 1: Clone the repository

```bash
git clone https://github.com/akshayakrithikasuresh-blip/Order-to-Audit-System.git
cd Order-to-Audit-System
```

### Step 2: Create a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 4: Configure environment variables

Create a `.env` file in the project root directory.

Add the following configuration with your own MySQL credentials:

```env
SECRET_KEY=your_secret_key
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=order_to_audit
```

Do not upload `.env` to GitHub.

### Step 5: Configure the database

The database structure is provided in `schema.sql`.

1. Open MySQL Workbench and connect to your MySQL server.
2. Create the database:

   ```sql
   CREATE DATABASE order_to_audit;
   ```

3. Navigate to **Server → Data Import**.
4. Select **Import from Self-Contained File**.
5. Browse and select the `schema.sql` file from the project folder.
6. Set the default target schema to `order_to_audit`.
7. Click **Start Import**.
8. Verify that the database tables have been created successfully.

Ensure that the MySQL server is running and that the configured database user has permission to access `order_to_audit`.

### Step 6: Create user accounts

Run:

```powershell
python create_salesman.py
```

The script creates the required role accounts when they do not already exist. Enter usernames, names and passwords when prompted.

### Step 7: Run the application

```powershell
python app.py
```

Open the application in a browser:

```text
http://127.0.0.1:5000/
```

Keep the terminal running while using the application.

## 15. Test Logins

The system supports five roles:

| Role | Test username |
|---|---|
| Admin | Use the configured Admin account |
| Salesman | `salesman1` |
| Production Supervisor | `prod_super` |
| Accountant | `accountant` |
| Owner | `owner` |

Passwords are configured locally and are intentionally not included in this public repository.

## 16. Repository

**GitHub:**  
https://github.com/akshayakrithikasuresh-blip/Order-to-Audit-System

The repository contains the application source code, database schema and development commit history.

---

**Project:** Order-to-Audit System  
**Framework:** Flask  
**Database:** MySQL  
**Language:** Python