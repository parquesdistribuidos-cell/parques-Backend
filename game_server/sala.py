"""Sala de juego con soporte para bots."""
import asyncio
import random
import string
from typing import Dict, List, Optional
from .motor.constantes import COLORES

ESTADO_ESPERANDO = "ESPERANDO"
ESTADO_EN_PARTIDA = "EN_PARTIDA"
ESTADO_TERMINADA = "TERMINADA"


class JugadorEnSala:
    def __init__(self, usuario_id: int, username: str, websocket, es_bot: bool = False):
        self.usuario_id = usuario_id
        self.username = username
        self.websocket = websocket
        self.color: Optional[str] = None
        self.listo: bool = False
        self.es_bot: bool = es_bot
        self.jugador_motor = None
        self.desconectado: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.usuario_id,
            "username": self.username,
            "color": self.color,
            "listo": self.listo,
            "es_bot": self.es_bot,
        }


class Sala:
    def __init__(self, pin: str, nombre: str, creador_id: int):
        self.pin = pin
        self.nombre = nombre
        self.creador_id = creador_id
        self.estado = ESTADO_ESPERANDO
        self.jugadores: List[JugadorEnSala] = []
        self.lock = asyncio.Lock()
        self.max_jugadores = 4

    def esta_llena(self) -> bool:
        return len(self.jugadores) >= self.max_jugadores

    def colores_disponibles(self) -> List[str]:
        tomados = {j.color for j in self.jugadores if j.color}
        return [c for c in COLORES if c not in tomados]

    def buscar_jugador(self, usuario_id: int) -> Optional[JugadorEnSala]:
        return next((j for j in self.jugadores if j.usuario_id == usuario_id), None)

    def todos_listos(self) -> bool:
        humanos = [j for j in self.jugadores if not j.es_bot]
        if len(humanos) < 1:
            return False
        total = len(self.jugadores)
        if total < 2:
            return False
        return all(j.listo and j.color for j in self.jugadores)

    def to_dict(self) -> dict:
        return {
            "pin": self.pin,
            "nombre": self.nombre,
            "estado": self.estado,
            "jugadores": [j.to_dict() for j in self.jugadores],
            "colores_disponibles": self.colores_disponibles(),
        }


def generar_pin(existentes: set) -> str:
    while True:
        pin = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if pin not in existentes:
            return pin
