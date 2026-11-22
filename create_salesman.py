
from getpass import getpass
from werkzeug.security import generate_password_hash
from app import app
from extensions import db
from models.user import User, Role

with app.app_context():

    role = Role.query.filter_by(role_name="Salesman").first()

    if not role:
        print("Salesman role not found in database.")
    else:
        username = input("Enter Salesman username: ").strip()

        if User.query.filter_by(username=username).first():
            print("Username already exists.")
        else:
            full_name = input("Enter Salesman full name: ").strip()
            password = getpass("Enter Salesman password: ")

            if not full_name or not password:
                print("Name and password cannot be empty.")
            else:
                salesman = User(
                    full_name=full_name,
                    username=username,
                    password_hash=generate_password_hash(password),
                    role_id=role.id,
                    is_active=True
                )

                db.session.add(salesman)
                db.session.commit()

                print("Salesman account created successfully!")
