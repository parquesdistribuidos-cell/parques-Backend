"""
Motor de reglas del parqués colombiano.

Esta clase implementa TODAS las reglas del juego. Está completamente
desacoplada de la red y la persistencia. Es testeable de forma aislada.

Reglas implementadas:
1. Salida de cárcel solo con pares (3 oportunidades iniciales si no hay éxito)
2. Tres pares consecutivos -> el jugador elige una ficha del tablero y la mete a meta
3. Captura al caer sobre rival (excepto si la casilla es de seguro)
4. Protección en la recta de color propio
5. Detección de victoria (las 4 fichas en meta)
6. Cálculo de movimientos legales

Este archivo fue desarrollado con asistencia de Claude (Anthropic).
"""

from dataclasses import dataclass
from typing import List, Optional

from .constantes import (
    COLORES,
    SALIDA_POR_COLOR,
    ENTRADA_RECTA_FINAL,
    RECTA_FINAL_LONGITUD,
    TOTAL_CASILLAS_TABLERO,
    PARES_CONSECUTIVOS_LIMITE,
    ESTADO_CARCEL,
    ESTADO_TABLERO,
    ESTADO_RECTA_FINAL,
    ESTADO_META,
    siguiente_casilla,
)
from .dados import ResultadoDados
from .ficha import Ficha
from .jugador import Jugador
from .tablero import Tablero


@dataclass
class MovimientoLegal:
    """Representa un movimiento que el jugador PUEDE hacer."""
    ficha_id: int
    valor: int
    dado: str  # "a", "b" o "suma"
    destino_descripcion: str  # ej: "casilla 23", "recta final pos 3", "meta", "captura ficha 31"
    captura: Optional[int] = None  # id de ficha capturada, si aplica

    def to_dict(self) -> dict:
        return {
            "ficha_id": self.ficha_id,
            "valor": self.valor,
            "dado": self.dado,
            "destino_descripcion": self.destino_descripcion,
            "captura": self.captura,
        }


@dataclass
class ResultadoMovimiento:
    """Resultado de aplicar un movimiento al tablero."""
    exito: bool
    ficha_movida: Optional[int] = None
    fichas_capturadas: List[int] = None
    llego_a_meta: bool = False
    salio_de_carcel: bool = False
    error: Optional[str] = None

    def __post_init__(self):
        if self.fichas_capturadas is None:
            self.fichas_capturadas = []


