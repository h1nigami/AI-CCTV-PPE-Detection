"""Tests for backend/auth/service.py, backend/auth/middleware.py, backend/auth/routes.py"""
from __future__ import annotations
import pytest
import jwt as pyjwt
from datetime import datetime, timedelta


# ── Additional fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def registered_user(auth_db):
    from backend.auth.service import register_user
    return register_user("testuser", "password123", "test@example.com", "viewer")


@pytest.fixture
def middleware_app(auth_db):
    """Minimal Flask app wiring login_required and admin_required decorators."""
    from flask import Flask, jsonify, g
    from backend.auth.middleware import login_required, admin_required

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/protected")
    @login_required
    def protected():
        return jsonify({"auth_type": g.auth_type, "user": g.current_user})

    @app.route("/admin-only")
    @admin_required
    def admin_only():
        return jsonify({"ok": True})

    return app.test_client()


# ── service.py: token operations ─────────────────────────────────────────────

class TestCreateAndVerifyToken:
    def test_access_token_has_expected_payload(self, auth_db):
        import backend.auth.service as svc
        from backend.auth.service import _create_token
        token = _create_token(1, "alice", "admin", "access")
        payload = pyjwt.decode(token, svc.JWT_SECRET, algorithms=[svc.JWT_ALGORITHM])
        assert payload["user_id"] == 1
        assert payload["username"] == "alice"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_type_field(self, auth_db):
        import backend.auth.service as svc
        from backend.auth.service import _create_token
        token = _create_token(1, "alice", "viewer", "refresh")
        payload = pyjwt.decode(token, svc.JWT_SECRET, algorithms=[svc.JWT_ALGORITHM])
        assert payload["type"] == "refresh"

    def test_verify_token_valid_access(self, auth_db):
        from backend.auth.service import _create_token, verify_token
        token = _create_token(42, "bob", "viewer", "access")
        payload = verify_token(token, token_type="access")
        assert payload is not None
        assert payload["user_id"] == 42
        assert payload["username"] == "bob"

    def test_verify_token_rejects_wrong_type(self, auth_db):
        from backend.auth.service import _create_token, verify_token
        token = _create_token(1, "alice", "admin", "access")
        assert verify_token(token, token_type="refresh") is None

    def test_verify_token_tampered_signature(self, auth_db):
        from backend.auth.service import _create_token, verify_token
        token = _create_token(1, "alice", "admin", "access")
        tampered = token[:-4] + "xxxx"
        assert verify_token(tampered) is None

    def test_verify_token_garbage_string(self, auth_db):
        from backend.auth.service import verify_token
        assert verify_token("not.a.token") is None

    def test_verify_token_expired(self, auth_db):
        import backend.auth.service as svc
        from backend.auth.service import _create_token, verify_token
        # Build a token with exp already in the past
        token = _create_token(1, "alice", "admin", "access")
        payload = pyjwt.decode(
            token, svc.JWT_SECRET, algorithms=[svc.JWT_ALGORITHM],
            options={"verify_exp": False}
        )
        payload["exp"] = datetime.utcnow() - timedelta(seconds=10)
        expired_token = pyjwt.encode(payload, svc.JWT_SECRET, algorithm=svc.JWT_ALGORITHM)
        assert verify_token(expired_token) is None


# ── service.py: user registration ────────────────────────────────────────────

class TestRegisterUser:
    def test_register_success_returns_id_and_role(self, auth_db):
        from backend.auth.service import register_user
        result = register_user("newuser", "pass123", "new@example.com", "viewer")
        assert "error" not in result
        assert result["username"] == "newuser"
        assert result["role"] == "viewer"
        assert isinstance(result["id"], int)

    def test_register_duplicate_username_returns_error(self, auth_db):
        from backend.auth.service import register_user
        register_user("dupeuser", "pass123")
        result = register_user("dupeuser", "different456")
        assert "error" in result

    def test_register_duplicate_email_returns_error(self, auth_db):
        from backend.auth.service import register_user
        register_user("user1", "pass123", "shared@example.com")
        result = register_user("user2", "pass456", "shared@example.com")
        assert "error" in result

    def test_register_unknown_role_falls_back_to_viewer(self, auth_db):
        from backend.auth.service import register_user
        result = register_user("roleuser", "pass123", role="superadmin")
        assert result["role"] == "viewer"


