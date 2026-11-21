
from getpass import getpass
from app import app
from extensions import db
from models.user import User, Role
from werkzeug.security import generate_password_hash

with app.app_context():

    role = Role.query.filter_by(role_name="Admin").first()

    if not role:
        print("Admin role not found. Check your roles table.")

    else:
        existing_user = User.query.filter_by(
            username="admin"
        ).first()

        if existing_user:
            print("Admin account already exists.")

        else:
            password = getpass("Create admin password: ")

            if len(password) < 8:
                print("Password must contain at least 8 characters.")

            else:
                admin = User(
                    full_name="System Administrator",
                    username="admin",
                    password_hash=generate_password_hash(password),
                    role_id=role.id
                )

                db.session.add(admin)
                db.session.commit()

                print("Admin account created successfully!")
                print("Username: admin")
