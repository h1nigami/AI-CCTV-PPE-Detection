from flask import jsonify, request


def configure_reid_routes(app, state):

    @app.route("/api/reid/persons")
    def reid_list():
        if state.gallery is None:
            return jsonify({"error": "Re-ID не активен"}), 400
        approvals = state.get_active_approvals()
        persons = state.gallery.list_all()
        for p in persons:
            left = approvals.get(p["global_id"], 0)
            # Остаток пропуска в секундах (0 — пропуска нет). Пока > 0, на человека
            # не срабатывают голосовые предупреждения о нехватке СИЗ.
            p["pass_seconds_left"] = int(left)
        return jsonify({"persons": persons})

    @app.route("/api/reid/persons/<int:global_id>/approve", methods=["POST"])
    def reid_approve(global_id):
        """Выдать пропуск личности вручную (на APPROVAL_DURATION секунд)."""
        state.grant_approval(global_id)
        left = state.get_active_approvals().get(global_id, 0)
        return jsonify({"status": "approved", "global_id": global_id,
                        "pass_seconds_left": int(left)})

    @app.route("/api/reid/persons/<int:global_id>/revoke", methods=["POST"])
    def reid_revoke(global_id):
        """Сбросить пропуск личности — снова под контролем СИЗ."""
        revoked = state.revoke_approval(global_id)
        return jsonify({
            "status": "revoked" if revoked else "no_active_pass",
            "global_id": global_id,
        })

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
            # get_active_approvals() считает только НЕистёкшие пропуска и под локом
            # (прямой доступ к state._approved давал бы гонку и учитывал просрочку).
            "total_approved": len(state.get_active_approvals()),
        })

    return app
