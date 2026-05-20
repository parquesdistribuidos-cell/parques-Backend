"""Router de usuarios."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import usuario_actual
from api.models import Usuario, Participacion, Partida
from api.schemas.auth import UsuarioResponse
from shared.db import get_db

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

@router.get("/me", response_model=UsuarioResponse)
async def perfil_actual(usuario: Usuario = Depends(usuario_actual)):
    return usuario

@router.get("/me/partidas")
async def mis_partidas(usuario: Usuario = Depends(usuario_actual), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Partida, Participacion)
        .join(Participacion, Participacion.partida_id == Partida.id)
        .where(Participacion.usuario_id == usuario.id)
        .order_by(Partida.fecha_inicio.desc())
        .limit(20)
    )
    rows = result.all()
    return {"partidas": [
        {
            "id": p.id,
            "fecha": str(p.fecha_inicio),
            "estado": p.estado,
            "gane": p.ganador_id == usuario.id,
            "color": part.color,
        }
        for p, part in rows
    ]}
