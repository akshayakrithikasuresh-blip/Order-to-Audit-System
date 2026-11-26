
from flask import Flask, render_template, redirect, url_for
from flask_login import login_required, current_user
from routes.inventory import inventory
from routes.production import production
from routes.sales import sales
from routes.invoices import invoices
from routes.dispatch import dispatch
from routes.payments import payments
from routes.reports import reports
from config import Config
from extensions import db, login_manager
from models.user import User
from routes.auth import auth
from routes.purchases import purchases

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth)
    app.register_blueprint(purchases)
    app.register_blueprint(inventory)
    app.register_blueprint(production)
    app.register_blueprint(sales)
    app.register_blueprint(invoices)
    app.register_blueprint(dispatch)
    app.register_blueprint(payments)
    app.register_blueprint(reports)
    @app.route("/")
    def home():
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", user=current_user)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
