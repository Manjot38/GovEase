"""GovEase - Flask application entry point.

Run:
    python -m backend.app
    -> http://localhost:5000

Serves the API under /api and the frontend/ directory as static files, so a
single process runs the whole prototype.

FOR MEMBER 1 AND MEMBER 3
-------------------------
Add your module without touching any news code:

    from backend.routes.assistant import assistant_bp     # Member 1
    app.register_blueprint(assistant_bp, url_prefix="/api")

    from backend.routes.documents import documents_bp     # Member 3
    app.register_blueprint(documents_bp, url_prefix="/api")

Keep your endpoints under your own path (/api/assistant/..., /api/documents/...)
so the three modules never collide. CORS is already open for local development,
so your own dev server on another port can call this API directly.
"""

import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend.database.db import init_db
from backend.routes.news import news_bp
from news.collector import start_background_refresh

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)


def create_app():
    app = Flask(__name__, static_folder=None)
    CORS(app)

    init_db()

    app.register_blueprint(news_bp, url_prefix="/api")
    # Member 1: register assistant_bp here.
    # Member 3: register documents_bp here.

    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:filename>")
    def frontend_files(filename):
        return send_from_directory(FRONTEND_DIR, filename)

    # The frontend's offline fallback lives outside frontend/, so expose just
    # that one file rather than the whole news package.
    @app.route("/news/data/seed_news.json")
    def seed_file():
        return send_from_directory(
            os.path.join(os.path.dirname(FRONTEND_DIR), "news", "data"),
            "seed_news.json",
        )

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "not_found"}), 404

    return app


app = create_app()

if __name__ == "__main__":
    # Optional and OFF unless GOVEASE_BACKGROUND_REFRESH=1 is set.
    if start_background_refresh():
        print("[app] background refresh enabled")
    else:
        print("[app] background refresh off (set GOVEASE_BACKGROUND_REFRESH=1 to enable)")

    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=debug)
