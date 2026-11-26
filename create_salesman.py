
from getpass import getpass
from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from models.user import User, Role


REQUIRED_ROLES = [
    "Salesman",
    "Production Supervisor",
    "Accountant",
    "Owner"
]


with app.app_context():

    print("\n===== USER ACCOUNT MANAGEMENT =====")

    for role_name in REQUIRED_ROLES:

        print(f"\n--- {role_name} ---")

        role = Role.query.filter_by(
            role_name=role_name
        ).first()

        if not role:
            print(f"{role_name} role not found. Skipping.")
            continue

        # Check whether an account already exists for this role
        existing_role_user = User.query.filter_by(
            role_id=role.id
        ).first()

        if existing_role_user:
            print(
                f"Account already exists for {role_name}: "
                f"{existing_role_user.username}"
            )
            continue

        username = input("Enter username: ").strip()

        if not username:
            print("Username cannot be empty. Skipping.")
            continue

        existing_username = User.query.filter_by(
            username=username
        ).first()

        if existing_username:
            print("Username already exists. Choose another.")
            continue

        full_name = input("Enter full name: ").strip()

        if not full_name:
            print("Full name cannot be empty. Skipping.")
            continue

        password = getpass("Enter password (minimum 8 characters): ")
        confirm_password = getpass("Confirm password: ")

        if len(password) < 8:
            print("Password must contain at least 8 characters.")
            continue

        if password != confirm_password:
            print("Passwords do not match. Skipping.")
            continue

        new_user = User(
            full_name=full_name,
            username=username,
            password_hash=generate_password_hash(password),
            role_id=role.id,
            is_active=True
        )

        try:
            db.session.add(new_user)
            db.session.commit()

            print(f"{role_name} account created successfully!")

        except Exception as error:
            db.session.rollback()
            print(f"Could not create {role_name} account: {error}")

    print("\n===== ACCOUNT MANAGEMENT COMPLETED =====")
