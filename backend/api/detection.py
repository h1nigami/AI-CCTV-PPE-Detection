import os
import uuid
import cv2
from flask import Flask, send_file, Response, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from backend.detection.engine import get_danger_zone, is_in_danger_zone
from backend.visualization.renderer import draw_danger_zone, put_text
from backend.config import CONF_THRESH, get_detection_setting


def _get_boxes_by_class(boxes, classes, names, class_name: str):
    return [boxes[i] for i, c in enumerate(classes) if names[int(c)] == class_name]


def _annotate_with_zone(result, names):
    """Поверх стандартной разметки YOLO строит опасную зону по конусам и
    помечает людей: красным «В ЗОНЕ», зелёным «Вне зоны». Возвращает кадр."""
    annotated = result.plot().copy()
    boxes = result.boxes.xyxy.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)
    cone_boxes = _get_boxes_by_class(boxes, classes, names, "Конус безопасности")
    person_boxes = _get_boxes_by_class(boxes, classes, names, "Человек")
    danger_zone = get_danger_zone(cone_boxes)
    if danger_zone is None:
        return annotated
    annotated = draw_danger_zone(annotated, danger_zone)
    for box in cone_boxes:
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 128, 255), 2)
        annotated = put_text(annotated, "Конус", (x1, max(0, y1 - 20)), color=(0, 128, 255))
    in_zone = 0
    for box in person_boxes:
        x1, y1, x2, y2 = map(int, box)
        inside = is_in_danger_zone(box, danger_zone)
        in_zone += int(inside)
        color = (0, 0, 255) if inside else (0, 200, 0)
        label = "В ЗОНЕ" if inside else "Вне зоны"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
        annotated = put_text(annotated, label, (x1, max(0, y1 - 20)), color=color)
    annotated = put_text(
        annotated,
        f"Опасная зона: {len(cone_boxes)} кон. | в зоне {in_zone}/{len(person_boxes)} чел.",
        (10, 30), color=(0, 0, 255))
    return annotated