# ── service.py: login ─────────────────────────────────────────────────────────

class TestLoginUser:
    def test_login_correct_credentials_returns_tokens(self, auth_db, registered_user):
        from backend.auth.service import login_user
        result = login_user("testuser", "password123")
        assert "error" not in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user"]["username"] == "testuser"

    def test_login_wrong_password_returns_error(self, auth_db, registered_user):
        from backend.auth.service import login_user
        result = login_user("testuser", "wrongpassword")
        assert "error" in result

    def test_login_unknown_username_returns_error(self, auth_db):
        from backend.auth.service import login_user
        result = login_user("nonexistent", "anypassword")
        assert "error" in result

    def test_login_inactive_user_returns_error(self, auth_db):
        from sqlalchemy.orm import sessionmaker
        from backend.db.models import User, UserRole
        from werkzeug.security import generate_password_hash
        import backend.auth.service as svc
        from backend.auth.service import login_user

        session = svc.get_session()
        session.add(User(
            username="inactiveuser",
            password_hash=generate_password_hash("pass123"),
            role=UserRole.VIEWER,
            is_active=False,
        ))
        session.commit()
        session.close()

        assert "error" in login_user("inactiveuser", "pass123")


# ── service.py: refresh token ─────────────────────────────────────────────────

class TestRefreshToken:
    def test_refresh_valid_token_returns_new_access_token(self, auth_db, registered_user):
        from backend.auth.service import login_user, refresh_token
        login_result = login_user("testuser", "password123")
        result = refresh_token(login_result["refresh_token"])
        assert "error" not in result
        assert "access_token" in result

    def test_refresh_invalid_string_returns_error(self, auth_db):
        from backend.auth.service import refresh_token
        assert "error" in refresh_token("not-a-valid-token")

    def test_refresh_with_access_token_fails(self, auth_db, registered_user):
        from backend.auth.service import login_user, refresh_token
        login_result = login_user("testuser", "password123")
        assert "error" in refresh_token(login_result["access_token"])


# ── service.py: API keys ──────────────────────────────────────────────────────

class TestApiKey:
    def test_create_api_key_format(self, auth_db):
        from backend.auth.service import create_api_key
        result = create_api_key("CI Bot", "api", 30)
        assert result["key"].startswith("ppe_")
        assert len(result["key"]) > 10
        assert result["name"] == "CI Bot"

    def test_verify_api_key_valid(self, auth_db):
        from backend.auth.service import create_api_key, verify_api_key
        created = create_api_key("test-key", "api", 30)
        result = verify_api_key(created["key"])
        assert result is not None
        assert result["name"] == "test-key"

    def test_verify_api_key_unknown_returns_none(self, auth_db):
        from backend.auth.service import verify_api_key
        assert verify_api_key("ppe_totally_unknown_key") is None

    def test_verify_api_key_expired_returns_none(self, auth_db):
        from backend.db.models import ApiKey, UserRole
        import backend.auth.service as svc
        from backend.auth.service import verify_api_key

        session = svc.get_session()
        session.add(ApiKey(
            key="ppe_expired_key_test",
            name="Expired",
            role=UserRole.API,
            is_active=True,
            expires_at=datetime.utcnow() - timedelta(days=1),
        ))
        session.commit()
        session.close()

        assert verify_api_key("ppe_expired_key_test") is None

    def test_verify_api_key_inactive_returns_none(self, auth_db):
        from backend.db.models import ApiKey, UserRole
        import backend.auth.service as svc
        from backend.auth.service import verify_api_key

        session = svc.get_session()
        session.add(ApiKey(
            key="ppe_inactive_key_test",
            name="Inactive",
            role=UserRole.API,
            is_active=False,
        ))
        session.commit()
        session.close()

        assert verify_api_key("ppe_inactive_key_test") is None


# ── middleware.py ─────────────────────────────────────────────────────────────

