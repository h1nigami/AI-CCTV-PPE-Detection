from __future__ import annotations
import uuid
from datetime import datetime, timedelta
import jwt
import jwt as _jwt
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_
from backend.db.engine import get_session
from backend.db.models import User, UserRole, ApiKey

JWT_SECRET = None
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRY = 15
JWT_REFRESH_EXPIRY = 7


def _get_secret() -> str:
    global JWT_SECRET
    if JWT_SECRET is not None:
        return JWT_SECRET
    from pathlib import Path
    secret_path = Path(__file__).parent.parent.parent / "data" / "jwt_secret.txt"
    if secret_path.exists():
        JWT_SECRET = secret_path.read_text().strip()
    else:
        import secrets
        JWT_SECRET = secrets.token_hex(64)
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(JWT_SECRET)
    return JWT_SECRET


def set_jwt_secret(secret: str):
    global JWT_SECRET
    JWT_SECRET = secret


def init_admin(username: str = "admin", password: str = "admin123", email: str = None):
    session = get_session()
    existing = session.query(User).filter_by(username=username).first()
    if existing:
        session.close()
        return
    admin = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    session.commit()
    session.close()
    print(f"[Auth] Создан admin: {username}/{password}")


def register_user(username: str, password: str, email: str = None, role: str = "viewer") -> dict:
    session = get_session()
    try:
        existing = session.query(User).filter(
            or_(User.username == username, User.email == email)
        ).first()
        if existing:
            return {"error": "Пользователь с таким именем или email уже существует"}
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=UserRole(role) if role in UserRole.__members__ else UserRole.VIEWER,
        )
        session.add(user)
        session.commit()
        return {"id": user.id, "username": user.username, "role": user.role.value}
    finally:
        session.close()


def login_user(username: str, password: str) -> dict:
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username, is_active=True).first()
        if not user or not check_password_hash(user.password_hash, password):
            return {"error": "Неверное имя пользователя или пароль"}
        user.last_login = datetime.utcnow()
        session.commit()
        access_token = _create_token(user.id, user.username, user.role.value, "access")
        refresh_token = _create_token(user.id, user.username, user.role.value, "refresh")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": user.id, "username": user.username, "role": user.role.value},
        }
    finally:
        session.close()


def refresh_token(refresh_token_str: str) -> dict:
    payload = verify_token(refresh_token_str, token_type="refresh")
    if payload is None:
        return {"error": "Недействительный refresh token"}
    session = get_session()
    try:
        user = session.query(User).filter_by(id=payload["user_id"], is_active=True).first()
        if not user:
            return {"error": "Пользователь не найден"}
        access_token = _create_token(user.id, user.username, user.role.value, "access")
        return {"access_token": access_token}
    finally:
        session.close()


def _create_token(user_id: int, username: str, role: str, token_type: str) -> str:
    now = datetime.utcnow()
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "type": token_type,
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    if token_type == "access":
        payload["exp"] = now + timedelta(minutes=JWT_ACCESS_EXPIRY)
    else:
        payload["exp"] = now + timedelta(days=JWT_REFRESH_EXPIRY)
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


def verify_token(token_str: str, token_type: str = "access") -> dict | None:
    try:
        payload = jwt.decode(token_str, _get_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_by_id(user_id: int) -> User | None:
    session = get_session()
    try:
        return session.query(User).filter_by(id=user_id).first()
    finally:
        session.close()


def create_api_key(name: str, role: str = "api", expires_days: int = 365) -> dict:
    import secrets
    session = get_session()
    try:
        key = "ppe_" + secrets.token_hex(32)
        api_key = ApiKey(
            key=key,
            name=name,
            role=UserRole(role) if role in UserRole.__members__ else UserRole.API,
            expires_at=datetime.utcnow() + timedelta(days=expires_days) if expires_days else None,
        )
        session.add(api_key)
        session.commit()
        return {"id": api_key.id, "name": api_key.name, "key": key, "role": api_key.role.value}
    finally:
        session.close()


def verify_api_key(key: str) -> dict | None:
    session = get_session()
    try:
        api_key = session.query(ApiKey).filter_by(key=key, is_active=True).first()
        if not api_key:
            return None
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None
        return {"id": api_key.id, "name": api_key.name, "role": api_key.role.value}
    finally:
        session.close()
