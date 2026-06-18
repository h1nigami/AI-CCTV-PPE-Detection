from flask import jsonify, request


def configure_camera_routes(app, state, camera_captures):

    @app.route("/cameras")
    def get_cameras():
        from backend.config import CAMERAS, get_camera_config
        result = {}
        for k, v in CAMERAS.items():
            cfg = get_camera_config(k)
            result[k] = {
                "source": v if isinstance(v, int) else v,
                "detect_enabled": cfg.get("detect_enabled", True),
            }
        return jsonify({"cameras": result})

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

    @app.route("/api/cameras/<cam_id>/analytics", methods=["PUT"])
    def api_toggle_analytics(cam_id):
        from backend.config import CAMERAS, set_camera_config, get_camera_config
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        data = request.get_json() or {}
        detect_enabled = data.get("detect_enabled")
        if detect_enabled is None:
            return jsonify({"error": "detect_enabled обязателен"}), 400
        set_camera_config(cam_id, detect_enabled=bool(detect_enabled))
        cfg = get_camera_config(cam_id)
        return jsonify({"status": "updated", "name": cam_id, "detect_enabled": cfg.get("detect_enabled")})

    # ── Зоны (полигоны редактора) ───────────────────────────────
    @app.route("/api/cameras/discover", methods=["POST"])
    def api_discover_cameras():
        """Найти открытые RTSP-потоки в локальной сети. {add:true} — добавить."""
        from backend.main import discover_cameras
        data = request.get_json(silent=True) or {}
        result = discover_cameras(add=bool(data.get("add")))
        return jsonify(result)

    @app.route("/api/cameras/<cam_id>/zones", methods=["GET"])
    def api_get_zones(cam_id):
        from backend.config import CAMERAS
        from backend.zones import get_zones
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        return jsonify({"zones": get_zones(cam_id)})

    @app.route("/api/cameras/<cam_id>/zones", methods=["PUT"])
    def api_set_zones(cam_id):
        """Полная замена набора зон камеры (как сохраняет редактор)."""
        from backend.config import CAMERAS
        from backend.zones import set_zones
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        data = request.get_json() or {}
        try:
            zones = set_zones(cam_id, data.get("zones", []))
        except (ValueError, TypeError) as exc:
            return jsonify({"error": f"Некорректная зона: {exc}"}), 400
        return jsonify({"status": "updated", "zones": zones})

    @app.route("/api/cameras/<cam_id>/zones", methods=["POST"])
    def api_add_zone(cam_id):
        from backend.config import CAMERAS
        from backend.zones import add_zone
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        try:
            zone = add_zone(cam_id, request.get_json() or {})
        except (ValueError, TypeError) as exc:
            return jsonify({"error": f"Некорректная зона: {exc}"}), 400
        return jsonify({"status": "added", "zone": zone}), 201

    @app.route("/api/cameras/<cam_id>/zones/<zone_id>", methods=["PUT"])
    def api_update_zone(cam_id, zone_id):
        from backend.config import CAMERAS
        from backend.zones import update_zone
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        try:
            zone = update_zone(cam_id, zone_id, request.get_json() or {})
        except (ValueError, TypeError) as exc:
            return jsonify({"error": f"Некорректная зона: {exc}"}), 400
        if zone is None:
            return jsonify({"error": "Зона не найдена"}), 404
        return jsonify({"status": "updated", "zone": zone})

    @app.route("/api/cameras/<cam_id>/zones/<zone_id>", methods=["DELETE"])
    def api_delete_zone(cam_id, zone_id):
        from backend.config import CAMERAS
        from backend.zones import delete_zone
        if cam_id not in CAMERAS:
            return jsonify({"error": "Камера не найдена"}), 404
        if not delete_zone(cam_id, zone_id):
            return jsonify({"error": "Зона не найдена"}), 404
        return jsonify({"status": "deleted", "id": zone_id})

    return app
