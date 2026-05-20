"""
Generación y validación de JWT compartido entre API y Game Server.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================
# Passwords
# ============================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ============================================
# JWT
# ============================================

def crear_token(usuario_id: int, username: str) -> str:
    """Genera un JWT con la info del usuario."""
    expira = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    payload = {
        "sub": str(usuario_id),
        "username": username,
        "exp": expira,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(token: str) -> Optional[dict]:
    """
    Valida un JWT y devuelve su payload.
    Retorna None si es inválido o está expirado.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None
