"""Flask application factory for the WAF Assessment backend.

Serves the compiled React PWA at `/` and the assessment API under `/api`, backed
by Lakebase Postgres. Auth to Lakebase is a short-lived OAuth token minted fresh
per connection (see server.db); schema is managed with Flask-Migrate (Alembic).
"""

import os

from flask import Flask
from flask_migrate import Migrate

from server.db import database_url, db, register_token_injection

migrate = Migrate()

STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["STATIC_DIR"] = STATIC_DIR
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Recycle connections before the ~1h OAuth token expires (45 min).
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 2700,
        "pool_pre_ping": True,
    }

    db.init_app(app)
    # Import models so Alembic autogenerate and create_all see them.
    from server import models  # noqa: F401

    migrate.init_app(app, db)
    register_token_injection(app)

    from server.routes import api, site

    app.register_blueprint(api)
    app.register_blueprint(site)

    return app
