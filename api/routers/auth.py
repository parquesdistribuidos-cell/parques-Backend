"""Router de autenticación."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UsuarioResponse
from api.services import auth_service
from shared.auth_jwt import crear_token
from shared.db import get_db


router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def register(datos: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Crea un usuario nuevo."""
    existente_user = await auth_service.buscar_por_username(db, datos.username)
    if existente_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya existe",
        )
    existente_mail = await auth_service.buscar_por_email(db, datos.email)
    if existente_mail:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado",
        )

    usuario = await auth_service.crear_usuario(db, datos)
    return usuario


@router.post("/login", response_model=TokenResponse)
async def login(datos: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Inicia sesión y devuelve un JWT."""
    usuario = await auth_service.autenticar(db, datos.username, datos.password)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    token = crear_token(usuario_id=usuario.id, username=usuario.username)
    return TokenResponse(
        access_token=token,
        usuario_id=usuario.id,
        username=usuario.username,
    )
