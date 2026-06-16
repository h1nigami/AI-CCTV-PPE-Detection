from flask import jsonify, request


def configure_camera_routes(app, state, camera_captures):

    @app.route("/cameras")
    def get_cameras():
        from backend.config import CAMERAS
        return jsonify({"cameras": {k: v if isinstance(v, int) else v for k, v in CAMERAS.items()}})

    @app.route("/api/cameras", methods=["POST"])
    def api_add_camera():
        from backend.main import add_camera
        from backend.config import CAMERAS
        data = request.get_json()
        cam_id = (data.get("name") or "").strip()
        source = data.get("source")
        if not cam_id:
            return jsonify({"error": "Имя камеры не может быть пустым"}), 400
        if not source and source != 0:
            return jsonify({"error": "Источник не может быть пустым"}), 400
        if cam_id in CAMERAS:
            return jsonify({"error": f"Камера '{cam_id}' уже существует"}), 409
        try:
            source_int = int(source)
        except (ValueError, TypeError):
            source_int = source
        add_camera(cam_id, source_int)
        return jsonify({"status": "added", "name": cam_id, "source": source_int}), 201

    @app.route("/api/cameras/<cam_id>", methods=["PUT"])
    def api_edit_camera(cam_id):
        from backend.main import _init_camera_resources
        from backend.config import CAMERAS, save_cameras
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        data = request.get_json()
        source = data.get("source")
        if not source and source != 0:
            return jsonify({"error": "Источник не может быть пустым"}), 400
        try:
            source_int = int(source)
        except (ValueError, TypeError):
            source_int = source
        if state.live_active and cam_id in camera_captures:
            camera_captures[cam_id].stop()
            del camera_captures[cam_id]
        CAMERAS[cam_id] = source_int
        save_cameras()
        if state.live_active:
            _init_camera_resources(cam_id, source_int)
            camera_captures[cam_id].start()
        return jsonify({"status": "updated", "name": cam_id, "source": source_int})

    @app.route("/api/cameras/<cam_id>", methods=["DELETE"])
    def api_delete_camera(cam_id):
        from backend.main import remove_camera
        from backend.config import CAMERAS
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        remove_camera(cam_id)
        return jsonify({"status": "deleted", "name": cam_id})

    @app.route("/api/cameras/<cam_id>/rename", methods=["POST"])
    def api_rename_camera(cam_id):
        from backend.main import rename_camera
        from backend.config import CAMERAS
        data = request.get_json()
        new_name = (data.get("name") or "").strip()
        if not new_name:
            return jsonify({"error": "Имя не может быть пустым"}), 400
        if new_name in CAMERAS:
            return jsonify({"error": f"Камера '{new_name}' уже существует"}), 409
        if not rename_camera(cam_id, new_name):
            return jsonify({"error": "Камера не найдена"}), 404
        return jsonify({"status": "renamed", "old": cam_id, "new": new_name, "source": CAMERAS[new_name]})

    return app
