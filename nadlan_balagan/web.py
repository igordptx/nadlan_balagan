"""Local-only results dashboard."""

import json
from pathlib import Path
import secrets

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from .config import DATA_DIR, PERIOD_LABELS, load_searches
from .service import Service


def create_app(service: Service) -> Flask:
    app = Flask(__name__)
    csrf_token = secrets.token_urlsafe(32)

    @app.get("/")
    def index():
        searches, errors = load_searches(service.search_dir)
        cards = []
        for search in searches.values():
            cards.append({
                "search": search,
                "period_label": PERIOD_LABELS[search.period],
                "latest": service.storage.latest(search.id),
                "success": service.storage.latest(search.id, "success"),
            })
        return render_template(
            "index.html", cards=cards, errors=errors, batches=service.storage.recent_batches(),
            status=service.status(), csrf_token=csrf_token,
        )

    @app.post("/run")
    def run():
        if not secrets.compare_digest(request.form.get("csrf_token", ""), csrf_token):
            abort(403)
        search_id = request.form.get("search_id") or None
        accepted, message = service.submit_manual(search_id)
        if not accepted:
            return render_template("message.html", message=message), 409
        return redirect(url_for("index"), code=303)

    @app.get("/search/<search_id>")
    def detail(search_id: str):
        searches, _ = load_searches(service.search_dir)
        search = searches.get(search_id)
        if not search:
            abort(404)
        success = service.storage.latest(search_id, "success")
        latest = service.storage.latest(search_id)
        columns = json.loads(success["columns_json"]) if success else []
        rows = json.loads(success["rows_json"]) if success else []
        return render_template("detail.html", search=search, latest=latest, success=success,
                               columns=columns, rows=rows, csrf_token=csrf_token)

    @app.get("/download/<search_id>")
    def download(search_id: str):
        success = service.storage.latest(search_id, "success")
        if not success or not success["csv_path"]:
            abort(404)
        path = Path(success["csv_path"]).resolve()
        if not path.is_relative_to(DATA_DIR.resolve()) or not path.is_file():
            abort(404)
        return send_file(path, mimetype="text/csv; charset=utf-8", as_attachment=True,
                         download_name=f"{search_id}-transactions.csv")

    @app.get("/health")
    def health():
        return jsonify({"ok": True, **service.status()})

    return app
