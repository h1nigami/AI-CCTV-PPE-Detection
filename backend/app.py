import os
import cv2

if not hasattr(cv2, 'INTER_NEAREST_EXACT'):
    cv2.INTER_NEAREST_EXACT = cv2.INTER_NEAREST

from flask import Flask, send_file, send_from_directory
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
from backend.tts.router import tts_bp
from backend.config import CAMERAS
from backend.db.engine import init_db
from backend.auth.routes import auth_bp
from backend.auth.service import init_admin, set_jwt_secret

app = Flask(__name__, static_folder=None)

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
FRONTEND_INDEX = os.path.join(FRONTEND_DIR, "index.html")

if not os.path.exists(FRONTEND_INDEX):
    # В Docker фронтенд собирается ВНУТРИ образа (Stage 1 Dockerfile/Dockerfile.gpu,
    # npm ci && npm run build) — при отсутствии здесь это либо запуск вне Docker
    # (голый python app.py на хосте без npm run build), либо образ собран без
    # `--build` до появления фронтенда. Чинится `docker compose ... up --build`
    # (Docker сам поставит зависимости и соберёт React — npm на хосте не нужен),
    # либо для запуска вне Docker — `cd frontend && npm install && npm run build`.
    print(
        f"[WARN] Не найден собранный frontend: {FRONTEND_INDEX}\n"
        f"       В Docker: docker compose --profile <cpu|gpu> up --build\n"
        f"       Вне Docker: cd frontend && npm install && npm run build\n"
        f"       До сборки на '/' будет отдаваться диагностическая страница вместо дашборда."
    )


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response


_FRONTEND_MISSING_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Frontend не собран</title>
<style>
  body{background:#080d14;color:#c8dff0;font-family:monospace;display:flex;
       align-items:center;justify-content:center;min-height:100vh;margin:0}
  .box{max-width:640px;padding:32px;border:1px solid #ff3355;border-radius:8px;
       background:#ff335511}
  h1{color:#ff3355;font-size:1.2rem;margin:0 0 12px}
  code{background:#111c2b;padding:2px 6px;border-radius:4px;color:#00e5ff}
  pre{background:#111c2b;padding:12px;border-radius:6px;overflow-x:auto}
</style></head><body>
  <div class="box">
    <h1>⚠ Frontend не собран</h1>
    <p>Бэкенд не нашёл собранный React-фронтенд (<code>frontend/dist/index.html</code>).</p>
    <p>В Docker — пересоберите образ (фронтенд собирается внутри него):</p>
    <pre>docker compose --profile gpu up --build -d</pre>
    <p>Вне Docker (локальный запуск python app.py):</p>
    <pre>cd frontend
npm install
npm run build</pre>
    <p>Подробнее — раздел «Локальный запуск» / «Docker» в CLAUDE.md.</p>
  </div>
</body></html>"""


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    if os.path.exists(FRONTEND_INDEX):
        return send_file(FRONTEND_INDEX)
    return _FRONTEND_MISSING_HTML, 503


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
app.register_blueprint(tts_bp)

# Автообнаружение камер при старте (опционально, в фоне — не блокирует запуск).
from backend.config import CAMERA_AUTODISCOVER, TTS_ENABLED
if CAMERA_AUTODISCOVER:
    import threading
    from backend.main import autodiscover_and_add
    threading.Thread(target=autodiscover_and_add, daemon=True).start()

# Прогрев TTS в фоне: грузит/докачивает голос Piper заранее, чтобы первый
# голосовой алерт не блокировался на скачивании модели. Мягко деградирует.
if TTS_ENABLED:
    import threading
    from backend.tts.service import get_tts_service
    threading.Thread(target=lambda: get_tts_service().available, daemon=True).start()

if __name__ == "__main__":
    from waitress import serve
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Запуск на http://127.0.0.1:{port}")
    serve(app, host='0.0.0.0', port=port)