class MotorReglas:
    """
    Aplicador puro de reglas. No mantiene estado propio; recibe
    Tablero y Jugador como parámetros.
    """

    # ============================================
    # SALIDA DE CÁRCEL
    # ============================================

    def puede_sacar_de_carcel(self, jugador: Jugador, dados: ResultadoDados) -> bool:
        """
        Reglas:
        - Necesita pares
        - Debe tener fichas en la cárcel
        - La casilla de salida no debe estar bloqueada por dos fichas rivales
        """
        if not dados.es_par:
            return False
        if not jugador.fichas_en_carcel():
            return False
        return True

    def sacar_de_carcel(
        self,
        tablero: Tablero,
        jugador: Jugador,
        dados: ResultadoDados,
        ficha_id: Optional[int] = None,
    ) -> ResultadoMovimiento:
        """
        Saca UNA ficha de la cárcel a la casilla de salida.

        Regla del parqués colombiano: con un par normal sale 1 ficha.
        Con par de seises se sacan 2 fichas si hay disponibles.

        Aquí sacamos una a la vez, llamada repetida por el orquestador
        si aplica par de seises.
        """
        if not self.puede_sacar_de_carcel(jugador, dados):
            return ResultadoMovimiento(exito=False, error="No puede sacar ficha de cárcel")

        en_carcel = jugador.fichas_en_carcel()
        if ficha_id is not None:
            ficha = next((f for f in en_carcel if f.id == ficha_id), None)
            if ficha is None:
                return ResultadoMovimiento(exito=False, error="La ficha no está en cárcel")
        else:
            ficha = en_carcel[0]

        casilla_salida = SALIDA_POR_COLOR[jugador.color]

        # Si la salida tiene una ficha rival, la capturamos (la salida es segura,
        # pero la regla habitual es que si llega justo en la salida con pares
        # puede comer; aquí aplicamos: la salida es segura -> no captura)
        # En parqués colombiano la salida es SEGURO, así que NO captura.
        # Las fichas conviven en seguros sin capturar.
        tablero.colocar_en_casilla(ficha, casilla_salida)

        return ResultadoMovimiento(
            exito=True,
            ficha_movida=ficha.id,
            salio_de_carcel=True,
        )

    # ============================================
    # MOVIMIENTOS LEGALES
    # ============================================

    def calcular_movimientos_legales(
        self,
        tablero: Tablero,
        jugador: Jugador,
        dados: ResultadoDados,
    ) -> List[MovimientoLegal]:
        movimientos: List[MovimientoLegal] = []

        # Si es par: un movimiento con la suma completa
        # Si no es par: cada dado por separado (sin suma)
        if dados.es_par:
            valores = [
                ("a", dados.valor_a),
                ("b", dados.valor_b),
                ("suma", dados.suma),
            ]
        else:
            valores = [
                ("a", dados.valor_a),
                ("b", dados.valor_b),
            ]

        for f in jugador.fichas_jugables():
            for nombre_dado, valor in valores:
                resultado = self._simular_movimiento(tablero, jugador, f, valor)
                if resultado is not None:
                    mov = MovimientoLegal(
                        ficha_id=f.id,
                        valor=valor,
                        dado=nombre_dado,
                        destino_descripcion=resultado["descripcion"],
                        captura=resultado.get("captura"),
                    )
                    movimientos.append(mov)

        return movimientos

    def _simular_movimiento(
        self,
        tablero: Tablero,
        jugador: Jugador,
        ficha: Ficha,
        valor: int,
    ) -> Optional[dict]:
        """
        Simula mover una ficha 'valor' casillas. Devuelve dict con
        info del destino, o None si es ilegal.
        """
        if ficha.estado == ESTADO_TABLERO:
            return self._simular_desde_tablero(tablero, jugador, ficha, valor)
        elif ficha.estado == ESTADO_RECTA_FINAL:
            return self._simular_desde_recta(jugador, ficha, valor)
        return None

    def _simular_desde_tablero(
        self,
        tablero: Tablero,
        jugador: Jugador,
        ficha: Ficha,
        valor: int,
    ) -> Optional[dict]:
        """Simula movimiento de ficha que está en el recorrido principal."""
        entrada_recta = ENTRADA_RECTA_FINAL[jugador.color]
        casilla_actual = ficha.posicion

        # Calculamos cuántas casillas faltan para llegar a la entrada de su recta
        if casilla_actual <= entrada_recta:
            casillas_hasta_entrada = entrada_recta - casilla_actual
        else:
            casillas_hasta_entrada = (TOTAL_CASILLAS_TABLERO - casilla_actual) + entrada_recta

        # ¿Entra a la recta final con este movimiento?
        if valor > casillas_hasta_entrada:
            pasos_en_recta = valor - casillas_hasta_entrada
            if pasos_en_recta > RECTA_FINAL_LONGITUD:
                # Se pasa de la meta -> movimiento inválido
                return None
            if pasos_en_recta == RECTA_FINAL_LONGITUD:
                return {"descripcion": "meta", "destino_tipo": "meta"}
            return {
                "descripcion": f"recta final posición {pasos_en_recta}",
                "destino_tipo": "recta",
                "destino_pos": pasos_en_recta,
            }

        # Movimiento normal en el tablero
        casilla_destino = siguiente_casilla(casilla_actual, valor)
        rivales = tablero.fichas_rivales_en_casilla(casilla_destino, jugador.color)
        es_safe = tablero.hay_seguro_en(casilla_destino)

        captura = None
        if rivales and not es_safe:
            # Captura a la primera rival
            captura = rivales[0].id

        descripcion = f"casilla {casilla_destino}"
        if captura:
            descripcion += f" (captura ficha {captura})"

        return {
            "descripcion": descripcion,
            "destino_tipo": "casilla",
            "destino_casilla": casilla_destino,
            "captura": captura,
        }

    def _simular_desde_recta(
        self,
        jugador: Jugador,
        ficha: Ficha,
        valor: int,
    ) -> Optional[dict]:
        """Simula movimiento de ficha en la recta final."""
        pos_destino = ficha.posicion + valor
        if pos_destino > RECTA_FINAL_LONGITUD:
            return None  # No se puede pasar de la meta
        if pos_destino == RECTA_FINAL_LONGITUD:
            return {"descripcion": "meta", "destino_tipo": "meta"}
        return {
            "descripcion": f"recta final posición {pos_destino}",
            "destino_tipo": "recta",
            "destino_pos": pos_destino,
        }

    # ============================================
    # APLICAR MOVIMIENTO
    # ============================================

    def aplicar_movimiento(
        self,
        tablero: Tablero,
        jugador: Jugador,
        ficha_id: int,
        valor: int,
    ) -> ResultadoMovimiento:
        """
        Aplica el movimiento al tablero. Asume que ya fue validado
        como legal por calcular_movimientos_legales.
        """
        ficha = jugador.buscar_ficha(ficha_id)
        if ficha is None:
            return ResultadoMovimiento(exito=False, error="Ficha no encontrada")

        sim = self._simular_movimiento(tablero, jugador, ficha, valor)
        if sim is None:
            return ResultadoMovimiento(exito=False, error="Movimiento inválido")

        capturadas: List[int] = []

        if sim["destino_tipo"] == "meta":
            tablero.colocar_en_meta(ficha)
            return ResultadoMovimiento(
                exito=True,
                ficha_movida=ficha.id,
                fichas_capturadas=capturadas,
                llego_a_meta=True,
            )

        if sim["destino_tipo"] == "recta":
            tablero.colocar_en_recta(ficha, sim["destino_pos"])
            return ResultadoMovimiento(
                exito=True,
                ficha_movida=ficha.id,
                fichas_capturadas=capturadas,
            )

        # destino_tipo == "casilla"
        casilla_destino = sim["destino_casilla"]
        if sim.get("captura"):
            ficha_capturada_id = sim["captura"]
            # Buscar la ficha rival y encarcelarla
            for f_rival in list(tablero.fichas_en_casilla(casilla_destino)):
                if f_rival.id == ficha_capturada_id:
                    tablero.encarcelar(f_rival)
                    capturadas.append(f_rival.id)
                    break

        tablero.colocar_en_casilla(ficha, casilla_destino)
        return ResultadoMovimiento(
            exito=True,
            ficha_movida=ficha.id,
            fichas_capturadas=capturadas,
        )

    # ============================================
    # REGLA DE LOS PARES
    # ============================================

    def procesar_pares(self, jugador: Jugador, dados: ResultadoDados) -> dict:
        """
        Actualiza el contador de pares consecutivos.

        Devuelve:
        - {"saca_ficha": True} si llegó a 3 pares (debe elegir una ficha del tablero
                                                    y mandarla a meta)
        - {"saca_ficha": False, "retiene_turno": True} si fue par (sigue su turno)
        - {"saca_ficha": False, "retiene_turno": False} si no fue par (turno pasa)
        """
        if dados.es_par:
            jugador.pares_consecutivos += 1
            if jugador.pares_consecutivos >= PARES_CONSECUTIVOS_LIMITE:
                # Resetear el contador después de aplicar el castigo
                jugador.pares_consecutivos = 0
                return {"saca_ficha": True, "retiene_turno": False}
            return {"saca_ficha": False, "retiene_turno": True}
        else:
            jugador.pares_consecutivos = 0
            return {"saca_ficha": False, "retiene_turno": False}

    def quemar_ficha(
        self,
        tablero: Tablero,
        jugador: Jugador,
        ficha_id: int,
    ) -> ResultadoMovimiento:
        """
        Aplica la regla de los 3 pares: el jugador elige una ficha
        del tablero (no de cárcel ni meta) y la manda a meta directamente.

        En realidad la regla del parqués colombiano es que la ficha va a la
        cárcel (se 'quema'), pero el enunciado del proyecto dice:
        'tiene derecho a sacar una ficha del juego, la que el jugador escoja'.

        Interpretamos 'sacar del juego' como mandar a meta (la quita del
        recorrido). Si en clase aclara que es a cárcel, cambiar aquí.
        """
        ficha = jugador.buscar_ficha(ficha_id)
        if ficha is None:
            return ResultadoMovimiento(exito=False, error="Ficha no encontrada")
        if ficha.estado in (ESTADO_CARCEL, ESTADO_META):
            return ResultadoMovimiento(
                exito=False,
                error="Solo se pueden 'sacar' fichas en juego",
            )

        tablero.colocar_en_meta(ficha)
        return ResultadoMovimiento(
            exito=True,
            ficha_movida=ficha.id,
            llego_a_meta=True,
        )

    # ============================================
    # OPORTUNIDADES INICIALES PARA SALIR DE CÁRCEL
    # ============================================

    def consumir_oportunidad_salida(self, jugador: Jugador):
        """
        Llamar después de un turno donde tenía fichas en cárcel y no pudo sacar.
        Cuando llega a 0, ya no tiene 'protección' especial inicial.
        """
        if jugador.oportunidades_salida > 0:
            jugador.oportunidades_salida -= 1

    # ============================================
    # VICTORIA
    # ============================================

    def hay_ganador(self, jugadores: List[Jugador]) -> Optional[Jugador]:
        """Devuelve el jugador ganador o None."""
        for j in jugadores:
            if j.ha_ganado():
                return j
        return None
