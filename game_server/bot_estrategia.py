"""
Estrategia heurística del bot jugador.

Prioridades (de mayor a menor):
1. Si puede llegar a meta -> va a meta
2. Si puede capturar rival -> captura
3. Si puede entrar a recta final -> entra
4. Si puede sacar de cárcel -> saca (se maneja aparte)
5. Mover la ficha más adelantada
"""
from typing import List
from .motor.reglas import MovimientoLegal
from .motor.tablero import Tablero
from .motor.jugador import Jugador


def elegir_movimiento_bot(
    movimientos: List[MovimientoLegal],
    tablero: Tablero,
    jugador: Jugador,
) -> MovimientoLegal:
    if not movimientos:
        raise ValueError("No hay movimientos disponibles")

    # 1. Ir a meta
    a_meta = [m for m in movimientos if "meta" in m.destino_descripcion.lower()]
    if a_meta:
        return a_meta[0]

    # 2. Capturar rival
    con_captura = [m for m in movimientos if m.captura is not None]
    if con_captura:
        return con_captura[0]

    # 3. Avanzar en recta final
    a_recta = [m for m in movimientos if "recta" in m.destino_descripcion.lower()]
    if a_recta:
        return sorted(a_recta, key=lambda m: m.valor, reverse=True)[0]

    # 4. Mover la ficha con mayor posición (más adelantada)
    from .motor.constantes import ESTADO_TABLERO
    fichas_tablero = [
        m for m in movimientos
        if jugador.buscar_ficha(m.ficha_id) and
        jugador.buscar_ficha(m.ficha_id).estado == ESTADO_TABLERO
    ]
    if fichas_tablero:
        return sorted(fichas_tablero, key=lambda m: (
            jugador.buscar_ficha(m.ficha_id).posicion + m.valor
        ), reverse=True)[0]

    return movimientos[0]
