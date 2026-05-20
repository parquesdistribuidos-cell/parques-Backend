"""
Ficha del juego de parqués.

Cada jugador tiene 4 fichas. Una ficha tiene:
- Un ID único (formato: jugador_id * 10 + indice, ej: 11, 12, 13, 14 para jugador 1)
- Un color (heredado del jugador dueño)
- Un estado (cárcel, tablero, recta final, meta)
- Una posición (significado depende del estado)

Este archivo fue desarrollado con asistencia de Claude (Anthropic).
"""

from dataclasses import dataclass
from .constantes import ESTADO_CARCEL


@dataclass
class Ficha:
    id: int
    color: str
    estado: str = ESTADO_CARCEL
    posicion: int = 0  # En cárcel = 0; en tablero = casilla 1-68; en recta = 1-8

    @property
    def jugador_id(self) -> int:
        """El ID del jugador dueño se extrae del ID de la ficha (ej: 13 -> jugador 1)."""
        return self.id // 10

    def __repr__(self) -> str:
        return f"Ficha(id={self.id}, color={self.color}, estado={self.estado}, pos={self.posicion})"

    def to_dict(self) -> dict:
        """Serialización para enviar por WebSocket."""
        return {
            "id": self.id,
            "color": self.color,
            "estado": self.estado,
            "posicion": self.posicion,
        }
