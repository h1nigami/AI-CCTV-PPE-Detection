import os
import cv2

if not hasattr(cv2, 'INTER_NEAREST_EXACT'):
    cv2.INTER_NEAREST_EXACT = cv2.INTER_NEAREST

from flask import Flask, send_file, send_from_directory, render_template
from backend.main import (
    generate_live_feed, start_live, stop_live, state,
    annotated_buffers, model, camera_captures,
)
from backend.api.detection import configure_detection_routes
from backend.api.cameras import configure_camera_routes
from backend.api.reid import configure_reid_routes
from backend.config import CAMERAS

app = Flask(__name__, static_folder=None, template_folder=str(
    os.path.join(os.path.dirname(__file__), "..", "templates")
))

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    return render_template("index.html")


app = configure_detection_routes(app, state, annotated_buffers,
                                  generate_live_feed, start_live, stop_live, model)
app = configure_camera_routes(app, state, camera_captures)
app = configure_reid_routes(app, state)

if __name__ == "__main__":
    from waitress import serve
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Запуск на http://127.0.0.1:{port}")
    serve(app, host='0.0.0.0', port=port)
