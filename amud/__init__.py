"""Amud: local quotes and tax invoices with mixed Hebrew-English PDFs."""

import os
from pathlib import Path

from flask import Flask

from .db import close_db, default_db_path, init_db
from .web import bp, register_template_helpers


def create_app(db_path=None):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    path = Path(db_path or os.environ.get("AMUD_DATABASE") or default_db_path())
    app.config["DATABASE"] = str(path)
    app.config["SECRET_KEY"] = os.environ.get("AMUD_SECRET", "amud-local-dev-key")
    app.config["JSON_AS_ASCII"] = False
    init_db(path)
    register_template_helpers(app)
    app.register_blueprint(bp)
    app.teardown_appcontext(close_db)
    return app
