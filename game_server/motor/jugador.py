"""
Jugador del juego de parqués.

Mantiene:
- Identidad (id_usuario, username)
- Color asignado
- Sus 4 fichas
- Contadores: pares consecutivos, oportunidades para salir de cárcel
"""

from dataclasses import dataclass, field
from typing import List

from .constantes import (
    FICHAS_POR_JUGADOR,
    OPORTUNIDADES_SALIDA_INICIAL,
    ESTADO_CARCEL,
    ESTADO_META,
)
from .ficha import Ficha


@dataclass
class Jugador:
    id: int
    username: str
    color: str
    fichas: List[Ficha] = field(default_factory=list)
    pares_consecutivos: int = 0
    oportunidades_salida: int = OPORTUNIDADES_SALIDA_INICIAL
    desconectado: bool = False
    es_bot: bool = False

    def __post_init__(self):
        """Si no se pasaron fichas, crea 4 en la cárcel."""
        if not self.fichas:
            self.fichas = [
                Ficha(id=self.id * 10 + i, color=self.color)
                for i in range(1, FICHAS_POR_JUGADOR + 1)
            ]

    def fichas_en_carcel(self) -> List[Ficha]:
        return [f for f in self.fichas if f.estado == ESTADO_CARCEL]

    def fichas_en_meta(self) -> List[Ficha]:
        return [f for f in self.fichas if f.estado == ESTADO_META]

    def fichas_jugables(self) -> List[Ficha]:
        """Fichas que se pueden mover (no están en meta ni cárcel)."""
        return [f for f in self.fichas if f.estado not in (ESTADO_CARCEL, ESTADO_META)]

    def ha_ganado(self) -> bool:
        """Un jugador gana cuando todas sus 4 fichas llegan a la meta."""
        return len(self.fichas_en_meta()) == FICHAS_POR_JUGADOR

    def buscar_ficha(self, ficha_id: int) -> Ficha | None:
        for f in self.fichas:
            if f.id == ficha_id:
                return f
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "color": self.color,
            "fichas": [f.to_dict() for f in self.fichas],
            "pares_consecutivos": self.pares_consecutivos,
            "oportunidades_salida": self.oportunidades_salida,
            "desconectado": self.desconectado,
            "es_bot": self.es_bot,
        }
