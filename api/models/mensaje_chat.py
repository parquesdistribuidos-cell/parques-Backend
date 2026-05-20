"""Modelo de Mensaje de Chat."""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class MensajeChat(Base):
    __tablename__ = "mensajes_chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    partida_id: Mapped[int] = mapped_column(ForeignKey("partidas.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
