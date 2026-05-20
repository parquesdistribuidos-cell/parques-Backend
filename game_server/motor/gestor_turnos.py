"""
Gestor de turnos del juego.

Decide quién juega, valida que solo el jugador en turno actúe,
mantiene el orden de rotación.
"""

import asyncio
from typing import Dict, List, Optional

from .jugador import Jugador


class GestorTurnos:
    """
    Maneja el orden y la rotación de turnos.

    Cumple con la 'semaforización' del enunciado: un asyncio.Lock asegura
    que solo un movimiento se procese a la vez.
    """

    def __init__(self):
        self.orden_jugadores: List[int] = []  # IDs en orden
        self.indice_actual: int = 0
        self.tiradas_iniciales: Dict[int, int] = {}  # para determinar primer turno
        self.lock = asyncio.Lock()
        self.iniciado: bool = False

    def registrar_tirada_inicial(self, jugador_id: int, valor: int):
        """Cada jugador tira una vez al inicio para decidir primer turno."""
        self.tiradas_iniciales[jugador_id] = valor

    def determinar_primer_turno(self, jugadores: List[Jugador]):
        """
        El jugador con el valor más alto en la tirada inicial empieza.
        En caso de empate gana el que aparece primero en la lista.
        """
        if not self.tiradas_iniciales:
            raise ValueError("Faltan tiradas iniciales")

        # Ordenar IDs por tirada inicial descendente
        ids_ordenados = sorted(
            self.tiradas_iniciales.keys(),
            key=lambda jid: -self.tiradas_iniciales[jid],
        )
        # El orden de turnos sigue ese ranking
        self.orden_jugadores = ids_ordenados
        # Pero verificamos que todos los IDs estén en jugadores activos
        ids_activos = {j.id for j in jugadores}
        self.orden_jugadores = [jid for jid in ids_ordenados if jid in ids_activos]
        self.indice_actual = 0
        self.iniciado = True

    def jugador_actual_id(self) -> Optional[int]:
        if not self.iniciado or not self.orden_jugadores:
            return None
        return self.orden_jugadores[self.indice_actual]

    def es_turno_de(self, jugador_id: int) -> bool:
        return self.jugador_actual_id() == jugador_id

    def avanzar_turno(self):
        """Pasa al siguiente jugador (saltando desconectados si aplica)."""
        if not self.orden_jugadores:
            return
        self.indice_actual = (self.indice_actual + 1) % len(self.orden_jugadores)

    def remover_jugador(self, jugador_id: int):
        """Cuando un jugador abandona la partida."""
        if jugador_id not in self.orden_jugadores:
            return
        idx_removido = self.orden_jugadores.index(jugador_id)
        self.orden_jugadores.remove(jugador_id)
        # Ajustar indice si era después del removido
        if idx_removido < self.indice_actual:
            self.indice_actual -= 1
        if self.orden_jugadores:
            self.indice_actual = self.indice_actual % len(self.orden_jugadores)

    def to_dict(self) -> dict:
        return {
            "orden_jugadores": self.orden_jugadores,
            "jugador_actual": self.jugador_actual_id(),
            "iniciado": self.iniciado,
        }