class TestLoginRequiredMiddleware:
    def test_no_authorization_header_returns_401(self, middleware_app):
        resp = middleware_app.get("/protected")
        assert resp.status_code == 401

    def test_valid_jwt_sets_g_current_user(self, auth_db, middleware_app):
        from backend.auth.service import _create_token
        token = _create_token(1, "alice", "viewer", "access")
        resp = middleware_app.get("/protected",
                                  headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["auth_type"] == "jwt"
        assert data["user"]["username"] == "alice"

    def test_invalid_token_returns_401(self, middleware_app):
        resp = middleware_app.get("/protected",
                                  headers={"Authorization": "Bearer garbage.token.value"})
        assert resp.status_code == 401

    def test_valid_api_key_sets_auth_type(self, auth_db, middleware_app):
        from backend.auth.service import create_api_key
        created = create_api_key("middleware-test", "api", 30)
        resp = middleware_app.get("/protected",
                                  headers={"Authorization": f"Bearer {created['key']}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["auth_type"] == "api_key"


class TestAdminRequiredMiddleware:
    def test_viewer_role_returns_403(self, auth_db, middleware_app):
        from backend.auth.service import _create_token
        token = _create_token(1, "viewer_user", "viewer", "access")
        resp = middleware_app.get("/admin-only",
                                  headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_admin_role_returns_200(self, auth_db, middleware_app):
        from backend.auth.service import _create_token
        token = _create_token(1, "admin_user", "admin", "access")
        resp = middleware_app.get("/admin-only",
                                  headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


# ── routes.py ────────────────────────────────────────────────────────────────

class TestRegisterEndpoint:
    def test_username_too_short_returns_400(self, auth_client):
        resp = auth_client.post("/api/auth/register",
                                json={"username": "ab", "password": "pass123"})
        assert resp.status_code == 400

    def test_password_too_short_returns_400(self, auth_client):
        resp = auth_client.post("/api/auth/register",
                                json={"username": "validuser", "password": "123"})
        assert resp.status_code == 400

    def test_register_success_returns_201(self, auth_client):
        resp = auth_client.post("/api/auth/register",
                                json={"username": "newuser", "password": "validpass",
                                      "email": "new@example.com"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["username"] == "newuser"

    def test_duplicate_username_returns_409(self, auth_client):
        auth_client.post("/api/auth/register",
                         json={"username": "dupuser", "password": "validpass"})
        resp = auth_client.post("/api/auth/register",
                                json={"username": "dupuser", "password": "validpass"})
        assert resp.status_code == 409


class TestLoginEndpoint:
    def test_missing_password_returns_400(self, auth_client):
        resp = auth_client.post("/api/auth/login",
                                json={"username": "someone"})
        assert resp.status_code == 400

    def test_wrong_credentials_returns_401(self, auth_client):
        auth_client.post("/api/auth/register",
                         json={"username": "logintest", "password": "goodpass"})
        resp = auth_client.post("/api/auth/login",
                                json={"username": "logintest", "password": "badpass"})
        assert resp.status_code == 401

    def test_success_returns_access_and_refresh_tokens(self, auth_client):
        auth_client.post("/api/auth/register",
                         json={"username": "logintest2", "password": "goodpass"})
        resp = auth_client.post("/api/auth/login",
                                json={"username": "logintest2", "password": "goodpass"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "access_token" in data
        assert "refresh_token" in data


class TestMeEndpoint:
    def test_unauthenticated_returns_401(self, auth_client):
        assert auth_client.get("/api/auth/me").status_code == 401

    def test_with_valid_jwt_returns_user_info(self, auth_client):
        auth_client.post("/api/auth/register",
                         json={"username": "meuser", "password": "passme123"})
        login_resp = auth_client.post("/api/auth/login",
                                      json={"username": "meuser", "password": "passme123"})
        token = login_resp.get_json()["access_token"]
        resp = auth_client.get("/api/auth/me",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["username"] == "meuser"


class TestApiKeyEndpoint:
    def test_viewer_cannot_create_key(self, auth_db, auth_client):
        from backend.auth.service import _create_token
        token = _create_token(1, "viewer", "viewer", "access")
        resp = auth_client.post("/api/auth/api-keys",
                                json={"name": "test"},
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_admin_can_create_key(self, auth_db, auth_client):
        from backend.auth.service import _create_token
        token = _create_token(1, "admin", "admin", "access")
        resp = auth_client.post("/api/auth/api-keys",
                                json={"name": "new-key"},
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        assert resp.get_json()["key"].startswith("ppe_")

    def test_empty_name_returns_400(self, auth_db, auth_client):
        from backend.auth.service import _create_token
        token = _create_token(1, "admin", "admin", "access")
        resp = auth_client.post("/api/auth/api-keys",
                                json={"name": ""},
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400
