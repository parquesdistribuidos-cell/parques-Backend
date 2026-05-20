"""Modelo de Participación (un usuario en una partida)."""

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Participacion(Base):
    __tablename__ = "participaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    partida_id: Mapped[int] = mapped_column(ForeignKey("partidas.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False)
    posicion_final: Mapped[int] = mapped_column(Integer, default=0)
    fichas_capturadas: Mapped[int] = mapped_column(Integer, default=0)
    movimientos_totales: Mapped[int] = mapped_column(Integer, default=0)
