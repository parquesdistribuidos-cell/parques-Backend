"""Dependencias de FastAPI."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Usuario
from api.services import auth_service
from shared.auth_jwt import decodificar_token
from shared.db import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """Extrae el usuario del JWT y lo valida contra la DB."""
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decodificar_token(token)
    if payload is None:
        raise creds_error
    usuario_id_str = payload.get("sub")
    if usuario_id_str is None:
        raise creds_error
    try:
        usuario_id = int(usuario_id_str)
    except ValueError:
        raise creds_error

    usuario = await auth_service.buscar_por_id(db, usuario_id)
    if usuario is None:
        raise creds_error
    return usuario
