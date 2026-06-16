from flask import jsonify, request


def configure_reid_routes(app, state):

    @app.route("/api/reid/persons")
    def reid_list():
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        return jsonify({"persons": state.gallery.list_all()})

    @app.route("/api/reid/persons/<int:global_id>/rename", methods=["POST"])
    def reid_rename(global_id):
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        data = request.get_json()
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Имя не может быть пустым"}), 400
        if state.gallery.rename(global_id, name):
            return jsonify({"status": "renamed", "global_id": global_id, "name": name})
        return jsonify({"error": "Не найдено"}), 404

    @app.route("/api/reid/persons/<int:global_id>", methods=["DELETE"])
    def reid_delete(global_id):
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        if state.gallery.delete(global_id):
            return jsonify({"status": "deleted", "global_id": global_id})
        return jsonify({"error": "Не найдено"}), 404

    @app.route("/api/reid/clear", methods=["POST"])
    def reid_clear():
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        state.gallery.clear()
        return jsonify({"status": "cleared"})

    @app.route("/api/reid/stats")
    def reid_stats():
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        return jsonify({
            "total_persons": state.gallery.count,
            "total_approved": len(list(state._approved.keys())) if hasattr(state, '_approved') else 0,
        })

    return app
