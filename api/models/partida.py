"""Modelo de Partida (tabla `partidas`)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Partida(Base):
    __tablename__ = "partidas"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    fecha_fin: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ganador_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    duracion_seg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="en_curso")  # en_curso | terminada | abandonada
