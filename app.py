import os
import uuid
import cv2
from ultralytics import YOLO
from flask import Flask, send_file, render_template, Response, request, jsonify
from main import generate_live_feed, start_live, stop_live, state, model
from waitress import serve

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    start_live()
    return jsonify({"status": "started"})


@app.route("/stop", methods=["POST"])
def stop():
    stop_live()
    return jsonify({"status": "stopped"})


@app.route("/video_feed")
def video_feed():
    return Response(generate_live_feed(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/detection_log")
def detection_log():
    logs = [
        {
            "id":        e.id,
            "timestamp": e.timestamp,
            "message":   e.message,
            "category":  e.category,
        }
        for e in reversed(state.get_log())
    ]
    return jsonify({"logs": logs})


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/upload", methods=["POST"])
def upload_file():
    from PIL import Image

    file = request.files["file"]
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):
        img = cv2.imread(path)
        results = model(img)[0]
        result_img = results.plot()
        output_path = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
        cv2.imwrite(output_path, result_img)
        return send_file(output_path, mimetype="image/jpeg")

    elif filename.lower().endswith((".mp4", ".avi", ".mov")):
        cap = cv2.VideoCapture(path)
        output_path = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, 20.0,
                              (int(cap.get(3)), int(cap.get(4))))
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            results = model(frame)[0]
            out.write(results.plot())

        cap.release()
        out.release()
        return send_file(output_path, mimetype="video/mp4")

    return "Unsupported file type", 400


@app.route("/export_logs")
def export_logs():
    import csv
    from io import StringIO

    csv_data = StringIO()
    csv_data.write('\ufeff')  # UTF-8 BOM для Excel
    writer = csv.writer(csv_data)
    writer.writerow(["Timestamp", "Category", "Status", "Details"])

    for entry in reversed(state.get_log()):
        msg = entry.message
        status, details = msg.split("|", 1) if "|" in msg else (msg, "")
        writer.writerow([
            entry.timestamp,
            entry.category.capitalize(),
            status.strip(),
            details.strip()
        ])

    return Response(
        csv_data.getvalue(),
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=ppe_detection_logs.csv"}
    )

@app.route("/test_print", methods=["POST"])
def test_print():
    import numpy as np
    from printer import print_frame

    # Создаём тестовый чёрный кадр вместо реального
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    statuses = ["Все СИЗ на месте", "Нет: каска, маска"]
    success  = print_frame(fake_frame, statuses)

    return jsonify({"printed": success})


if __name__ == "__main__":
    print("Запуск на http://localhost:8000")
    serve(app, host='0.0.0.0', port=8000)