"""Modelo de Jugada individual (para auditoría)."""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Jugada(Base):
    __tablename__ = "jugadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    partida_id: Mapped[int] = mapped_column(ForeignKey("partidas.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    turno_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    dado_a: Mapped[int] = mapped_column(Integer, nullable=False)
    dado_b: Mapped[int] = mapped_column(Integer, nullable=False)
    ficha_movida: Mapped[int] = mapped_column(Integer, nullable=False)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
