"""JWT 인증 및 비밀번호 해싱 유틸리티"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings

_settings = Settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """평문 비밀번호를 bcrypt 해시로 변환한다."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """평문 비밀번호와 해시를 비교한다."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT 액세스 토큰을 생성한다."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=_settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, _settings.secret_key, algorithm=_settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    """JWT 토큰을 검증하고 페이로드를 반환한다. 유효하지 않으면 예외를 발생시킨다."""
    try:
        payload = jwt.decode(
            token, _settings.secret_key, algorithms=[_settings.jwt_algorithm]
        )
        return payload
    except JWTError as exc:
        raise ValueError(f"유효하지 않은 토큰: {exc}") from exc
