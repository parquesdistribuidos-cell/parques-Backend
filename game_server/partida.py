"""
Orquestador de una partida completa de parqués.

Conecta el motor de reglas con el Game Server WebSocket.
Maneja: tirada inicial, turnos, dados, movimientos, chat, victoria.
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional

from .motor.constantes import COLORES
from .motor.dados import Dados, ResultadoDados
from .motor.gestor_turnos import GestorTurnos
from .motor.jugador import Jugador
from .motor.reglas import MotorReglas
from .motor.tablero import Tablero
from .protocolo import construir, error
from .sala import JugadorEnSala

logger = logging.getLogger("game_server.partida")


async def _enviar(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        pass


async def _broadcast(jugadores: List[JugadorEnSala], msg: str, excluir_id: int = None):
    tareas = [
        _enviar(j.websocket, msg)
        for j in jugadores
        if j.usuario_id != excluir_id
    ]
    if tareas:
        await asyncio.gather(*tareas, return_exceptions=True)


class Partida:
    """
    Ciclo de vida de una partida completa.
    Se instancia desde la Sala cuando todos los jugadores están listos.
    """

    def __init__(self, jugadores_sala: List[JugadorEnSala], partida_id: int = 0):
        self.partida_id = partida_id
        self.jugadores_sala = jugadores_sala

        # Motor
        self.tablero = Tablero()
        self.dados = Dados()
        self.motor = MotorReglas()
        self.gestor = GestorTurnos()

        # Crear jugadores del motor
        self.jugadores: Dict[int, Jugador] = {}
        for js in jugadores_sala:
            jug = Jugador(id=js.usuario_id, username=js.username, color=js.color, es_bot=js.es_bot)
            js.jugador_motor = jug
            self.jugadores[js.usuario_id] = jug
            # Inicializar fichas en cárcel
            for f in jug.fichas:
                self.tablero.encarcelar(f)

        # Estado
        self.turno_lock = asyncio.Lock()
        self.dados_actuales: Optional[ResultadoDados] = None
        self.turno_numero: int = 0
        self.activa: bool = False

        # Para esperar decisión del jugador
        self._esperando_movimiento: Optional[asyncio.Event] = None
        self._movimiento_recibido: Optional[dict] = None

        # Para Berkeley
        self._berkeley_respuestas: Dict[int, float] = {}

    # ============================================
    # Arranque
    # ============================================

    async def iniciar(self):
        """Ejecuta la secuencia completa de inicio de partida."""
        self.activa = True
        logger.info(f"Partida {self.partida_id} iniciando con {len(self.jugadores)} jugadores")

        # 1. Berkeley
        await self._ejecutar_berkeley()

        # 2. Tirada inicial para determinar primer turno
        await self._tirada_inicial()

        # 3. Loop principal del juego
        await self._loop_principal()

    async def _ejecutar_berkeley(self):
        from .berkeley import Berkeley
        bk = Berkeley()
        offsets = await bk.sincronizar(self.jugadores_sala)
        logger.info(f"Berkeley offsets: {offsets}")

    async def _tirada_inicial(self):
        """Cada jugador tira un dado para determinar quién empieza."""
        await _broadcast(
            self.jugadores_sala,
            construir("TURNO_ASIGNADO", {
                "fase": "tirada_inicial",
                "mensaje": "Todos lanzan para ver quién empieza. Espera...",
                "jugador_id": None,
            })
        )
        await asyncio.sleep(0.5)

        tiradas = {}
        for js in self.jugadores_sala:
            r = self.dados.lanzar()
            valor = r.valor_a + r.valor_b
            tiradas[js.usuario_id] = valor
            self.gestor.registrar_tirada_inicial(js.usuario_id, valor)
            await _broadcast(
                self.jugadores_sala,
                construir("DADOS_RESULTADO", {
                    "fase": "tirada_inicial",
                    "jugador_id": js.usuario_id,
                    "username": js.username,
                    "dado_a": r.valor_a,
                    "dado_b": r.valor_b,
                    "suma": valor,
                })
            )
            await asyncio.sleep(0.3)

        self.gestor.determinar_primer_turno(list(self.jugadores.values()))

        primer = self.gestor.jugador_actual_id()
        jugador_primer = self.jugadores[primer]
        await _broadcast(
            self.jugadores_sala,
            construir("PARTIDA_INICIADA", {
                "orden_turnos": self.gestor.orden_jugadores,
                "primer_turno": primer,
                "tiradas": tiradas,
                "tablero": self.tablero.to_dict(),
                "jugadores": {str(uid): j.to_dict() for uid, j in self.jugadores.items()},
            })
        )
        logger.info(f"Primer turno: {jugador_primer.username}")

    # ============================================
    # Loop principal
    # ============================================

    async def _loop_principal(self):
        MAX_TURNOS = 2000  # Evitar bucle infinito
        turno_count = 0

        while self.activa and turno_count < MAX_TURNOS:
            turno_count += 1
            jid = self.gestor.jugador_actual_id()
            if jid is None:
                break

            jugador = self.jugadores.get(jid)
            if jugador is None:
                self.gestor.avanzar_turno()
                continue

            js = self._buscar_js(jid)
            if js is None or js.desconectado:
                self.gestor.avanzar_turno()
                continue

            await self._ejecutar_turno(jugador, js)

            # Verificar victoria
            ganador = self.motor.hay_ganador(list(self.jugadores.values()))
            if ganador:
                await self._finalizar(ganador)
                return

        logger.warning(f"Partida {self.partida_id} terminó por límite de turnos")
        self.activa = False

    async def _ejecutar_turno(self, jugador: Jugador, js: JugadorEnSala):
        """Ejecuta el turno completo de un jugador."""
        self.turno_numero += 1
        retiene_turno = True
        
        while retiene_turno and self.activa:
            retiene_turno = False

            # Notificar turno
            await _broadcast(
                self.jugadores_sala,
                construir("TURNO_ASIGNADO", {
                    "jugador_id": jugador.id,
                    "username": jugador.username,
                    "color": jugador.color,
                    "turno_numero": self.turno_numero,
                    "timeout_seg": 60,
                    "tablero": self.tablero.to_dict(),
                })
            )

            # Lanzar dados
            dados = await self._lanzar_dados_turno(jugador, js)
            if dados is None:
                break

            # Procesar pares
            resultado_pares = self.motor.procesar_pares(jugador, dados)

            if resultado_pares["saca_ficha"]:
                # 3 pares consecutivos: el jugador elige una ficha para quemar
                await self._manejar_tres_pares(jugador, js, dados)
                break

            # ¿Tiene fichas en cárcel y sacó par?
            if dados.es_par and jugador.fichas_en_carcel():
                await self._manejar_salida_carcel(jugador, js, dados)

            # Movimientos normales
            movs = self.motor.calcular_movimientos_legales(self.tablero, jugador, dados)

            if not movs:
                await _broadcast(
                    self.jugadores_sala,
                    construir("SIN_MOVIMIENTOS", {
                        "jugador_id": jugador.id,
                        "username": jugador.username,
                        "dado_a": dados.valor_a,
                        "dado_b": dados.valor_b,
                    })
                )
                # Consumir oportunidad si solo tiene fichas en cárcel
                if not jugador.fichas_jugables():
                    self.motor.consumir_oportunidad_salida(jugador)
            else:
                await self._pedir_y_aplicar_movimiento(jugador, js, dados, movs)

            # Broadcast estado
            await self._broadcast_estado()

            # ¿Retiene turno por par?
            if resultado_pares["retiene_turno"]:
                retiene_turno = True
                await asyncio.sleep(0.5)

        self.gestor.avanzar_turno()

    async def _lanzar_dados_turno(self, jugador: Jugador, js: JugadorEnSala) -> Optional[ResultadoDados]:
        """Espera a que el jugador lance los dados (o el bot lo hace automático)."""
        if js.es_bot:
            await asyncio.sleep(0.8)  # Pausa visual del bot
            dados = self.dados.lanzar()
        else:
            # Esperar mensaje LANZAR_DADOS del cliente
            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None

            await _enviar(
                js.websocket,
                construir("ACCION_REQUERIDA", {
                    "accion": "LANZAR_DADOS",
                    "jugador_id": jugador.id,
                })
            )

            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=60)
                msg = self._movimiento_recibido
                if msg and msg.get("type") == "LANZAR_DADOS":
                    dados = self.dados.lanzar()
                else:
                    dados = self.dados.lanzar()
            except asyncio.TimeoutError:
                logger.warning(f"Timeout esperando dados de {jugador.username}")
                dados = self.dados.lanzar()
            finally:
                self._esperando_movimiento = None

        self.dados_actuales = dados

        await _broadcast(
            self.jugadores_sala,
            construir("DADOS_RESULTADO", {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "dado_a": dados.valor_a,
                "dado_b": dados.valor_b,
                "es_par": dados.es_par,
                "pares_consecutivos": jugador.pares_consecutivos,
            })
        )
        await asyncio.sleep(0.3)
        return dados

    async def _manejar_salida_carcel(self, jugador: Jugador, js: JugadorEnSala, dados: ResultadoDados):
        """Permite al jugador sacar fichas de la cárcel con pares."""
        fichas_en_carcel = jugador.fichas_en_carcel()
        cantidad = 2 if dados.es_par_de_seises and len(fichas_en_carcel) >= 2 else 1

        for _ in range(cantidad):
            if not jugador.fichas_en_carcel():
                break
            resultado = self.motor.sacar_de_carcel(self.tablero, jugador, dados)
            if resultado.exito:
                await _broadcast(
                    self.jugadores_sala,
                    construir("FICHA_SALIO_CARCEL", {
                        "jugador_id": jugador.id,
                        "username": jugador.username,
                        "ficha_id": resultado.ficha_movida,
                        "color": jugador.color,
                    })
                )

    async def _pedir_y_aplicar_movimiento(
        self, jugador: Jugador, js: JugadorEnSala,
        dados: ResultadoDados, movimientos
    ):
        """Pide al jugador qué ficha mover y aplica el movimiento."""
        movs_dict = [m.to_dict() for m in movimientos]

        if js.es_bot:
            # Bot elige según heurística
            from .bot_estrategia import elegir_movimiento_bot
            mov_elegido = elegir_movimiento_bot(movimientos, self.tablero, jugador)
            await asyncio.sleep(0.6)
        else:
            # Pedir decisión al jugador humano
            await _enviar(
                js.websocket,
                construir("ACCION_REQUERIDA", {
                    "accion": "MOVER_FICHA",
                    "jugador_id": jugador.id,
                    "movimientos_legales": movs_dict,
                    "dado_a": dados.valor_a,
                    "dado_b": dados.valor_b,
                })
            )

            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None

            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=60)
                msg = self._movimiento_recibido
                if msg and msg.get("type") == "MOVER_FICHA":
                    ficha_id = msg["payload"].get("ficha_id")
                    valor = msg["payload"].get("valor")
                    mov_elegido = next(
                        (m for m in movimientos if m.ficha_id == ficha_id and m.valor == valor),
                        movimientos[0]
                    )
                else:
                    mov_elegido = movimientos[0]
            except asyncio.TimeoutError:
                logger.warning(f"Timeout esperando movimiento de {jugador.username}")
                mov_elegido = movimientos[0]
            finally:
                self._esperando_movimiento = None

        # Aplicar
        resultado = self.motor.aplicar_movimiento(
            self.tablero, jugador, mov_elegido.ficha_id, mov_elegido.valor
        )

        if resultado.exito:
            msg_payload = {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "ficha_id": resultado.ficha_movida,
                "fichas_capturadas": resultado.fichas_capturadas,
                "llego_a_meta": resultado.llego_a_meta,
                "tablero": self.tablero.to_dict(),
            }
            await _broadcast(self.jugadores_sala, construir("FICHA_MOVIDA", msg_payload))

            # Notificar capturas
            for fid in resultado.fichas_capturadas:
                await _broadcast(
                    self.jugadores_sala,
                    construir("FICHA_CAPTURADA", {
                        "ficha_capturada_id": fid,
                        "captor_id": jugador.id,
                        "captor_username": jugador.username,
                    })
                )

    async def _manejar_tres_pares(self, jugador: Jugador, js: JugadorEnSala, dados: ResultadoDados):
        """El jugador elige una ficha para sacar del juego (3 pares consecutivos)."""
        fichas_en_juego = jugador.fichas_jugables()
        if not fichas_en_juego:
            return

        await _broadcast(
            self.jugadores_sala,
            construir("TRES_PARES", {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "mensaje": f"{jugador.username} sacó 3 pares. Debe elegir una ficha para quemar.",
            })
        )

        if js.es_bot or not fichas_en_juego:
            ficha_elegida = fichas_en_juego[0].id
        else:
            await _enviar(js.websocket, construir("ACCION_REQUERIDA", {
                "accion": "ELEGIR_FICHA_QUEMAR",
                "fichas_disponibles": [f.to_dict() for f in fichas_en_juego],
            }))
            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None
            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=30)
                msg = self._movimiento_recibido
                ficha_elegida = msg["payload"].get("ficha_id", fichas_en_juego[0].id) if msg else fichas_en_juego[0].id
            except asyncio.TimeoutError:
                ficha_elegida = fichas_en_juego[0].id
            finally:
                self._esperando_movimiento = None

        resultado = self.motor.quemar_ficha(self.tablero, jugador, ficha_elegida)
        if resultado.exito:
            await _broadcast(self.jugadores_sala, construir("FICHA_QUEMADA", {
                "jugador_id": jugador.id,
                "ficha_id": ficha_elegida,
                "tablero": self.tablero.to_dict(),
            }))

    async def _broadcast_estado(self):
        await _broadcast(
            self.jugadores_sala,
            construir("ESTADO_TABLERO", {
                "tablero": self.tablero.to_dict(),
                "jugadores": {str(uid): j.to_dict() for uid, j in self.jugadores.items()},
                "turno_actual": self.gestor.jugador_actual_id(),
            })
        )

    async def _finalizar(self, ganador: Jugador):
        self.activa = False
        logger.info(f"Partida {self.partida_id} ganada por {ganador.username}")
        await _broadcast(
            self.jugadores_sala,
            construir("PARTIDA_TERMINADA", {
                "ganador_id": ganador.id,
                "ganador_username": ganador.username,
                "ganador_color": ganador.color,
                "tablero": self.tablero.to_dict(),
                "estadisticas": {
                    str(uid): {
                        "fichas_en_meta": len(j.fichas_en_meta()),
                        "pares_totales": j.pares_consecutivos,
                    }
                    for uid, j in self.jugadores.items()
                }
            })
        )

    # ============================================
    # Recepción de mensajes del cliente
    # ============================================

    def recibir_mensaje(self, tipo: str, payload: dict, usuario_id: int):
        """Llamado por el Game Server cuando llega un mensaje del cliente durante la partida."""
        self._movimiento_recibido = {"type": tipo, "payload": payload, "usuario_id": usuario_id}
        if self._esperando_movimiento:
            self._esperando_movimiento.set()

    def registrar_berkeley(self, usuario_id: int, ts_cliente: float):
        from .berkeley import Berkeley
        bk = Berkeley()
        bk.registrar_respuesta(self._berkeley_respuestas, usuario_id, ts_cliente)

    def _buscar_js(self, usuario_id: int) -> Optional[JugadorEnSala]:
        for js in self.jugadores_sala:
            if js.usuario_id == usuario_id:
                return js
        return None

    def marcar_desconectado(self, usuario_id: int):
        jugador = self.jugadores.get(usuario_id)
        if jugador:
            jugador.desconectado = True
