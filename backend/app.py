"""GovEase - Flask application entry point.

Run:
    python -m backend.app
    -> http://localhost:5000

Serves the API under /api and the frontend/ directory as static files, so a
single process runs the whole prototype.

The chatbot and news modules are registered under /api, and the document
tool under /api/documents. CORS is enabled for
local development, so the frontend can also call this API from another port.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend.database.db import init_db
from backend.routes.chat import chat_bp
from backend.routes.documents import MAX_REQUEST_MB, documents_bp
from backend.routes.news import news_bp
from news.collector import start_background_refresh

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)


def create_app():
    app = Flask(__name__, static_folder=None)
    CORS(app, expose_headers=["X-GovEase-Meta", "X-GovEase-Warnings", "Content-Disposition"])
    # Uploads for the document tool; the blueprint rejects anything larger
    # with a JSON error before the body is read.
    app.config["MAX_CONTENT_LENGTH"] = (MAX_REQUEST_MB + 1) * 1024 * 1024

    init_db()

    app.register_blueprint(news_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(documents_bp, url_prefix="/api/documents")

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

    @app.errorhandler(413)
    def too_large(error):
        return jsonify({
            "error": "request_too_large",
            "message": "Upload at most %d MB at once." % MAX_REQUEST_MB,
        }), 413

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
