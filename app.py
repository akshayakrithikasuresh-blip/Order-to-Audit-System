
from flask import Flask, render_template, redirect, url_for
from flask_login import login_required, current_user

from config import Config
from extensions import db, login_manager
from models.user import User
from routes.auth import auth


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth)

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
