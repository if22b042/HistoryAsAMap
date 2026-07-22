import os

from flask import Flask
from flask_cors import CORS

from backend.config import Config, INSTANCE_DIR
from backend.extensions import db
from backend.routes.admin import admin_bp
from backend.routes.events import events_bp


def create_app(config_class=Config) -> Flask:
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    app.register_blueprint(events_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, port=5000)
