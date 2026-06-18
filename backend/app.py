import os
import cv2

if not hasattr(cv2, 'INTER_NEAREST_EXACT'):
    cv2.INTER_NEAREST_EXACT = cv2.INTER_NEAREST

from flask import Flask, send_file, send_from_directory, render_template
from backend.main import (
    generate_live_feed, start_live, stop_live, state,
    annotated_buffers, model, camera_captures,
    start_face_workers, stop_face_workers,
)
from backend.api.detection import configure_detection_routes
from backend.api.cameras import configure_camera_routes
from backend.api.reid import configure_reid_routes
from backend.api.events import events_bp
from backend.api.monitoring import monitoring_bp
from backend.api.recordings import recordings_bp
from backend.config import CAMERAS
from backend.db.engine import init_db
from backend.auth.routes import auth_bp
from backend.auth.service import init_admin, set_jwt_secret

app = Flask(__name__, static_folder=None, template_folder=str(
    os.path.join(os.path.dirname(__file__), "..", "templates")
))

init_db()

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if JWT_SECRET:
    set_jwt_secret(JWT_SECRET)

init_admin(
    username=os.environ.get("ADMIN_USERNAME", "admin"),
    password=os.environ.get("ADMIN_PASSWORD", "admin123"),
    email=os.environ.get("ADMIN_EMAIL", None),
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    return render_template("index.html")


app.register_blueprint(auth_bp)
app = configure_detection_routes(app, state, annotated_buffers,
                                  generate_live_feed, start_live, stop_live, model,
                                  start_face_workers=start_face_workers,
                                  stop_face_workers=stop_face_workers)
app = configure_camera_routes(app, state, camera_captures)
app = configure_reid_routes(app, state)
app.register_blueprint(events_bp)
app.register_blueprint(monitoring_bp)
app.register_blueprint(recordings_bp)

# Автообнаружение камер при старте (опционально, в фоне — не блокирует запуск).
from backend.config import CAMERA_AUTODISCOVER
if CAMERA_AUTODISCOVER:
    import threading
    from backend.main import autodiscover_and_add
    threading.Thread(target=autodiscover_and_add, daemon=True).start()

if __name__ == "__main__":
    from waitress import serve
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Запуск на http://127.0.0.1:{port}")
    serve(app, host='0.0.0.0', port=port)
