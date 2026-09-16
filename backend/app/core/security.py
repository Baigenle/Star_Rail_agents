import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        # 常量时间比较可减少根据响应耗时推测密码摘要的风险。
        return hmac.compare_digest(digest, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.jwt_expire_minutes)
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64encode(
        json.dumps({"sub": user_id, "iat": int(now.timestamp()), "exp": int(expires.timestamp())}, separators=(",", ":")).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = hmac.new(settings.jwt_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}", int((expires - now).total_seconds())


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = hmac.new(settings.jwt_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
        # 先验证签名，再信任 sub/exp；任何解析异常都按无效登录处理，不向客户端泄露细节。
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        data = json.loads(_b64decode(payload))
        if int(data.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            return None
        return data if data.get("sub") else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
