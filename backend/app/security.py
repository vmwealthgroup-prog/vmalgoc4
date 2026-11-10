import time
import bcrypt, jwt
from cryptography.fernet import Fernet
from .config import get_settings


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode()[:72], h.encode())
    except ValueError:
        return False


def make_token(user_id: int, role: str) -> str:
    s = get_settings()
    return jwt.encode({"sub": str(user_id), "role": role, "exp": int(time.time()) + s.access_token_minutes * 60},
                      s.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:  # development only: derive a stable throwaway key from the secret
        import base64, hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(text: str) -> str:
    return _fernet().decrypt(text.encode()).decode()
