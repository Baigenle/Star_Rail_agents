from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    database: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user = database.get(User, str(payload.get("sub"))) if payload else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效或已过期")
    return user


def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    database: Session = Depends(get_db),
) -> User | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    payload = decode_access_token(credentials.credentials)
    user = database.get(User, str(payload.get("sub"))) if payload else None
    return user if user and user.is_active else None


def is_admin_username(username: str) -> bool:
    # 管理员身份来自部署环境，而不是前端或数据库可编辑字段，避免普通用户自行提权。
    # 这里匹配的是注册“用户名”，不是邮箱；统一小写并忽略配置中的空格。
    return username in {
        item.strip().lower()
        for item in settings.admin_usernames.split(",")
        if item.strip()
    }


def public_user(user: User) -> UserResponse:
    return UserResponse.model_validate(user).model_copy(
        update={"is_admin": is_admin_username(user.username)}
    )


def auth_response(user: User) -> AuthResponse:
    token, expires_in = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        expires_in=expires_in,
        user=public_user(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, database: Session = Depends(get_db)) -> AuthResponse:
    duplicate = database.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if duplicate:
        field = "用户名" if duplicate.username == payload.username else "邮箱"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{field}已被使用")
    user = User(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, database: Session = Depends(get_db)) -> AuthResponse:
    account = payload.account.strip().lower()
    user = database.scalar(select(User).where(or_(User.username == account, User.email == account)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    return auth_response(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return public_user(user)
