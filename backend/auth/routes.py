from __future__ import annotations
from flask import Blueprint, request, jsonify, g
from backend.auth.service import (
    register_user, login_user, refresh_token, create_api_key, get_user_by_id
)
from backend.auth.middleware import login_required, admin_required

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    email = (data.get("email") or "").strip() or None
    role = data.get("role", "viewer")
    if not username or len(username) < 3:
        return jsonify({"error": "Имя пользователя должно быть не менее 3 символов"}), 400
    if len(password) < 6:
        return jsonify({"error": "Пароль должен быть не менее 6 символов"}), 400
    result = register_user(username, password, email, role)
    if "error" in result:
        return jsonify(result), 409
    return jsonify(result), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Имя пользователя и пароль обязательны"}), 400
    result = login_user(username, password)
    if "error" in result:
        return jsonify(result), 401
    return jsonify(result)


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json() or {}
    token = data.get("refresh_token", "")
    if not token:
        return jsonify({"error": "refresh_token обязателен"}), 400
    result = refresh_token(token)
    if "error" in result:
        return jsonify(result), 401
    return jsonify(result)


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    if g.auth_type == "api_key":
        return jsonify({
            "auth_type": "api_key",
            "name": g.current_user.get("name"),
            "role": g.current_user.get("role"),
        })
    user = get_user_by_id(g.current_user["user_id"])
    if not user:
        return jsonify({"error": "Пользователь не найден"}), 404
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    })


@auth_bp.route("/api-keys", methods=["POST"])
@admin_required
def create_key():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    role = data.get("role", "api")
    expires_days = data.get("expires_days", 365)
    if not name:
        return jsonify({"error": "Имя ключа обязательно"}), 400
    result = create_api_key(name, role, expires_days)
    return jsonify(result), 201
