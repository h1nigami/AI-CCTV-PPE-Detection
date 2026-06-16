from __future__ import annotations
from functools import wraps
from flask import request, jsonify, g
from backend.auth.service import verify_token, verify_api_key


def _get_token_from_header() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_header()
        if not token:
            return jsonify({"error": "Требуется авторизация"}), 401
        payload = verify_token(token, token_type="access")
        if payload is None:
            api_key = verify_api_key(token)
            if api_key is None:
                return jsonify({"error": "Недействительный токен"}), 401
            g.current_user = api_key
            g.auth_type = "api_key"
        else:
            g.current_user = payload
            g.auth_type = "jwt"
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        role = g.current_user.get("role", "")
        if role != "admin":
            return jsonify({"error": "Требуются права администратора"}), 403
        return f(*args, **kwargs)
    return decorated


def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_header()
        if not token:
            return jsonify({"error": "Требуется API ключ"}), 401
        api_key = verify_api_key(token)
        if api_key is None:
            payload = verify_token(token, token_type="access")
            if payload is None:
                return jsonify({"error": "Недействительный API ключ"}), 401
            g.current_user = payload
            g.auth_type = "jwt"
        else:
            g.current_user = api_key
            g.auth_type = "api_key"
        return f(*args, **kwargs)
    return decorated