def configure_detection_routes(app, state, annotated_buffers, generate_live_feed,
                                start_live, stop_live, model,
                                start_face_workers=None, stop_face_workers=None):

    @app.route("/start", methods=["POST"])
    def start():
        start_live()
        return jsonify({"status": "started"})

    @app.route("/stop", methods=["POST"])
    def stop():
        stop_live()
        return jsonify({"status": "stopped"})

    @app.route("/video_frame/<cam_id>")
    def video_frame(cam_id):
        from backend.config import CAMERAS, STREAM_STALE_SEC
        if cam_id not in CAMERAS:
            return "Камера не найдена", 404
        ann_buf = annotated_buffers.get(cam_id)
        if ann_buf is None:
            return "Буфер не найден", 404
        # Свежесть судим по RAW-буферу захвата: при потере камеры capture
        # перестаёт писать кадры → отдаём 204, фронт показывает «NO SIGNAL»
        # (иначе висел бы замороженный последний кадр как «живой»).
        from backend.main import frame_buffers
        raw_buf = frame_buffers.get(cam_id)
        if raw_buf is not None and raw_buf.age() > STREAM_STALE_SEC:
            return b"", 204
        frame = ann_buf.read()
        if frame is None:
            return b"", 204
        # Качество 85 вместо 95 — на 30-40% быстрее кодирование,
        # визуально разница незаметна при 1280x720
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            return b"", 500
        return Response(
            buffer.tobytes(),
            mimetype='image/jpeg',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.route("/video_feed/<cam_id>")
    def video_feed_cam(cam_id):
        from backend.config import CAMERAS
        if cam_id not in CAMERAS:
            return "Камера не найдена", 404
        return Response(
            generate_live_feed(cam_id),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                     "Pragma": "no-cache", "Expires": "0"},
        )

    @app.route("/video_feed")
    def video_feed():
        from backend.config import CAMERAS
        cam_id = list(CAMERAS.keys())[0] if CAMERAS else "cam1"
        return Response(
            generate_live_feed(cam_id),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                     "Pragma": "no-cache", "Expires": "0"},
        )

    @app.route("/api/detect-modes", methods=["GET"])
    def api_get_detect_modes():
        from backend.config import DETECT_MODES
        return jsonify({"modes": dict(DETECT_MODES)})

    @app.route("/api/detect-modes", methods=["PUT"])
    def api_set_detect_modes():
        from backend.config import DETECT_MODES, save_detect_modes
        data = request.get_json() or {}
        old_faces = DETECT_MODES.get("faces", True)
        for key in ("people", "ppe", "faces", "movement"):
            if key in data:
                DETECT_MODES[key] = bool(data[key])
        if not DETECT_MODES["people"]:
            DETECT_MODES["ppe"] = False
            DETECT_MODES["faces"] = False
            # Перемещения строятся поверх детекции людей — гасим вслед за ней.
            DETECT_MODES["movement"] = False
        save_detect_modes()
        new_faces = DETECT_MODES.get("faces", True)
        if new_faces != old_faces:
            try:
                if new_faces and start_face_workers:
                    start_face_workers()
                elif not new_faces and stop_face_workers:
                    stop_face_workers()
            except Exception as exc:
                print(f"[Detection] Face worker switch failed: {exc}")
        return jsonify({"status": "updated", "modes": dict(DETECT_MODES)})

    @app.route("/api/ppe-required", methods=["GET"])
    def api_get_ppe_required():
        from backend.config import PPE_REQUIRED_DEFAULT
        return jsonify({"required": list(PPE_REQUIRED_DEFAULT)})

    @app.route("/api/ppe-required", methods=["PUT"])
    def api_set_ppe_required():
        # Какие СИЗ обязательны для выдачи пропуска по жесту «ОК» (дефолт вне
        # пользовательских зон). Мутируем список НА МЕСТЕ — main.py держит ту же
        # ссылку. Пустой список → пропуск выдаётся без требования СИЗ.
        from backend.config import PPE_REQUIRED_DEFAULT, save_ppe_required
        data = request.get_json() or {}
        items = data.get("required", [])
        if not isinstance(items, list):
            return jsonify({"error": "required должен быть списком"}), 400
        PPE_REQUIRED_DEFAULT[:] = [x for x in ("helmet", "mask", "vest") if x in items]
        save_ppe_required()
        return jsonify({"status": "updated", "required": list(PPE_REQUIRED_DEFAULT)})

    @app.route("/api/detection-settings", methods=["GET"])
    def api_get_detection_settings():
        # Возвращаем И текущие значения, И спеку (label/desc/min/max/step/unit/group)
        # — фронт рендерит панель настроек генеративно по спеке.
        from backend.config import DETECTION_SETTINGS, DETECTION_SETTINGS_SPEC
        return jsonify({"settings": dict(DETECTION_SETTINGS),
                        "spec": DETECTION_SETTINGS_SPEC})

    @app.route("/api/detection-settings", methods=["PUT"])
    def api_set_detection_settings():
        # Частичное обновление: {"settings": {key: value, ...}} (или плоский dict).
        # Валидация/clamp по спеке — на бэке (update_detection_settings). Значения
        # читаются точками детекции живыми → применяются без рестарта.
        from backend.config import update_detection_settings
        data = request.get_json(silent=True) or {}
        patch = data.get("settings") if isinstance(data.get("settings"), dict) else data
        updated = update_detection_settings(patch)
        return jsonify({"status": "updated", "settings": updated})

    @app.route("/api/status")
    def api_status():
        return jsonify({"running": state.live_active})

    @app.route("/api/voice_alert")
    def api_voice_alert():
        # Курсорная модель: клиент шлёт ?after=<seq> и получает все алерты новее
        # курсора (не извлекая их из общей очереди). Без after — только текущий
        # курсор (инициализация без переигрывания бэклога). Так несколько вкладок
        # и несколько камер обслуживаются независимо, без «съедания» алертов.
        after = request.args.get("after", type=int)
        return jsonify(state.get_voice_alerts_since(after))

    @app.route("/api/notifications")
    def api_notifications():
        return jsonify({"notifications": state.pop_notifications()})

    @app.route("/api/movement")
    def api_movement():
        # Снапшот перемещений: кто сидит на месте (и сколько), кто встал и идёт.
        # ?cam_id=<id> — по одной камере, иначе по всем. Данные пишутся в
        # process_frame на каждом кадре (эфемерные, последний кадр камеры).
        cam_id = request.args.get("cam_id")
        return jsonify({"movement": state.get_movement(cam_id)})

    @app.route("/api/movement/tracks")
    def api_movement_tracks():
        # Кросс-камерные треки на карте: по личности (global_id) — единая линия
        # пути через все камеры (точки ног, спроецированные гомографией в общие
        # координаты плана). Длина следа — рантайм-настройка movement_map_trail_sec.
        trail = get_detection_setting("movement_map_trail_sec") or 60.0
        return jsonify({"tracks": state.get_map_tracks(trail_sec=float(trail))})

    @app.route("/detection_log")
    def detection_log():
        cam_id = request.args.get("cam_id")
        logs = state.get_log()
        if cam_id:
            logs = [e for e in logs if e.cam_id == cam_id]
        return jsonify({"logs": [
            {"id": e.id, "timestamp": e.timestamp,
             "message": e.message, "category": e.category,
             "cam_id": e.cam_id, "global_id": e.global_id}
            for e in reversed(logs)
        ]})

    @app.route("/export_logs")
    def export_logs():
        import csv
        from io import StringIO
        csv_data = StringIO()
        csv_data.write('\ufeff')
        writer = csv.writer(csv_data)
        writer.writerow(["Timestamp", "Camera", "Category", "Message"])
        for entry in reversed(state.get_log()):
            writer.writerow([entry.timestamp, entry.cam_id,
                             entry.category.capitalize(), entry.message])
        return Response(
            csv_data.getvalue(),
            mimetype="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": "attachment; filename=ppe_logs.csv"}
        )

    UPLOAD_FOLDER = os.path.abspath("uploads")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    @app.route("/upload", methods=["POST"])
    def upload_file():
        file = request.files.get("file")
        if file is None:
            return "No file uploaded", 400
        safe_name = secure_filename(file.filename) or "upload"
        filename = f"{uuid.uuid4().hex}_{safe_name}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        output = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
        try:
            file.save(path)
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                img = cv2.imread(path)
                if img is None:
                    return "Invalid image file", 400
                result = model(img, conf=get_detection_setting("person_conf"))[0]
                annotated = _annotate_with_zone(result, model.names)
                cv2.imwrite(output, annotated)
                with open(output, "rb") as f:
                    data = f.read()
                return Response(data, mimetype="image/jpeg")
            elif filename.lower().endswith((".mp4", ".avi", ".mov")):
                cap = cv2.VideoCapture(path)
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(output, fourcc, 20.0,
                                      (int(cap.get(3)), int(cap.get(4))))
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    result = model(frame, conf=get_detection_setting("person_conf"))[0]
                    annotated = _annotate_with_zone(result, model.names)
                    out.write(annotated)
                cap.release()
                out.release()
                with open(output, "rb") as f:
                    data = f.read()
                return Response(data, mimetype="video/mp4")
            return "Unsupported file type", 400
        finally:
            for p in (path, output):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass

    return app
