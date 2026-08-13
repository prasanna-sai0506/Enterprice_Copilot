from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGO = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def create_token(payload: dict) -> str:
    data = dict(payload)
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    data["exp"] = exp
    return jwt.encode(data, settings.JWT_SECRET, algorithm=ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])


def try_decode(token: str) -> dict | None:
    try:
        return decode_token(token)
    except JWTError:
        return None
