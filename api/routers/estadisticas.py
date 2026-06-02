"""Estadísticas y ranking."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from api.models import Partida, Participacion, Usuario
from shared.db import get_db

router = APIRouter(prefix="/estadisticas", tags=["Estadísticas"])

@router.get("/ranking")
async def ranking(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Usuario.username,
            func.count(Partida.id).label("partidas_jugadas"),
            func.sum(
                cast(Partida.ganador_id == Usuario.id, Integer)
            ).label("victorias"),
        )
        .join(Participacion, Participacion.usuario_id == Usuario.id)
        .join(Partida, Partida.id == Participacion.partida_id)
        .group_by(Usuario.id, Usuario.username)
        .order_by(func.count(Partida.id).desc())
        .limit(20)
    )
    rows = result.all()
    return {"ranking": [{"username": r.username, "partidas": r.partidas_jugadas} for r in rows]}

@router.get("/probabilidad/{usuario_id}")
async def probabilidad(usuario_id: int, db: AsyncSession = Depends(get_db)):
    total = await db.execute(
        select(func.count()).select_from(Participacion).where(Participacion.usuario_id == usuario_id)
    )
    victorias = await db.execute(
        select(func.count()).select_from(Partida).where(Partida.ganador_id == usuario_id)
    )
    t = total.scalar() or 0
    v = victorias.scalar() or 0
    prob = round((v + 1) / (t + 4) * 100, 1)  # ajuste bayesiano
    return {"usuario_id": usuario_id, "partidas": t, "victorias": v, "probabilidad_pct": prob}
