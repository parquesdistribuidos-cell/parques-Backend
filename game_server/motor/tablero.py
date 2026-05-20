"""
Tablero del juego de parqués.

Mantiene el estado completo del tablero. Es solo ESTADO: las reglas viven
en MotorReglas. Esta clase ofrece consultas y mutaciones básicas.

Estructura:
- casillas: dict[int, list[Ficha]]  -- las 68 casillas del recorrido principal
- carceles: dict[str, list[Ficha]]  -- una por color, lista de fichas presas
- rectas_finales: dict[str, dict[int, list[Ficha]]]  -- recta por color, 8 casillas
- meta: dict[str, list[Ficha]]  -- fichas terminadas por color

Este archivo fue desarrollado con asistencia de Claude (Anthropic).
"""

from typing import Dict, List, Optional

from .constantes import (
    COLORES,
    TOTAL_CASILLAS_TABLERO,
    RECTA_FINAL_LONGITUD,
    ESTADO_CARCEL,
    ESTADO_TABLERO,
    ESTADO_RECTA_FINAL,
    ESTADO_META,
    es_seguro,
)
from .ficha import Ficha


class Tablero:
    def __init__(self):
        # Las 68 casillas del recorrido principal
        self.casillas: Dict[int, List[Ficha]] = {
            i: [] for i in range(1, TOTAL_CASILLAS_TABLERO + 1)
        }

        # Cárceles por color
        self.carceles: Dict[str, List[Ficha]] = {color: [] for color in COLORES}

        # Rectas finales por color (8 casillas cada una)
        self.rectas_finales: Dict[str, Dict[int, List[Ficha]]] = {
            color: {i: [] for i in range(1, RECTA_FINAL_LONGITUD + 1)}
            for color in COLORES
        }

        # Fichas en meta por color
        self.meta: Dict[str, List[Ficha]] = {color: [] for color in COLORES}

    # ============================================
    # Métodos para colocar fichas
    # ============================================

    def encarcelar(self, ficha: Ficha):
        """Coloca una ficha en su cárcel correspondiente."""
        self._sacar_de_donde_este(ficha)
        ficha.estado = ESTADO_CARCEL
        ficha.posicion = 0
        self.carceles[ficha.color].append(ficha)

    def colocar_en_casilla(self, ficha: Ficha, casilla: int):
        """Coloca una ficha en una casilla del recorrido principal."""
        if not (1 <= casilla <= TOTAL_CASILLAS_TABLERO):
            raise ValueError(f"Casilla inválida: {casilla}")
        self._sacar_de_donde_este(ficha)
        ficha.estado = ESTADO_TABLERO
        ficha.posicion = casilla
        self.casillas[casilla].append(ficha)

    def colocar_en_recta(self, ficha: Ficha, posicion: int):
        """Coloca una ficha en una casilla de su recta final (1-8)."""
        if not (1 <= posicion <= RECTA_FINAL_LONGITUD):
            raise ValueError(f"Posición de recta final inválida: {posicion}")
        self._sacar_de_donde_este(ficha)
        ficha.estado = ESTADO_RECTA_FINAL
        ficha.posicion = posicion
        self.rectas_finales[ficha.color][posicion].append(ficha)

    def colocar_en_meta(self, ficha: Ficha):
        """Marca una ficha como terminada."""
        self._sacar_de_donde_este(ficha)
        ficha.estado = ESTADO_META
        ficha.posicion = 0
        self.meta[ficha.color].append(ficha)

    def _sacar_de_donde_este(self, ficha: Ficha):
        """Quita la ficha de su ubicación actual (cualquiera que sea)."""
        if ficha.estado == ESTADO_CARCEL:
            if ficha in self.carceles[ficha.color]:
                self.carceles[ficha.color].remove(ficha)
        elif ficha.estado == ESTADO_TABLERO:
            if ficha in self.casillas[ficha.posicion]:
                self.casillas[ficha.posicion].remove(ficha)
        elif ficha.estado == ESTADO_RECTA_FINAL:
            recta = self.rectas_finales[ficha.color]
            if ficha in recta[ficha.posicion]:
                recta[ficha.posicion].remove(ficha)
        elif ficha.estado == ESTADO_META:
            if ficha in self.meta[ficha.color]:
                self.meta[ficha.color].remove(ficha)

    # ============================================
    # Consultas
    # ============================================

    def fichas_en_casilla(self, casilla: int) -> List[Ficha]:
        """Fichas actualmente en una casilla del recorrido principal."""
        return list(self.casillas.get(casilla, []))

    def fichas_rivales_en_casilla(self, casilla: int, color_propio: str) -> List[Ficha]:
        """Fichas en la casilla que NO son del color dado."""
        return [f for f in self.fichas_en_casilla(casilla) if f.color != color_propio]

    def hay_seguro_en(self, casilla: int) -> bool:
        """Indica si la casilla es de seguro."""
        return es_seguro(casilla)

    def get_ficha_por_id(self, ficha_id: int) -> Optional[Ficha]:
        """Busca una ficha por ID en cualquier parte del tablero."""
        # Buscar en cárceles
        for color in COLORES:
            for f in self.carceles[color]:
                if f.id == ficha_id:
                    return f
            for f in self.meta[color]:
                if f.id == ficha_id:
                    return f
            for casilla_fichas in self.rectas_finales[color].values():
                for f in casilla_fichas:
                    if f.id == ficha_id:
                        return f
        # Buscar en el recorrido principal
        for casilla_fichas in self.casillas.values():
            for f in casilla_fichas:
                if f.id == ficha_id:
                    return f
        return None

    # ============================================
    # Serialización
    # ============================================

    def to_dict(self) -> dict:
        """Estado completo del tablero para enviar por WebSocket."""
        return {
            "casillas": {
                str(num): [f.to_dict() for f in fichas]
                for num, fichas in self.casillas.items() if fichas
            },
            "carceles": {
                color: [f.to_dict() for f in fichas]
                for color, fichas in self.carceles.items()
            },
            "rectas_finales": {
                color: {
                    str(pos): [f.to_dict() for f in fichas]
                    for pos, fichas in casillas.items() if fichas
                }
                for color, casillas in self.rectas_finales.items()
            },
            "meta": {
                color: [f.to_dict() for f in fichas]
                for color, fichas in self.meta.items()
            },
        }
