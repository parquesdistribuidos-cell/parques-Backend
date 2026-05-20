"""Servicios de autenticación."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Usuario
from api.schemas.auth import RegisterRequest
from shared.auth_jwt import hash_password, verify_password


async def crear_usuario(db: AsyncSession, datos: RegisterRequest) -> Usuario:
    """Crea un usuario nuevo en la DB."""
    usuario = Usuario(
        username=datos.username,
        email=datos.email,
        password_hash=hash_password(datos.password),
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


async def buscar_por_username(db: AsyncSession, username: str) -> Optional[Usuario]:
    result = await db.execute(select(Usuario).where(Usuario.username == username))
    return result.scalar_one_or_none()


async def buscar_por_email(db: AsyncSession, email: str) -> Optional[Usuario]:
    result = await db.execute(select(Usuario).where(Usuario.email == email))
    return result.scalar_one_or_none()


async def buscar_por_id(db: AsyncSession, usuario_id: int) -> Optional[Usuario]:
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    return result.scalar_one_or_none()


async def autenticar(db: AsyncSession, username: str, password: str) -> Optional[Usuario]:
    """Verifica credenciales. Retorna el usuario si son correctas."""
    usuario = await buscar_por_username(db, username)
    if usuario is None:
        return None
    if not verify_password(password, usuario.password_hash):
        return None
    return usuario
