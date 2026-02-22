from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, verify_password, hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter()
_settings = Settings()


def _get_user(db: Session, username: str) -> User | None:
    """DB에서 사용자를 조회한다. 없으면 .env 관리자 계정과 비교한다."""
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user

    # DB에 사용자가 없을 때 .env 관리자 시드 사용
    if username == _settings.admin_username and _settings.admin_password_hash:
        sentinel = User(
            id=0,
            username=_settings.admin_username,
            password_hash=_settings.admin_password_hash,
        )
        return sentinel

    return None


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """사용자 자격증명을 검증하고 JWT 액세스 토큰을 발급한다."""
    user = _get_user(db, payload.username)

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자명 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token, username=user.username)
