# Order-to-Audit System -- Run Instructions

This guide explains how to set up and run the Flask application on
another **Windows** computer.

## 1. Prerequisites

Install the following:

-   Python 3.10 or later
-   MySQL Server 8.0 or later
-   Git

## 2. Clone the GitHub repository

Open PowerShell and run:

``` powershell
git clone https://github.com/akshayakrithikasuresh-blip/Order-to-Audit-System.git
cd Order-to-Audit-System
```

## 3. Create and activate a virtual environment

``` powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this in the same PowerShell window,
then activate again:

``` powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 4. Install Python dependencies

``` powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Create the MySQL database

1.  Start MySQL Server.
2.  Open MySQL Workbench and connect to the local MySQL server.
3.  Create a database:

``` sql
CREATE DATABASE order_to_audit_demo;
```

4.  Open the repository's `schema.sql` file in MySQL Workbench and
    execute it against `order_to_audit_demo`.

**Important:** `schema.sql` is a structure-only export. It creates the
database tables but does not necessarily populate the master records,
demo transactions, or test user accounts. Those records and accounts
must be created or imported separately before reviewers can log in and
explore a populated demo.

## 6. Configure the environment variables

Create a file named `.env` in the project root (the same folder as
`app.py`).

Add the following, replacing the example values with the local MySQL
credentials:

``` env
SECRET_KEY=replace-with-a-long-random-secret
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=order_to_audit_demo
DB_USER=root
DB_PASSWORD=your_mysql_password
```

Do not commit `.env` to a public GitHub repository. Keep real passwords
and secret keys private. Ensure `.env` is listed in `.gitignore`.

## 7. Run the application

From the project folder, with the virtual environment activated:

``` powershell
python app.py
```

When Flask starts successfully, open this address in a browser on the
same computer:

``` text
http://127.0.0.1:5000/
```

Keep the PowerShell window open while using the application. Press
`Ctrl + C` in that window to stop the server.

## 8. Test accounts

The application has role support for these accounts:

  Role                    Username
  ----------------------- --------------
  Admin                   `admin`
  Salesman                `salesman1`
  Production Supervisor   `prod_super`
  Accountant              `accountant`
  Owner                   `owner`

The passwords are not included in this document. Use only dedicated demo
credentials supplied separately by the project owner after the demo
accounts have been created or seeded. Do not publish real account
passwords or password hashes in this public repository.

## Troubleshooting

-   **MySQL connection error:** Check that MySQL Server is running and
    that `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`
    in `.env` are correct.
-   **Missing Python package:** Activate the virtual environment and run
    `pip install -r requirements.txt` again.
-   **PowerShell script execution blocked:** Run the
    `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` command
    shown in Step 3.
-   **Login page opens but accounts do not work:** The schema alone does
    not create user accounts or populate demo data. Confirm that the
    required demo users and master records have been added to the
    database.

## Notes for reviewers

`http://127.0.0.1:5000/` is a local address. It works on the computer
running the application; it is not a public live link. To access the
application remotely, the project must be deployed to a hosting service.
